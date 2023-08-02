import json
from pathlib import Path

from shapely.geometry import Polygon

from mindspore.mindrecord import FileWriter

from mindocr.data.utils.polygon_utils import sort_clockwise


class IC15_Converter:
    """
    Format annotation to standard form for ic15 dataset.
    The ground truth is provided in terms of word bounding boxes. Bounding boxes are specified by the coordinates of
    their four corners in a clock-wise manner. For each image a corresponding UTF-8 encoded text file is provided,
    following the naming convention:
        `[image name].txt`
    The text files are comma separated files, where each line corresponds to one text block in the image and gives
    its bounding box coordinates (four corners, clockwise) and its transcription in the format:
        `x1,y1,x2,y2,x3,y3,x4,y4,transcription`
    Note that the transcription is anything that follows the 8th comma until the end of line. No escape characters are
    to be used.
    If the transcription is provided as "###", then text block (word) is considered as "don't care".
    """

    def __init__(self, path_mode="relative", mindrecord: bool = False, **kwargs):
        self._to_mr = mindrecord
        self._path_mode = "abs" if self._to_mr else path_mode

    def convert(self, task="det", image_dir=None, label_path=None, output_path=None):
        label_path = Path(label_path)
        assert label_path.exists(), f"{label_path} no exist!"

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        if task == "det":
            self._format_det_label(Path(image_dir), label_path, output_path)
        if task == "rec":
            self._format_rec_label(label_path, output_path)

    def _format_det_label(self, image_dir, label_dir, output_path):
        if self._to_mr:
            writer = FileWriter(file_name=output_path)
            writer.add_schema({"image": {"type": "bytes"}, "label": {"type": "string"}})
        else:
            writer = open(output_path, "w")

        for label_fp in sorted(label_dir.glob("*.txt"), key=lambda path: int(path.stem.split("_")[-1])):
            img_path = image_dir / (label_fp.stem.split("_", 1)[1] + ".jpg")
            assert (
                img_path.exists()
            ), f"{img_path} not exist! Please check the input image_dir {image_dir} and names in {label_fp}"

            label = []
            with open(label_fp, "r", encoding="utf-8-sig") as f:
                for line in f.readlines():
                    line = line.strip("\n\r").replace("\xef\xbb\xbf", "").split(",", 8)

                    points = [[int(line[i]), int(line[i + 1])] for i in range(0, 8, 2)]  # reshape points (4, 2)
                    # sort points and validate
                    points = sort_clockwise(points).tolist()
                    if not Polygon(points).is_valid:
                        print(f"Warning {img_path.name}: skipping invalid polygon {points}")
                        continue

                    label.append({"transcription": line[8], "points": points})

            img_path = img_path.name if self._path_mode == "relative" else str(img_path)
            label = json.dumps(label, ensure_ascii=False)
            if self._to_mr:
                with open(img_path, "rb") as f:
                    img = f.read()
                writer.write_raw_data([{"image": img, "label": label}])
            else:
                writer.write(img_path + "\t" + label + "\n")

        if self._to_mr:
            writer.commit()
        else:
            writer.close()

    def _format_rec_label(self, label_path, output_path):
        with open(output_path, "w") as outf:
            with open(label_path, "r") as f:
                for line in f:
                    # , may occur in text
                    sep_index = line.find(",")
                    img_path = line[:sep_index].strip().replace("\ufeff", "")
                    label = line[sep_index + 1 :].strip().replace('"', "")
                    outf.write(img_path + "\t" + label + "\n")

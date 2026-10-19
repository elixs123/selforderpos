import os
import threading
import urllib.request
from pathlib import Path

import cv2
import numpy as np

MODELS_FOLDER = Path(__file__).resolve().parent / "models"
MODEL_URL = "https://github.com/Megvii-BaseDetection/YOLOX/releases/download/0.1.1rc0/yolox_s.onnx"
MODEL_FILE = "yolox_s.onnx"
INPUT_SIZE = 640
MIN_CONFIDENCE = 0.5
MATCH_IOU = 0.3
IGNORED_CLASSES = {0, 56, 57, 58, 59, 60, 61, 62, 63, 66, 68, 69, 70, 71, 72}
DEFAULT_CAMERAS = "A2,B2"


def enabled() -> bool:
    return os.environ.get("CAM_COUNTER", "yolox").lower() not in ("", "off", "0", "ne")


def counting_cameras() -> set[str]:
    return {name.strip() for name in os.environ.get("CAM_COUNT_CAMERAS", DEFAULT_CAMERAS).split(",") if name.strip()}


def iou(first: np.ndarray, second: np.ndarray) -> float:
    left, top = max(first[0], second[0]), max(first[1], second[1])
    right, bottom = min(first[2], second[2]), min(first[3], second[3])
    inner = max(0.0, right - left) * max(0.0, bottom - top)
    union = (first[2] - first[0]) * (first[3] - first[1]) + (second[2] - second[0]) * (second[3] - second[1]) - inner
    return inner / union if union > 0 else 0.0


def unmatched(boxes: list[np.ndarray], others: list[np.ndarray]) -> list[np.ndarray]:
    return [box for box in boxes if all(iou(box, other) < MATCH_IOU for other in others)]


class ObjectCounter:
    def __init__(self, path: Path | None = None) -> None:
        import onnxruntime

        path = path or self._download()
        self.session = onnxruntime.InferenceSession(str(path), providers=["CPUExecutionProvider"])
        self.input_name = self.session.get_inputs()[0].name
        grids, strides = [], []
        for stride in (8, 16, 32):
            cells = INPUT_SIZE // stride
            rows, columns = np.meshgrid(np.arange(cells), np.arange(cells), indexing="ij")
            grids.append(np.stack((columns, rows), 2).reshape(-1, 2))
            strides.append(np.full((cells * cells, 1), stride))
        self.grids, self.strides = np.concatenate(grids), np.concatenate(strides)
        self.lock = threading.Lock()

    @staticmethod
    def _download() -> Path:
        path = MODELS_FOLDER / MODEL_FILE
        if not path.exists():
            MODELS_FOLDER.mkdir(parents=True, exist_ok=True)
            print("Preuzimam model za brojanje artikala (YOLOX-s, 36 MB)...")
            partial = path.with_suffix(".part")
            urllib.request.urlretrieve(MODEL_URL, partial)
            partial.rename(path)
        return path

    def detect(self, image: np.ndarray) -> list[np.ndarray]:
        if image is None or image.size == 0:
            return []
        height, width = image.shape[:2]
        ratio = min(INPUT_SIZE / height, INPUT_SIZE / width)
        canvas = np.full((INPUT_SIZE, INPUT_SIZE, 3), 114, np.uint8)
        canvas[:int(height * ratio), :int(width * ratio)] = cv2.resize(image, (int(width * ratio), int(height * ratio)))
        with self.lock:
            output = self.session.run(None, {self.input_name: canvas.transpose(2, 0, 1)[None].astype(np.float32)})[0][0]
        centers = (output[:, :2] + self.grids) * self.strides
        sizes = np.exp(output[:, 2:4]) * self.strides
        scores = output[:, 4:5] * output[:, 5:]
        classes, confidence = scores.argmax(1), scores.max(1)
        keep = (confidence >= MIN_CONFIDENCE) & ~np.isin(classes, list(IGNORED_CLASSES))
        if not keep.any():
            return []
        centers, sizes, confidence = centers[keep], sizes[keep], confidence[keep]
        boxes = np.concatenate([centers - sizes / 2, centers + sizes / 2], 1) / ratio
        rectangles = [[float(x1), float(y1), float(x2 - x1), float(y2 - y1)] for x1, y1, x2, y2 in boxes]
        chosen = np.array(cv2.dnn.NMSBoxes(rectangles, confidence.tolist(), MIN_CONFIDENCE, 0.45)).reshape(-1)
        return [boxes[index] for index in chosen]


_counter = None
_failed = False


def get_counter() -> ObjectCounter | None:
    global _counter, _failed
    if _counter is None and not _failed and enabled():
        try:
            _counter = ObjectCounter()
        except Exception as error:
            print(f"Brojanje artikala (YOLOX) nije dostupno: {error}")
            _failed = True
    return _counter

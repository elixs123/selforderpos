import os
import threading
import time
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
# YOLOX zna "izgubiti" artikal koji se preklapa sa drugim; manji broj u zoni B vrijedi tek kad je toliko stabilan.
B_DROP_SECONDS = 8.0
# Isto u zoni A: "uzeto više artikala" vrijedi tek kad YOLOX toliko dugo vidi manjak od 2 i više.
A_CONFIRM_SECONDS = 3.0


def enabled() -> bool:
    """YOLOX broji artikle; uključuje se u Postavke > Kamere (upisuje se u CAM_COUNTER pri pokretanju kamera)."""
    return os.environ.get("CAM_COUNTER", "yolox").lower() not in ("", "off", "0", "ne")


def providers(available: list[str]) -> list:
    """Na Macu YOLOX ide kroz CoreML (izmjereno ~3x brže od procesora); CPU ostaje kao rezerva."""
    if "CoreMLExecutionProvider" in available and os.environ.get("CAM_COREML", "1") != "0":
        return [("CoreMLExecutionProvider", {"MLComputeUnits": "ALL"}), "CPUExecutionProvider"]
    return ["CPUExecutionProvider"]


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
        try:
            self.session = onnxruntime.InferenceSession(str(path), providers=providers(onnxruntime.get_available_providers()))
        except Exception:
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

    def detect(self, image: np.ndarray, ignored: set[int] | None = None) -> list[np.ndarray]:
        skipped = IGNORED_CLASSES if ignored is None else ignored
        return [box for _, _, box in self.detections(image, MIN_CONFIDENCE, skipped)]

    def detections(
        self, image: np.ndarray, min_confidence: float = MIN_CONFIDENCE, skipped: set[int] = frozenset(),
    ) -> list[tuple[int, float, np.ndarray]]:
        """(COCO klasa, pouzdanost, okvir x1 y1 x2 y2); klase iz skipped se izbace prije NMS-a."""
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
        keep = (confidence >= min_confidence) & ~np.isin(classes, list(skipped))
        if not keep.any():
            return []
        centers, sizes, confidence, classes = centers[keep], sizes[keep], confidence[keep], classes[keep]
        boxes = np.concatenate([centers - sizes / 2, centers + sizes / 2], 1) / ratio
        rectangles = [[float(x1), float(y1), float(x2 - x1), float(y2 - y1)] for x1, y1, x2, y2 in boxes]
        chosen = np.array(cv2.dnn.NMSBoxes(rectangles, confidence.tolist(), min_confidence, 0.45)).reshape(-1)
        return [(int(classes[index]), float(confidence[index]), boxes[index]) for index in chosen]

_counter = None
_failed = False


def failed() -> bool:
    """YOLOX se nije mogao učitati; bez njega kasa ne smije raditi (brojanje artikala je obavezno)."""
    return _failed


def get_counter() -> ObjectCounter | None:
    """YOLOX služi samo za brojanje artikala; prepoznavanje rade drugi modeli (similarity)."""
    global _counter, _failed
    if not enabled():
        return None
    if _counter is None and not _failed:
        try:
            _counter = ObjectCounter()
        except Exception as error:
            print(f"Brojanje artikala (YOLOX) nije dostupno: {error}")
            _failed = True
    return _counter


class ZoneALedger:
    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.expected: int | None = None
        self.pending: int | None = None
        self.count: int | None = None
        self.missing = 0
        self.extra_after_accept = False
        self.post_accept = False
        self._more_since: float | None = None

    def observe(self, count: int, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        if count != self.pending:
            self.pending = count
            return False
        before = (self.missing, self.extra_after_accept, self.count)
        self.count = count
        if self.expected is None or count >= self.expected:
            self.expected = count
            self.missing = 0
            self.extra_after_accept = False
            self._more_since = None
        else:
            missing = self.expected - count
            if missing >= 2 and missing > self.missing:
                if self._more_since is None:
                    self._more_since = now
                if now - self._more_since < A_CONFIRM_SECONDS:
                    return before != (self.missing, self.extra_after_accept, self.count)
            self._more_since = None
            self.missing = missing
        if self.post_accept:
            self.extra_after_accept = self.missing >= 1
            self.post_accept = False
        return before != (self.missing, self.extra_after_accept, self.count)

    def accepted(self) -> None:
        if self.expected is not None:
            self.expected -= 1
        self.missing = max(0, self.missing - 1)
        self.pending = None
        self.post_accept = True
        self._more_since = None


class ZoneBLedger:
    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.known: int | None = None
        self.pending: int | None = None
        self.extra = 0
        self._lower_since: float | None = None

    def observe(self, count: int, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        if count != self.pending:
            self.pending = count
            return False
        before = self.extra
        if self.known is None:
            self.known = count
        elif count < self.known:
            # Artikal uzet iz zone B (pakovanje) ili ga YOLOX samo trenutno ne vidi: known se smanji tek poslije B_DROP_SECONDS.
            if self._lower_since is None:
                self._lower_since = now
            if now - self._lower_since >= B_DROP_SECONDS:
                self.known, self._lower_since = count, None
        else:
            self._lower_since = None
        self.extra = max(0, count - self.known)
        return before != self.extra

    def accepted(self, count: int | None) -> None:
        if count is not None:
            # Prihvaćen artikal je u zoni B: bar jedan više nego prije, i kad ga YOLOX u tom trenutku ne vidi (zaklonjen).
            self.known = count if self.known is None else max(count, self.known + 1)
        self.pending = None
        self.extra = 0
        self._lower_since = None

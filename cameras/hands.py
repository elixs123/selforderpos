import urllib.request
from pathlib import Path

import cv2
import numpy as np

MODEL_URL = "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/latest/hand_landmarker.task"
MODEL_PATH = Path(__file__).resolve().parent / "models" / "hand_landmarker.task"
DETECT_WIDTH = 320


def download_model() -> Path:
    if MODEL_PATH.exists():
        return MODEL_PATH
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    print("Preuzimam model za ruke (8 MB)...")
    partial = MODEL_PATH.with_suffix(".part")
    urllib.request.urlretrieve(MODEL_URL, partial)
    partial.rename(MODEL_PATH)
    return MODEL_PATH


class HandDetector:
    def __init__(self) -> None:
        import mediapipe
        from mediapipe.tasks.python import vision
        from mediapipe.tasks.python.core.base_options import BaseOptions

        self._mediapipe = mediapipe
        options = vision.HandLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(download_model())),
            running_mode=vision.RunningMode.IMAGE,
            num_hands=4,
            min_hand_detection_confidence=0.4,
        )
        self._landmarker = vision.HandLandmarker.create_from_options(options)

    def find(self, image: np.ndarray) -> list[np.ndarray]:
        height, width = image.shape[:2]
        scale = DETECT_WIDTH / width
        small = cv2.resize(image, (DETECT_WIDTH, max(1, round(height * scale))))
        rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
        result = self._landmarker.detect(self._mediapipe.Image(image_format=self._mediapipe.ImageFormat.SRGB, data=rgb))
        hulls = []
        for landmarks in result.hand_landmarks:
            points = np.array([[point.x * width, point.y * height] for point in landmarks], dtype=np.int32)
            hulls.append(cv2.convexHull(points))
        return hulls

    def mask(self, image: np.ndarray, margin: int = 25) -> tuple[np.ndarray, list[np.ndarray]]:
        hulls = self.find(image)
        mask = np.zeros(image.shape[:2], dtype=np.uint8)
        if hulls:
            cv2.fillPoly(mask, hulls, 255)
            mask = cv2.dilate(mask, np.ones((margin, margin), np.uint8))
        return mask, hulls


def load_hand_detector() -> HandDetector | None:
    try:
        return HandDetector()
    except Exception as error:
        print(f"Prepoznavanje ruku nije dostupno ({error}). Kamere rade bez njega.")
        return None

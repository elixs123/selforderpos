import os
from dataclasses import dataclass

import cv2
import numpy as np

COLOR_THRESHOLD = 0.5
WORK_SIZE = 200

_embedder = None
_embedder_failed = False


def get_embedder():
    global _embedder, _embedder_failed
    if _embedder is None and not _embedder_failed:
        try:
            from embedder import Embedder

            _embedder = Embedder()
        except Exception as error:
            print(f"AI model nije dostupan, koristim boju i oblik: {error}")
            _embedder_failed = True
    return _embedder


def method_name() -> str:
    embedder = get_embedder()
    return embedder.name if embedder else "boja+oblik"


def match_threshold() -> float:
    custom = os.environ.get("CAM_MATCH_THRESHOLD")
    if custom:
        return float(custom)
    embedder = get_embedder()
    return embedder.threshold if embedder else COLOR_THRESHOLD


def _prepare(image: np.ndarray) -> np.ndarray:
    height, width = image.shape[:2]
    scale = WORK_SIZE / max(height, width)
    return cv2.resize(image, (max(1, round(width * scale)), max(1, round(height * scale))))


def color_histogram(image: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    histogram = cv2.calcHist([hsv], [0, 1], None, [30, 32], [0, 180, 0, 256])
    cv2.normalize(histogram, histogram)
    return histogram


def color_similarity(first: np.ndarray, second: np.ndarray) -> float:
    return max(0.0, cv2.compareHist(color_histogram(first), color_histogram(second), cv2.HISTCMP_CORREL))


def shape_similarity(first: np.ndarray, second: np.ndarray) -> float:
    orb = cv2.ORB_create(500)
    keypoints_first, descriptors_first = orb.detectAndCompute(cv2.cvtColor(first, cv2.COLOR_BGR2GRAY), None)
    keypoints_second, descriptors_second = orb.detectAndCompute(cv2.cvtColor(second, cv2.COLOR_BGR2GRAY), None)
    if descriptors_first is None or descriptors_second is None:
        return 0.0
    matcher = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
    good = [match for match in matcher.match(descriptors_first, descriptors_second) if match.distance < 50]
    smaller = max(1, min(len(keypoints_first), len(keypoints_second)))
    return min(1.0, 2 * len(good) / smaller)


def classic_similarity(first: np.ndarray, second: np.ndarray) -> float:
    first, second = _prepare(first), _prepare(second)
    return round(0.6 * color_similarity(first, second) + 0.4 * shape_similarity(first, second), 3)


@dataclass
class Signature:
    image: np.ndarray
    histogram: np.ndarray
    vectors: list[np.ndarray] | None


def signature(image: np.ndarray, rotations: bool = True) -> Signature:
    small = _prepare(image)
    embedder = get_embedder()
    vectors = None
    if embedder is not None:
        vectors = embedder.embed_rotations(image) if rotations else [embedder.embed(image)]
    return Signature(small, color_histogram(small), vectors)


def compare(query: Signature, reference: Signature) -> float:
    color = max(0.0, cv2.compareHist(query.histogram, reference.histogram, cv2.HISTCMP_CORREL))
    if query.vectors and reference.vectors:
        ai = max(float(first @ second) for first in query.vectors for second in reference.vectors)
        return round(0.7 * ai + 0.3 * color, 3)
    return round(0.6 * color + 0.4 * shape_similarity(query.image, reference.image), 3)


def similarity(first: np.ndarray | None, second: np.ndarray | None) -> float:
    if first is None or second is None or first.size == 0 or second.size == 0:
        return 0.0
    return compare(signature(first), signature(second, rotations=False))

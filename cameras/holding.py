from dataclasses import dataclass, field

import numpy as np

from counter import IGNORED_CLASSES, get_counter
from hands import HandDetector
from zones import crop

HOLD_IGNORED = IGNORED_CLASSES | {24, 25, 26, 27, 28, 67}
HOLD_MARGIN = 0.25
HOLD_OVERLAP = 0.2


@dataclass
class HoldResult:
    held: bool = False
    hands: list[np.ndarray] = field(default_factory=list)
    items: list[np.ndarray] = field(default_factory=list)
    held_items: list[np.ndarray] = field(default_factory=list)


def hand_box(hull: np.ndarray, margin: float = HOLD_MARGIN) -> np.ndarray:
    points = hull.reshape(-1, 2)
    left, top = points.min(0)
    right, bottom = points.max(0)
    pad_x, pad_y = (right - left) * margin, (bottom - top) * margin
    return np.array([left - pad_x, top - pad_y, right + pad_x, bottom + pad_y], dtype=float)


def covered_share(item: np.ndarray, area: np.ndarray) -> float:
    """Koliki dio okvira predmeta leži unutar okvira ruke."""
    left, top = max(item[0], area[0]), max(item[1], area[1])
    right, bottom = min(item[2], area[2]), min(item[3], area[3])
    inner = max(0.0, right - left) * max(0.0, bottom - top)
    whole = max(1.0, (item[2] - item[0]) * (item[3] - item[1]))
    return inner / whole


def held_items(hulls: list[np.ndarray], items: list[np.ndarray]) -> list[np.ndarray]:
    boxes = [hand_box(hull) for hull in hulls]
    return [item for item in items if any(covered_share(item, box) >= HOLD_OVERLAP for box in boxes)]


class HeldItemDetector:
    """Kamere C: ruka kupca + predmet (YOLOX) koji se preklapa s rukom = artikal u ruci."""

    def __init__(self, hands: HandDetector | None) -> None:
        self.hands = hands

    def check(self, frame: np.ndarray, zone) -> HoldResult:
        counter = get_counter()
        if self.hands is None or counter is None or frame is None:
            return HoldResult()
        roi, (offset_x, offset_y) = crop(frame, zone)
        if roi.size == 0:
            return HoldResult()
        hulls = self.hands.find(roi)
        if not hulls:
            return HoldResult()
        items = counter.detect(roi, HOLD_IGNORED)
        shift = np.array([offset_x, offset_y], dtype=float)
        shifted_hulls = [hull + shift.astype(hull.dtype) for hull in hulls]
        shifted_items = [item + np.array([offset_x, offset_y, offset_x, offset_y], dtype=float) for item in items]
        holding = held_items(shifted_hulls, shifted_items)
        return HoldResult(bool(holding), shifted_hulls, shifted_items, holding)

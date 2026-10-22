from collections import deque
from dataclasses import dataclass, field

import cv2
import numpy as np

from counter import IGNORED_CLASSES, get_counter
from zones import crop

PERSON = 0
ITEM_IGNORED = (IGNORED_CLASSES - {PERSON}) | {24, 25, 26, 27, 28, 67}
PERSON_CONFIDENCE = 0.5
ITEM_CONFIDENCE = 0.35
HELD_OVERLAP = 0.5
PERSON_MARGIN = 0.1
STATIC_IOU = 0.3
STILL_IOU = 0.8
STILL_PASSES = 4
MERGE_IOU = 0.5


@dataclass
class HoldResult:
    held: bool = False
    people: list[np.ndarray] = field(default_factory=list)
    items: list[np.ndarray] = field(default_factory=list)
    held_items: list[np.ndarray] = field(default_factory=list)


def iou(first: np.ndarray, second: np.ndarray) -> float:
    left, top = max(first[0], second[0]), max(first[1], second[1])
    right, bottom = min(first[2], second[2]), min(first[3], second[3])
    inner = max(0.0, right - left) * max(0.0, bottom - top)
    union = (first[2] - first[0]) * (first[3] - first[1]) + (second[2] - second[0]) * (second[3] - second[1]) - inner
    return inner / union if union > 0 else 0.0


def covered_share(item: np.ndarray, area: np.ndarray) -> float:
    """Koliki dio okvira predmeta leži unutar okvira osobe."""
    left, top = max(item[0], area[0]), max(item[1], area[1])
    right, bottom = min(item[2], area[2]), min(item[3], area[3])
    inner = max(0.0, right - left) * max(0.0, bottom - top)
    return inner / max(1.0, (item[2] - item[0]) * (item[3] - item[1]))


def widened(box: np.ndarray, margin: float = PERSON_MARGIN) -> np.ndarray:
    pad_x, pad_y = (box[2] - box[0]) * margin, (box[3] - box[1]) * margin
    return np.array([box[0] - pad_x, box[1] - pad_y, box[2] + pad_x, box[3] + pad_y], dtype=float)


def merged(boxes: list[np.ndarray]) -> list[np.ndarray]:
    kept: list[np.ndarray] = []
    for box in boxes:
        if all(iou(box, other) < MERGE_IOU for other in kept):
            kept.append(box)
    return kept


def tiles(image: np.ndarray) -> list[tuple[np.ndarray, int, int]]:
    """Četiri preklopljene pločice (2/3 visine i širine): artikal u ruci je odozgo mali, pa ga YOLOX bolje vidi uvećanog."""
    height, width = image.shape[:2]
    part_h, part_w = 2 * height // 3, 2 * width // 3
    return [(image[y:y + part_h, x:x + part_w], x, y) for y in (0, height - part_h) for x in (0, width - part_w)]


class HeldItemDetector:
    """Kamere C (odozgo): osoba + predmet koji se nalazi uz osobu i pomjera se = artikal u ruci.

    Predmeti koji stoje na kasi (vide se i kad nema osobe, ili miruju nekoliko provjera) se ne računaju.
    """

    def __init__(self) -> None:
        self.static: dict[str, list[np.ndarray]] = {}
        self.history: dict[str, deque] = {}

    def check(self, name: str, frame: np.ndarray, zone) -> HoldResult:
        counter = get_counter()
        if counter is None or frame is None:
            return HoldResult()
        roi, (offset_x, offset_y) = crop(frame, zone)
        if roi.size == 0:
            return HoldResult()
        shift = np.array([offset_x, offset_y, offset_x, offset_y], dtype=float)
        whole = counter.detections(roi, ITEM_CONFIDENCE, ITEM_IGNORED)
        people = [box for kind, score, box in whole if kind == PERSON and score >= PERSON_CONFIDENCE]
        history = self.history.setdefault(name, deque(maxlen=STILL_PASSES))
        if not people:
            self.static[name] = [box for kind, _, box in whole if kind != PERSON]
            history.clear()
            return HoldResult()
        found = [box for kind, _, box in whole if kind != PERSON]
        for part, x, y in tiles(roi):
            found += [box + np.array([x, y, x, y], dtype=float)
                      for kind, _, box in counter.detections(part, ITEM_CONFIDENCE, ITEM_IGNORED) if kind != PERSON]
        items = merged(sorted(found, key=lambda box: (box[2] - box[0]) * (box[3] - box[1]), reverse=True))
        static = self.static.get(name, [])
        moving = [item for item in items
                  if all(iou(item, other) < STATIC_IOU for other in static) and not self._still(item, history)]
        history.append(items)
        areas = [widened(person) for person in people]
        held = [item for item in moving if any(covered_share(item, area) >= HELD_OVERLAP for area in areas)]
        return HoldResult(bool(held), [box + shift for box in people], [box + shift for box in items], [box + shift for box in held])

    @staticmethod
    def _still(item: np.ndarray, history: deque) -> bool:
        """Predmet koji stoji na istom mjestu u svim zadnjim provjerama leži (npr. na kasi), ne drži se u ruci."""
        return len(history) == history.maxlen and all(any(iou(item, old) >= STILL_IOU for old in past) for past in history)


def draw(frame: np.ndarray, result: HoldResult, held_color, item_color, person_color) -> None:
    for person in result.people:
        cv2.rectangle(frame, (int(person[0]), int(person[1])), (int(person[2]), int(person[3])), person_color, 3)
    for item in result.items:
        held = any(item is other or np.array_equal(item, other) for other in result.held_items)
        cv2.rectangle(frame, (int(item[0]), int(item[1])), (int(item[2]), int(item[3])), held_color if held else item_color, 4 if held else 2)

from dataclasses import dataclass

import cv2
import numpy as np

PIXEL_THRESHOLD = 25
EMPTY_SHARE = 0.6


def _small(image: np.ndarray, work_width: int) -> tuple[np.ndarray, float]:
    height, width = image.shape[:2]
    scale = width / work_width
    return cv2.resize(image, (work_width, max(1, round(height / scale)))), scale


def _gray(image: np.ndarray, work_width: int) -> tuple[np.ndarray, float]:
    small, scale = _small(image, work_width)
    if small.ndim == 2:
        small = cv2.cvtColor(small, cv2.COLOR_GRAY2BGR)
    return cv2.GaussianBlur(small, (5, 5), 0), scale


def _distance(first: np.ndarray, second: np.ndarray) -> np.ndarray:
    return cv2.absdiff(first, second).max(axis=2)


def _ignore(ignore: np.ndarray | None, shape: tuple[int, int]) -> np.ndarray | None:
    if ignore is None:
        return None
    return cv2.resize(ignore, (shape[1], shape[0]), interpolation=cv2.INTER_NEAREST) > 0


def _difference(first: np.ndarray, second: np.ndarray, *ignores: np.ndarray | None) -> np.ndarray:
    _, mask = cv2.threshold(_distance(first, second), PIXEL_THRESHOLD, 255, cv2.THRESH_BINARY)
    for ignore in ignores:
        if ignore is not None:
            mask[ignore] = 0
    return mask


def _ratio(mask: np.ndarray) -> float:
    return cv2.countNonZero(mask) / mask.size


def changed_box(before: np.ndarray, after: np.ndarray, padding: int = 10) -> tuple[int, int, int, int] | None:
    if before.shape != after.shape:
        return None
    first = cv2.GaussianBlur(before, (5, 5), 0)
    second = cv2.GaussianBlur(after, (5, 5), 0)
    mask = cv2.morphologyEx(_difference(first, second), cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    points = cv2.findNonZero(mask)
    if points is None or len(points) < 0.005 * mask.size:
        return None
    x, y, w, h = cv2.boundingRect(points)
    height, width = mask.shape
    left, top = max(0, x - padding), max(0, y - padding)
    return left, top, min(width, x + w + padding) - left, min(height, y + h + padding) - top


@dataclass(frozen=True)
class Placement:
    box: tuple[int, int, int, int]
    change_ratio: float


class ZoneWatcher:
    def __init__(
        self,
        change_min: float = 0.01,
        motion_max: float = 0.004,
        stable_seconds: float = 0.8,
        work_width: int = 320,
    ) -> None:
        self.change_min = change_min
        self.motion_max = motion_max
        self.stable_seconds = stable_seconds
        self.work_width = work_width
        self.armed = False
        self.change_ratio = 0.0
        self.motion_ratio = 0.0
        self._baseline: np.ndarray | None = None
        self._previous: np.ndarray | None = None
        self._previous_ignore: np.ndarray | None = None
        self._stable_since: float | None = None
        self._scale = 1.0
        self._waiting_for_motion = False

    def arm(self, image: np.ndarray) -> None:
        self._baseline, self._scale = _gray(image, self.work_width)
        self._previous = self._baseline
        self._previous_ignore = None
        self._stable_since = None
        self._waiting_for_motion = False
        self.armed = True

    def rearm(self) -> None:
        self._stable_since = None
        self._waiting_for_motion = True
        self.armed = True

    def disarm(self) -> None:
        self.armed = False
        self._stable_since = None

    def update(self, image: np.ndarray, now: float, ignore: np.ndarray | None = None) -> Placement | None:
        gray, self._scale = _gray(image, self.work_width)
        hand = _ignore(ignore, gray.shape)
        if self._previous is not None and self._previous.shape == gray.shape:
            self.motion_ratio = _ratio(_difference(gray, self._previous, hand, self._previous_ignore))
        self._previous, self._previous_ignore = gray, hand
        if self._baseline is None or self._baseline.shape != gray.shape:
            return None
        change_mask = _difference(gray, self._baseline, hand)
        self.change_ratio = _ratio(change_mask)
        if not self.armed:
            return None
        if self._waiting_for_motion:
            if self.motion_ratio > self.motion_max:
                self._waiting_for_motion = False
            return None
        if self.change_ratio < self.change_min or self.motion_ratio > self.motion_max:
            self._stable_since = None
            return None
        if self._stable_since is None:
            self._stable_since = now
            return None
        if now - self._stable_since < self.stable_seconds:
            return None
        self.disarm()
        x, y, w, h = cv2.boundingRect(cv2.findNonZero(change_mask))
        box = tuple(round(value * self._scale) for value in (x, y, w, h))
        return Placement(box, self.change_ratio)


@dataclass(frozen=True)
class BasketEvent:
    kind: str
    item: np.ndarray | None
    change_ratio: float


class BasketTracker:
    def __init__(
        self,
        motion_max: float = 0.004,
        stable_seconds: float = 0.8,
        change_min: float = 0.002,
        clear_ratio: float = 0.25,
        occupied_min: float = 0.01,
        work_width: int = 320,
    ) -> None:
        self.motion_max = motion_max
        self.stable_seconds = stable_seconds
        self.change_min = change_min
        self.clear_ratio = clear_ratio
        self.occupied_min = occupied_min
        self.work_width = work_width
        self.motion_ratio = 0.0
        self.occupancy = 0.0
        self.last_note = "-"
        self._previous: np.ndarray | None = None
        self._previous_ignore: np.ndarray | None = None
        self._background: np.ndarray | None = None
        self._stable_gray: np.ndarray | None = None
        self._stable_image: np.ndarray | None = None
        self._stable_ignore: np.ndarray | None = None
        self._stable_since: float | None = None
        self._moved = False

    @property
    def ready(self) -> bool:
        return self._background is not None

    @property
    def occupied(self) -> bool:
        return self.occupancy >= self.occupied_min

    def _clean(self, mask: np.ndarray) -> np.ndarray:
        return cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))

    def update(self, image: np.ndarray, now: float, ignore: np.ndarray | None = None) -> BasketEvent | None:
        gray, scale = _gray(image, self.work_width)
        hand = _ignore(ignore, gray.shape)
        if self._previous is not None and self._previous.shape == gray.shape:
            self.motion_ratio = _ratio(_difference(gray, self._previous, hand, self._previous_ignore))
        self._previous, self._previous_ignore = gray, hand
        if self.motion_ratio > self.motion_max:
            self._stable_since = None
            self._moved = True
            return None
        if self._stable_since is None:
            self._stable_since = now
            return None
        if now - self._stable_since < self.stable_seconds:
            return None
        if self._background is None or self._background.shape != gray.shape:
            if hand is not None and hand.any():
                return None
            self._background = gray
            self._stable_gray, self._stable_image, self._stable_ignore = gray, image.copy(), hand
            self.occupancy = 0.0
            self._moved = False
            return BasketEvent("empty", None, 0.0)
        if not self._moved:
            return None
        self._moved = False
        mask = self._clean(_difference(gray, self._stable_gray, hand, self._stable_ignore))
        change = _ratio(mask)
        old_gray, old_image = self._stable_gray, self._stable_image
        self._stable_gray, self._stable_image, self._stable_ignore = gray, image.copy(), hand
        self.occupancy = _ratio(self._clean(_difference(gray, self._background, hand)))
        if change < self.change_min:
            self.last_note = f"premala promjena {change:.2%}"
            return None
        selected = mask > 0
        old_was_empty = float((_distance(old_gray, self._background)[selected] < PIXEL_THRESHOLD).mean())
        new_is_empty = float((_distance(gray, self._background)[selected] < PIXEL_THRESHOLD).mean())
        self.last_note = f"promjena {change:.2%}, prije prazno {old_was_empty:.0%}, sad prazno {new_is_empty:.0%}"
        if old_was_empty >= EMPTY_SHARE:
            return BasketEvent("added", None, change)
        x, y, w, h = cv2.boundingRect(cv2.findNonZero(mask))
        padding = 6
        left, top = max(0, round((x - padding) * scale)), max(0, round((y - padding) * scale))
        right, bottom = round((x + w + padding) * scale), round((y + h + padding) * scale)
        return BasketEvent("taken", old_image[top:bottom, left:right].copy(), change)

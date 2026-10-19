import time
from collections import deque
from dataclasses import dataclass

import cv2
import numpy as np

VERSION = "zona A v6 (poravnanje svjetla, provjera sadržaja izreza, pomjeren artikal se ne računa)"
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


PART_MIN_SHARE = 0.002
OCCUPIED_SHARE = 0.25
ALIGN_RANGE = 45
MAX_ITEM_SHARE = 0.6
FREED_ITEM_SHARE = 0.95
WHOLE_ZONE_SHARE = 0.9
MIN_TEXTURE = 6.0
WHITE_LEVEL = 200
STILL_THERE = 0.9
NEAR_SHARE = 0.4
MULTI_MIN_SHARE = 0.012
MULTI_RELATIVE = 0.15
MERGE_GAP = 0.15


def align(reference: np.ndarray, image: np.ndarray) -> np.ndarray:
    difference = image.astype(np.int16) - reference.astype(np.int16)
    close = np.abs(difference).max(axis=2) < ALIGN_RANGE
    if close.mean() < 0.2:
        return reference
    offset = np.median(difference[close], axis=0).astype(np.int16)
    if np.abs(offset).max() < 4:
        return reference
    return np.clip(reference.astype(np.int16) + offset, 0, 255).astype(np.uint8)


def reject_reason(old_gray: np.ndarray, gray: np.ndarray, background: np.ndarray, box: tuple[int, int, int, int],
                  max_share: float = MAX_ITEM_SHARE) -> str | None:
    x, y, w, h = box
    if w * h > max_share * gray.shape[0] * gray.shape[1]:
        return "izrez je prevelik (promjena svjetla ili cijela zona)"
    if not was_occupied(old_gray, background, box):
        return "izrez je prazna podloga"
    patch = old_gray[y:y + h, x:x + w]
    if patch.size == 0:
        return "izrez je prazan"
    mean, spread = cv2.meanStdDev(patch)
    if float(spread.max()) < MIN_TEXTURE and float(mean.min()) > WHITE_LEVEL:
        return "izrez je jednolična bijela slika"
    height, width = gray.shape[:2]
    pad_x, pad_y = round(NEAR_SHARE * w), round(NEAR_SHARE * h)
    left, top = max(0, x - pad_x), max(0, y - pad_y)
    window = gray[top:min(height, y + h + pad_y), left:min(width, x + w + pad_x)]
    if window.shape[0] > h and window.shape[1] > w and w > 3 and h > 3:
        match = cv2.matchTemplate(window, patch, cv2.TM_CCOEFF_NORMED)
        if float(np.nan_to_num(match).max()) >= STILL_THERE:
            return "isti artikal je još tu, samo pomjeren"
    return None
CORE_SHARE = 0.5
MIN_THICKNESS = 3


def thick_blobs(mask: np.ndarray) -> list[tuple[int, tuple[int, int, int, int]]]:
    cleaned = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    thickness = cv2.distanceTransform(cleaned, cv2.DIST_L2, 3)
    peak = float(thickness.max())
    if peak < MIN_THICKNESS:
        return []
    core = (thickness >= CORE_SHARE * peak).astype(np.uint8) * 255
    radius = int(np.ceil(CORE_SHARE * peak)) + 1
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * radius + 1, 2 * radius + 1))
    blob = cv2.bitwise_and(cv2.dilate(core, kernel), cleaned)
    count, _, stats, _ = cv2.connectedComponentsWithStats(blob)
    parts = [(int(stats[index, cv2.CC_STAT_AREA]), tuple(int(value) for value in stats[index, :4]))
             for index in range(1, count) if stats[index, cv2.CC_STAT_AREA] >= PART_MIN_SHARE * mask.size]
    return sorted(parts, reverse=True)


def _box_gap(first: tuple[int, int, int, int], second: tuple[int, int, int, int]) -> float:
    fx, fy, fw, fh = first
    sx, sy, sw, sh = second
    dx = max(sx - (fx + fw), fx - (sx + sw), 0)
    dy = max(sy - (fy + fh), fy - (sy + sh), 0)
    return float(np.hypot(dx, dy))


def _union(first: tuple[int, int, int, int], second: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    left, top = min(first[0], second[0]), min(first[1], second[1])
    right = max(first[0] + first[2], second[0] + second[2])
    bottom = max(first[1] + first[3], second[1] + second[3])
    return left, top, right - left, bottom - top


def separate_items(mask: np.ndarray) -> list[tuple[int, tuple[int, int, int, int]]]:
    clusters = [list(part) for part in thick_blobs(mask)]
    merged = True
    while merged:
        merged = False
        for first in range(len(clusters)):
            for second in range(first + 1, len(clusters)):
                one, other = clusters[first], clusters[second]
                size = max(one[1][2], one[1][3], other[1][2], other[1][3])
                if _box_gap(one[1], other[1]) <= MERGE_GAP * size:
                    clusters[first] = [one[0] + other[0], _union(one[1], other[1])]
                    del clusters[second]
                    merged = True
                    break
            if merged:
                break
    if not clusters:
        return []
    largest = max(area for area, _ in clusters)
    kept = [(area, box) for area, box in clusters
            if area >= MULTI_MIN_SHARE * mask.size and area >= MULTI_RELATIVE * largest]
    return sorted(kept, reverse=True)


def taken_candidates(old_gray: np.ndarray, gray: np.ndarray, background_old: np.ndarray, background_new: np.ndarray,
                     old_ignore: np.ndarray | None) -> list[tuple[int, int, int, int]]:
    objects = _difference(old_gray, background_old, old_ignore)
    now_empty = (_distance(gray, background_new) < PIXEL_THRESHOLD).astype(np.uint8) * 255
    return [box for _, box in thick_blobs(cv2.bitwise_and(objects, now_empty))]


def was_occupied(old_gray: np.ndarray, background: np.ndarray, box: tuple[int, int, int, int]) -> bool:
    x, y, w, h = box
    region = _distance(old_gray, background)[y:y + h, x:x + w]
    return region.size > 0 and float((region >= PIXEL_THRESHOLD).mean()) >= OCCUPIED_SHARE


def main_box(mask: np.ndarray) -> tuple[tuple[int, int, int, int] | None, int]:
    parts = thick_blobs(mask)
    if parts:
        return parts[0][1], len(parts)
    points = cv2.findNonZero(mask)
    return (cv2.boundingRect(points) if points is not None else None), 0


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
        self.last_mask: np.ndarray | None = None
        self.motion_ratio = 0.0
        self.last_box: tuple[int, int, int, int] | None = None
        self.parts = 0
        self.items: list[tuple[int, tuple[int, int, int, int]]] = []
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

    @property
    def waiting_for_motion(self) -> bool:
        return self._waiting_for_motion

    def still_seconds(self, now: float) -> float:
        return 0.0 if self._stable_since is None else now - self._stable_since

    def count_items_now(self) -> int:
        self.items = [] if self.last_mask is None else separate_items(self.last_mask)
        return len(self.items)

    def update(self, image: np.ndarray, now: float, ignore: np.ndarray | None = None) -> Placement | None:
        gray, self._scale = _gray(image, self.work_width)
        hand = _ignore(ignore, gray.shape)
        if self._previous is not None and self._previous.shape == gray.shape:
            self.motion_ratio = _ratio(_difference(gray, self._previous, hand, self._previous_ignore))
        self._previous, self._previous_ignore = gray, hand
        if self._baseline is None or self._baseline.shape != gray.shape:
            return None
        change_mask = _difference(gray, align(self._baseline, gray), hand)
        self.change_ratio = _ratio(change_mask)
        self.last_mask = change_mask
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
        found, self.parts = main_box(change_mask)
        self.items = separate_items(change_mask)
        if found is None:
            return None
        box = tuple(round(value * self._scale) for value in found)
        self.last_box = box
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
        self.last_mask: np.ndarray | None = None
        self.last_box: tuple[int, int, int, int] | None = None
        self.last_before: np.ndarray | None = None
        self.history: deque = deque(maxlen=4)
        self.take_number = 0
        self.parts = 0
        self._previous: np.ndarray | None = None
        self._previous_ignore: np.ndarray | None = None
        self._background: np.ndarray | None = None
        self._stable_gray: np.ndarray | None = None
        self._stable_image: np.ndarray | None = None
        self._stable_ignore: np.ndarray | None = None
        self._stable_ignore_old: np.ndarray | None = None
        self._stable_since: float | None = None
        self._moved = False

    @property
    def ready(self) -> bool:
        return self._background is not None

    @property
    def occupied(self) -> bool:
        return self.occupancy >= self.occupied_min

    @property
    def learning_note(self) -> str:
        if self._background is not None:
            return "spremna"
        if self._previous is None:
            return "još nema slike"
        if self._previous_ignore is not None and self._previous_ignore.any():
            return "ruka je u zoni"
        if self.motion_ratio > self.motion_max:
            return f"pokret u zoni {self.motion_ratio:.1%} (dozvoljeno {self.motion_max:.1%})"
        return "čekam mirovanje"

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
        return self._evaluate(gray, image, hand, scale)

    @property
    def moved(self) -> bool:
        return self._moved

    def evaluate_now(self, image: np.ndarray, ignore: np.ndarray | None = None) -> BasketEvent | None:
        if self._background is None or not self._moved or self._stable_gray is None:
            return None
        gray, scale = _gray(image, self.work_width)
        if gray.shape != self._stable_gray.shape:
            return None
        self._moved = False
        self._stable_since = None
        return self._evaluate(gray, image, _ignore(ignore, gray.shape), scale)

    def _evaluate(self, gray: np.ndarray, image: np.ndarray, hand: np.ndarray | None, scale: float) -> BasketEvent | None:
        if hand is not None and hand.any():
            self._moved = True
            self.last_note = "ruka je u zoni, čekam da je povučete"
            return None
        old_gray, old_image = self._stable_gray, self._stable_image
        mask = self._clean(_difference(gray, align(old_gray, gray), hand, self._stable_ignore))
        change = _ratio(mask)
        self.last_mask = mask
        self._stable_ignore_old = self._stable_ignore
        self._stable_gray, self._stable_image, self._stable_ignore = gray, image.copy(), hand
        background_old = align(self._background, old_gray)
        background_new = align(self._background, gray)
        self.occupancy = _ratio(self._clean(_difference(gray, background_new, hand)))
        if change < self.change_min:
            self.last_note = f"premala promjena {change:.2%}"
            return None
        selected = mask > 0
        old_was_empty = float((_distance(old_gray, background_old)[selected] < PIXEL_THRESHOLD).mean())
        new_is_empty = float((_distance(gray, background_new)[selected] < PIXEL_THRESHOLD).mean())
        self.last_note = f"promjena {change:.2%}, prije prazno {old_was_empty:.0%}, sad prazno {new_is_empty:.0%}"
        if old_was_empty >= EMPTY_SHARE:
            return BasketEvent("added", None, change)
        candidates = taken_candidates(old_gray, gray, background_old, background_new, self._stable_ignore_old)
        source = f"prazno mjesto nađeno ({len(candidates)})"
        max_share = FREED_ITEM_SHARE
        if float((_distance(old_gray, background_old) >= PIXEL_THRESHOLD).mean()) >= WHOLE_ZONE_SHARE:
            max_share = MAX_ITEM_SHARE
        if not candidates:
            candidates = [box for _, box in thick_blobs(mask)]
            source = f"podloga nije vidljiva (puna korpa), najdeblja promjena ({len(candidates)})"
            max_share = MAX_ITEM_SHARE
        found, reasons = None, []
        for box in candidates:
            reason = reject_reason(old_gray, gray, background_old, box, max_share)
            if reason is None:
                found = box
                break
            reasons.append(reason)
        self.parts = len(candidates)
        if found is None:
            self.last_note += f", {source}, odbačeno: {'; '.join(reasons) or 'nema kandidata'}"
            return None
        if reasons:
            self.last_note += f", preskočeno {len(reasons)} ({reasons[0]})"
        self.last_note += f", {source}, uzimam najveće"
        x, y, w, h = found
        padding = 6
        left, top = max(0, round((x - padding) * scale)), max(0, round((y - padding) * scale))
        right, bottom = round((x + w + padding) * scale), round((y + h + padding) * scale)
        self.last_box = (left, top, right - left, bottom - top)
        self.last_before = old_image.copy()
        cv2.rectangle(self.last_before, (left, top), (right, bottom), (255, 170, 60), 2)
        mask_view = cv2.cvtColor(cv2.resize(mask, (image.shape[1], image.shape[0]), interpolation=cv2.INTER_NEAREST), cv2.COLOR_GRAY2BGR)
        cv2.rectangle(mask_view, (left, top), (right, bottom), (255, 170, 60), 2)
        self.take_number += 1
        self.history.appendleft({
            "number": self.take_number, "at": time.monotonic(), "clock": time.strftime("%H:%M:%S"),
            "before": self.last_before, "after": image.copy(), "mask": mask_view, "note": self.last_note,
        })
        return BasketEvent("taken", old_image[top:bottom, left:right].copy(), change)

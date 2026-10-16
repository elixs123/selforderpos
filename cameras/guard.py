import json
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

from hands import load_hand_detector
from reader import CameraReader
from samples import SampleStore
from similarity import Signature, compare, match_threshold, method_name, signature
from watcher import BasketTracker, ZoneWatcher
from zones import crop, load_zones

TIMEOUT_SECONDS = 30
TAKEN_MAX_AGE = 60
TAKEN_WAIT = 12
TAKE_MERGE_SECONDS = 2.5
LOOP_SECONDS = 0.04
CROP_PADDING = 10


@dataclass(frozen=True)
class Outcome:
    number: int
    kind: str
    verdict: str
    barcode: str
    product_code: str | None
    message: str


def zone_of(camera: str) -> str:
    return camera[0]


def item_from(frame: np.ndarray, offset: tuple[int, int], box: tuple[int, int, int, int]) -> np.ndarray:
    x, y, w, h = box
    offset_x, offset_y = offset
    left, top = max(0, offset_x + x - CROP_PADDING), max(0, offset_y + y - CROP_PADDING)
    return frame[top:offset_y + y + h + CROP_PADDING, left:offset_x + x + w + CROP_PADDING].copy()


class CheckoutGuard:
    def __init__(self, readers: dict[str, CameraReader]) -> None:
        self.readers = readers
        self.cameras_a = sorted(name for name in readers if zone_of(name) == "A")
        self.cameras_b = sorted(name for name in readers if zone_of(name) == "B")
        self.zones = load_zones()
        self.trackers = {name: BasketTracker() for name in self.cameras_a}
        self.watchers = {name: ZoneWatcher() for name in self.cameras_b}
        self.store = SampleStore()
        self.hands = load_hand_detector()
        self.hand_shapes: dict[str, list[np.ndarray]] = {name: [] for name in readers}
        self.state = "learning"
        self.message = "Zona A mora biti prazna dok kamera uči pozadinu..."
        self.basket_status = "učim praznu zonu"
        self.last_event_a = "-"
        self.scores = "-"
        self.barcode = ""
        self.product_code: str | None = None
        self.product_name: str | None = None
        self.outcome: Outcome | None = None
        self.debug: dict | None = None
        self.debug_number = 0
        self.debug_folder: Path | None = None
        self._outcome_number = 0
        self._dump_number = 0
        self._last_taken: tuple[list[np.ndarray], float] | None = None
        self._taken_items: list[np.ndarray] = []
        self._taken_at = 0.0
        self._pending_until: float | None = None
        self._armed_at = 0.0
        self._reference_cache: dict[str, Signature] = {}
        self._missing_references: set[str] = set()
        self._lock = threading.RLock()
        self._running = False
        self.events: deque[tuple[int, str, str, str]] = deque(maxlen=300)
        self.event_number = 0
        self.last_problems: list[str] = []
        self.armed_seconds = 0.0

    def log(self, kind: str, text: str) -> None:
        self.event_number += 1
        self.events.append((self.event_number, datetime.now().strftime("%H:%M:%S"), kind, text))

    @property
    def tracker(self) -> BasketTracker:
        return self.trackers[self.cameras_a[0]]

    @property
    def watcher(self) -> ZoneWatcher:
        return self.watchers[self.cameras_b[0]]

    @property
    def zone_a_ready(self) -> bool:
        return bool(self.trackers) and all(tracker.ready for tracker in self.trackers.values())

    @property
    def zone_a_occupied(self) -> bool:
        return any(tracker.occupied for tracker in self.trackers.values())

    @property
    def zone_a_motion(self) -> float:
        return max((tracker.motion_ratio for tracker in self.trackers.values()), default=0.0)

    @property
    def zone_b_armed(self) -> bool:
        return any(watcher.armed for watcher in self.watchers.values())

    @property
    def busy(self) -> bool:
        return self.zone_b_armed or self._pending_until is not None

    def latest(self, name: str) -> np.ndarray | None:
        reader = self.readers.get(name)
        return reader.latest() if reader else None

    def start(self) -> None:
        for reader in self.readers.values():
            reader.start()
        self._running = True
        threading.Thread(target=self._loop, daemon=True).start()

    def stop(self) -> None:
        self._running = False
        for reader in self.readers.values():
            reader.stop()

    def _loop(self) -> None:
        while self._running:
            started = time.monotonic()
            try:
                self.step()
            except Exception as error:
                print(f"Kamere: {error}")
            time.sleep(max(0.0, LOOP_SECONDS - (time.monotonic() - started)))

    def enable_debug(self, folder: Path) -> None:
        self.debug_folder = folder
        folder.mkdir(parents=True, exist_ok=True)
        print(f"Dijagnostika: slike se spremaju u {folder}")

    def _dump(self, event: str, extra: dict | None = None) -> None:
        if self.debug_folder is None:
            return
        self._dump_number += 1
        prefix = self.debug_folder / f"{self._dump_number:03d}-{event}"
        images: dict[str, np.ndarray | None] = {}
        for name in self.readers:
            frame = self.latest(name)
            images[f"{name}-full"] = frame
            if frame is not None:
                images[f"{name}-zone"], _ = crop(frame, self.zones.get(name))
        for name, tracker in self.trackers.items():
            images[f"{name}-mask"] = tracker.last_mask
        for name, watcher in self.watchers.items():
            images[f"{name}-mask"] = watcher.last_mask
        extra = extra or {}
        for key, value in extra.items():
            if isinstance(value, np.ndarray):
                images[key] = value
            elif isinstance(value, list):
                for index, image in enumerate(value):
                    if isinstance(image, np.ndarray):
                        images[f"{key}-{index + 1}"] = image
        for name, image in images.items():
            if image is not None and getattr(image, "size", 0):
                cv2.imwrite(f"{prefix}-{name}.jpg", image)
        info = {
            "time": datetime.now().isoformat(timespec="seconds"),
            "event": event, "state": self.state, "message": self.message,
            "barcode": self.barcode, "product": self.product_name,
            "zone_a": self.basket_status, "last_event_a": self.last_event_a,
            "a": {name: {"occupancy": round(t.occupancy, 4), "motion": round(t.motion_ratio, 4), "note": t.last_note}
                  for name, t in self.trackers.items()},
            "b": {name: {"change": round(w.change_ratio, 4), "motion": round(w.motion_ratio, 4), "armed": w.armed}
                  for name, w in self.watchers.items()},
            "scores": self.scores, "zones": self.zones, "hands": self.hands is not None,
        }
        info.update({key: value for key, value in extra.items() if not isinstance(value, (np.ndarray, list))})
        with open(self.debug_folder / "log.jsonl", "a", encoding="utf-8") as log:
            log.write(json.dumps(info, ensure_ascii=False) + "\n")

    def _set(self, state: str, message: str) -> None:
        if state != self.state or message != self.message:
            self.log(state, message)
        self.state = state
        self.message = message

    def _finish(self, kind: str, verdict: str, message: str) -> None:
        self._outcome_number += 1
        self.outcome = Outcome(self._outcome_number, kind, verdict, self.barcode, self.product_code, message)
        self._set(kind, message)
        self._dump(f"{kind}-{verdict}")

    def scan(self, barcode: str, product_code: str | None, product_name: str | None) -> bool:
        with self._lock:
            self.barcode, self.product_code, self.product_name = barcode, product_code, product_name
            self.log("scan", f"Skenirano {barcode} ({product_name or 'nepoznat artikal'}), šifra {product_code or '-'}")
            if self.busy:
                self.message = "Prvo odložite prethodni artikal u zonu B."
                return False
            now = time.monotonic()
            recent_take = self._last_taken is not None and now - self._last_taken[1] <= TAKEN_MAX_AGE
            if not self.zone_a_ready:
                self._finish("rejected", "not_ready", "Kamera još uči praznu zonu A. Sačekajte trenutak.")
                return False
            if not self.zone_a_occupied and not recent_take:
                self._finish("rejected", "zone_a_empty", "Stavite korpu ili artikle u zonu A.")
                return False
            if not self.cameras_b or any(self.latest(name) is None for name in self.cameras_b):
                self._finish("rejected", "camera_b", "Kamera zone B nema sliku. Pozovite osoblje.")
                return False
            self.scores = "-"
            if recent_take:
                items, taken_at = self._last_taken
                self._last_taken = None
                self._wait_for_zone_b(items, taken_at)
                return True
            self._pending_until = now + TAKEN_WAIT
            self._set("waiting_take", "Čekam da kamera vidi koji je artikal uzet iz zone A...")
            self._dump("scan-waiting-take")
            return True

    def cancel(self) -> None:
        with self._lock:
            for watcher in self.watchers.values():
                watcher.disarm()
            self._pending_until = None
            self._set("ready", "Prekinuto.")

    def approve(self) -> None:
        with self._lock:
            if not self.busy and self.state != "mismatch":
                return
            for watcher in self.watchers.values():
                watcher.disarm()
            self._pending_until = None
            self._finish("accepted", "staff", "Osoblje je odobrilo artikal.")

    def _wait_for_zone_b(self, items: list[np.ndarray], taken_at: float) -> None:
        self._pending_until = None
        self._taken_items = list(items)
        self._taken_at = taken_at
        for index, item in enumerate(items):
            self.store.save("taken", self.barcode, self.product_code, self.product_name, f"A{index + 1}", crop_image=item)
        for name, watcher in self.watchers.items():
            roi, _ = crop(self.latest(name), self.zones.get(name))
            watcher.arm(roi)
        self._armed_at = time.monotonic()
        self._set("waiting_place", f"Odložite artikal u zonu B: {self.product_name or self.barcode}")
        self._dump("scan-armed-b", {"taken-item": items})

    def _judge(self, items: list[np.ndarray], change_ratio: float) -> tuple[str, list[str], float | None, float | None]:
        queries = [signature(item) for item in items]
        taken = [signature(item, rotations=False) for item in self._taken_items if item is not None and item.size]
        score_taken = max((compare(query, other) for query in queries for other in taken), default=None)
        references = self._reference_signatures(self.product_code)
        scored = [(compare(query, reference), reference) for query in queries for reference in references]
        best = max(scored, key=lambda pair: pair[0], default=None)
        score_product = best[0] if best else None
        threshold = match_threshold()
        sizes = sorted(self.store.reference_sizes(self.product_code))
        middle = sizes[len(sizes) // 2] if sizes else 0
        size = f"{change_ratio / middle:.1f}x" if middle > 0 else "-"
        self.scores = (
            f"uzeto->odlozeno: {'-' if score_taken is None else f'{score_taken:.2f}'}   "
            f"skenirano->odlozeno: {'-' if score_product is None else f'{score_product:.2f}'} ({len(references)} ref)   "
            f"velicina: {size}   prag {threshold} ({method_name()})   kamera A: {len(taken)}, B: {len(queries)}"
        )
        self.debug_number += 1
        self.debug = {
            "taken": self._taken_items[0] if self._taken_items else None,
            "placed": items[0] if items else None,
            "reference": best[1].image if best else None,
            "score_taken": score_taken,
            "score_product": score_product,
            "threshold": threshold,
        }
        problems = []
        if score_taken is None:
            problems.append("nije viđeno šta je uzeto iz zone A")
        elif score_taken < threshold:
            problems.append("nije isto što je uzeto iz zone A")
        if score_product is not None and score_product < threshold:
            problems.append("ne liči na skenirani artikal")
        self.last_problems = problems
        self.log("poredjenje", self.scores + ("   PROBLEM: " + ", ".join(problems) if problems else "   OK"))
        if problems:
            return "mismatch", problems, score_taken, score_product
        if score_product is None:
            return "learned", [], score_taken, score_product
        return "ok", [], score_taken, score_product

    def _reference_signatures(self, product_code: str | None) -> list[Signature]:
        result = []
        for path in self.store.reference_paths(product_code, limit=20):
            if path in self._missing_references:
                continue
            if path not in self._reference_cache:
                image = self.store.load_image(path)
                if image is None:
                    self._missing_references.add(path)
                    continue
                self._reference_cache[path] = signature(image, rotations=False)
            result.append(self._reference_cache[path])
        return result

    def _hand_mask(self, name: str, roi: np.ndarray, offset: tuple[int, int]) -> np.ndarray | None:
        if self.hands is None:
            return None
        mask, hulls = self.hands.mask(roi)
        self.hand_shapes[name] = [hull + np.array(offset, dtype=np.int32) for hull in hulls]
        return mask

    def _watch_zone_a(self) -> None:
        now = time.monotonic()
        for name, tracker in self.trackers.items():
            frame = self.latest(name)
            if frame is None:
                continue
            roi, offset = crop(frame, self.zones.get(name))
            event = tracker.update(roi, now, self._hand_mask(name, roi, offset))
            if event is not None:
                self._on_zone_a_event(name, event, now)

    def _on_zone_a_event(self, camera: str, event, now: float) -> None:
        self.last_event_a = f"{camera} {event.kind}: {self.trackers[camera].last_note}"
        self.log(f"zona-{camera}", self.last_event_a)
        self._dump(f"zone-{camera}-{event.kind}", {f"{camera}-item": event.item})
        occupancy = max(tracker.occupancy for tracker in self.trackers.values())
        if event.kind == "empty":
            if self.zone_a_ready:
                self.basket_status = "prazna (pozadina naučena)"
                self._set("empty", "Stavite korpu ili artikle u zonu A.")
            return
        if event.kind == "added":
            self.basket_status = f"ima artikala ({occupancy:.0%})"
            if not self.busy:
                self._set("ready", "Uzmite artikal i skenirajte ga.")
            return
        self.basket_status = f"uzet artikal, ostalo {occupancy:.0%}"
        if self.zone_b_armed and now - self._taken_at <= TAKE_MERGE_SECONDS:
            self._taken_items.append(event.item)
            return
        if self._pending_until is not None:
            self._wait_for_zone_b([event.item], now)
            return
        if self.zone_b_armed:
            return
        if self._last_taken is not None and now - self._last_taken[1] <= TAKE_MERGE_SECONDS:
            self._last_taken[0].append(event.item)
        else:
            self._last_taken = ([event.item], now)
        self._set("taken", "Artikal uzet iz zone A. Skenirajte ga.")

    def _watch_zone_b(self) -> None:
        now = time.monotonic()
        placements = {}
        frames = {}
        for name, watcher in self.watchers.items():
            frame = self.latest(name)
            if frame is None:
                continue
            roi, offset = crop(frame, self.zones.get(name))
            frames[name] = (frame, offset)
            placement = watcher.update(roi, now, self._hand_mask(name, roi, offset))
            if placement is not None:
                placements[name] = placement
        if placements:
            self._on_placed(placements, frames, now)
        elif self.zone_b_armed and now - self._armed_at > TIMEOUT_SECONDS:
            for watcher in self.watchers.values():
                watcher.disarm()
            for name, (frame, _) in frames.items():
                self.store.save("timeout", self.barcode, self.product_code, self.product_name, name, full_image=frame)
            self._finish("timeout", "timeout", "Artikal nije odložen. Pozovite osoblje.")

    def _on_placed(self, placements: dict, frames: dict, now: float) -> None:
        items, change_ratio = [], max(placement.change_ratio for placement in placements.values())
        for name, watcher in self.watchers.items():
            if name not in frames:
                continue
            frame, offset = frames[name]
            placement = placements.get(name)
            if placement is not None:
                items.append((name, item_from(frame, offset, placement.box), placement.change_ratio))
            elif watcher.change_ratio >= watcher.change_min and watcher.last_mask is not None:
                points = cv2.findNonZero(watcher.last_mask)
                if points is not None:
                    roi, _ = crop(frame, self.zones.get(name))
                    factor = roi.shape[1] / watcher.last_mask.shape[1]
                    x, y, w, h = cv2.boundingRect(points)
                    box = tuple(round(value * factor) for value in (x, y, w, h))
                    items.append((name, item_from(frame, offset, box), watcher.change_ratio))
            watcher.disarm()
        crops = [item for _, item, _ in items]
        verdict, problems, score_taken, score_product = self._judge(crops, change_ratio)
        for name, item, ratio in items:
            self.store.save(
                "placed", self.barcode, self.product_code, self.product_name, name,
                crop_image=item, full_image=frames[name][0], change_ratio=ratio,
                verdict=verdict, score_taken=score_taken, score_product=score_product,
            )
        self._dump(f"placed-{verdict}", {
            "B-item": crops, "taken-item": self._taken_items,
            "reference": self.debug["reference"] if self.debug else None,
            "problems": problems, "score_taken": score_taken, "score_product": score_product,
        })
        if verdict == "mismatch":
            for watcher in self.watchers.values():
                watcher.rearm()
            self._armed_at = now
            self._set("mismatch", "Artikal ne odgovara: " + ", ".join(problems) + ". Uklonite ga i odložite skenirani artikal.")
            return
        message = "Artikal prvi put viđen, naučen." if verdict == "learned" else "Artikal odgovara."
        self._finish("accepted", verdict, message)

    def step(self) -> None:
        with self._lock:
            self._watch_zone_a()
            if self._pending_until is not None and time.monotonic() > self._pending_until:
                self._pending_until = None
                self._finish("rejected", "not_taken", "Kamera nije vidjela da je artikal uzet iz zone A. Vratite ga i pokušajte ponovo.")
            self._watch_zone_b()

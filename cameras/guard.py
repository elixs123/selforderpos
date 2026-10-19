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
from watcher import BasketTracker, ZoneWatcher, looks_like_item, main_box, separate_items
from zones import crop, load_zones, zones_changed_at

TIMEOUT_SECONDS = 30
TAKEN_MAX_AGE = 60
TAKEN_WAIT = 12
TAKE_MERGE_SECONDS = 2.5
LOOP_SECONDS = 0.04
HAND_PASS_SECONDS = 0.2
HAND_MAX_AGE = 1.5
CROP_PADDING = 10
MULTIPLE_PROBLEM = "odloženo je više artikala"
MULTIPLE_MESSAGE = "Odložili ste više artikala. Uklonite višak i ostavite samo skenirani artikal."
UNSCANNED_MESSAGE = "Uzeli ste još jedan artikal iz zone A. Skenirajte ga."
NOT_TAKEN_MESSAGE = "Taj artikal nije uzet iz zone A. Ako ste ga već skenirali, ne skenirajte ga ponovo."
PLACED_UNSCANNED_MESSAGE = "U zonu B je odložen artikal koji nije skeniran. Uklonite ga iz zone B pa ga skenirajte."
ZONE_B_QUIET_SECONDS = 2.0
MAX_TAKES = 30


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
        self.references_since = zones_changed_at()
        self.trackers = {name: BasketTracker() for name in self.cameras_a}
        self.watchers = {name: ZoneWatcher() for name in self.cameras_b}
        self.idle_b = {name: BasketTracker() for name in self.cameras_b}
        self._placed_unscanned: dict[str, int] = {}
        self._b_active_at = -1000.0
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
        self._takes: list[tuple[np.ndarray, np.ndarray | None, float, str]] = []
        self._scan_takes: list[tuple[np.ndarray, np.ndarray | None, float, str]] = []
        self.last_taken_index = 0
        self._forgot_at = -1000.0
        self._item_like_cache: dict[int, tuple] = {}
        self._taken_items: list[np.ndarray] = []
        self._taken_befores: list[np.ndarray | None] = []
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
        self.step_ms = 0.0
        self.hands_ms = 0.0
        self.judge_ms = 0.0
        self.zone_a_ms = 0.0
        self.zone_b_ms = 0.0
        self._judging = False
        self._job_id = 0
        self._reference_lock = threading.Lock()
        self._taken_signatures: dict[int, tuple[np.ndarray, Signature]] = {}
        self._seen: dict[str, int] = {}
        self._frames_b: dict[str, tuple[np.ndarray, tuple[int, int]]] = {}
        self._hand_cache: dict[str, tuple[np.ndarray, list[np.ndarray], float]] = {}
        self._hand_lock = threading.Lock()

    def log(self, kind: str, text: str) -> None:
        self.event_number += 1
        self.events.append((self.event_number, datetime.now().strftime("%H:%M:%S"), kind, text))

    @property
    def tracker(self) -> BasketTracker:
        return self.trackers[self.cameras_a[0]]

    @property
    def watcher(self) -> ZoneWatcher:
        return self.watchers[self.cameras_b[0]]

    def _is_live(self, name: str) -> bool:
        reader = self.readers.get(name)
        return reader is not None and reader.status == "uživo"

    @property
    def zone_a_ready(self) -> bool:
        return any(tracker.ready for name, tracker in self.trackers.items() if self._is_live(name))

    def zone_a_waiting_reason(self) -> str:
        parts = []
        for name, tracker in self.trackers.items():
            if not self._is_live(name):
                parts.append(f"{name}: kamera nema sliku ({self.readers[name].status})")
            elif not tracker.ready:
                parts.append(f"{name}: {tracker.learning_note}")
        return "; ".join(parts) or "-"

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
    def unscanned(self) -> int:
        return self.unscanned_taken + self.unscanned_placed

    @property
    def unscanned_taken(self) -> int:
        counts: dict[str, int] = {}
        for take in self._takes:
            if self._item_like(take[0]):
                counts[take[3]] = counts.get(take[3], 0) + 1
        return max(counts.values(), default=0)

    def _expire_takes(self, now: float) -> None:
        self._takes = [take for take in self._takes if now - take[2] <= TAKEN_MAX_AGE or self._item_like(take[0])]

    def _zone_a_active(self) -> bool:
        for name, tracker in self.trackers.items():
            if not self._is_live(name):
                continue
            if tracker.moved or tracker.motion_ratio > tracker.motion_max or self.hand_shapes.get(name):
                return True
        return False

    def _item_like(self, image) -> bool:
        key = id(image)
        cached = self._item_like_cache.get(key)
        if cached is None or cached[0] is not image:
            cached = (image, looks_like_item(image))
            self._item_like_cache[key] = cached
            if len(self._item_like_cache) > 200:
                self._item_like_cache.clear()
        return cached[1]

    @property
    def unscanned_placed(self) -> int:
        return max(self._placed_unscanned.values(), default=0)

    def _unscanned_message(self) -> str:
        return PLACED_UNSCANNED_MESSAGE if self.unscanned_placed else UNSCANNED_MESSAGE

    def forgive_unscanned(self) -> None:
        with self._lock:
            if not self.unscanned:
                return
            self.log("osoblje", f"osoblje je poništilo {self.unscanned} neskeniranih artikala")
            self._takes = []
            self._placed_unscanned = {}
            if not self.busy:
                self._set("ready", "Uzmite artikal i skenirajte ga.")

    def _leftover_takes(self, takes: list, index: int) -> list:
        if not takes:
            return []
        index = min(max(index, 0), len(takes) - 1)
        best = takes[index]
        rest = [take for position, take in enumerate(takes) if position != index]
        used = {best[3]}
        for camera in sorted({take[3] for take in rest} - used):
            same_item = [take for take in rest if take[3] == camera and abs(take[2] - best[2]) <= TAKE_MERGE_SECONDS]
            if same_item:
                rest.remove(min(same_item, key=lambda take: abs(take[2] - best[2])))
        return rest

    def _return_unscanned(self, takes: list) -> None:
        takes = [take for take in takes if self._item_like(take[0])]
        self._takes = (takes + self._takes)[-MAX_TAKES:]
        if self.unscanned:
            self.log("zona-A", f"neskeniranih artikala: {self.unscanned}")
            self._set("taken", self._unscanned_message())

    @property
    def busy(self) -> bool:
        return self.zone_b_armed or self._pending_until is not None or self._judging

    def latest(self, name: str) -> np.ndarray | None:
        reader = self.readers.get(name)
        return reader.latest() if reader else None

    def start(self) -> None:
        for reader in self.readers.values():
            reader.start()
        self._running = True
        threading.Thread(target=self._loop, daemon=True).start()
        if self.hands is not None:
            threading.Thread(target=self._hand_loop, daemon=True).start()

    def stop(self) -> None:
        self._running = False
        for reader in self.readers.values():
            reader.stop()

    def _loop(self) -> None:
        while self._running:
            started = time.monotonic()
            try:
                self.step()
                self.step_ms = self.step_ms * 0.9 + (time.monotonic() - started) * 100
            except Exception as error:
                print(f"Kamere: {error}")
            time.sleep(max(0.0, LOOP_SECONDS - (time.monotonic() - started)))

    def _hand_loop(self) -> None:
        while self._running:
            started = time.monotonic()
            names = list(self.cameras_a) + (list(self.cameras_b) if self.zone_b_armed else [])
            for name in names:
                frame = self.latest(name)
                if frame is None:
                    continue
                roi, offset = crop(frame, self.zones.get(name))
                try:
                    mask, hulls = self.hands.mask(roi)
                except Exception as error:
                    print(f"Ruke: {error}")
                    continue
                shifted = [hull + np.array(offset, dtype=np.int32) for hull in hulls]
                with self._hand_lock:
                    self._hand_cache[name] = (mask, shifted, time.monotonic())
            elapsed = time.monotonic() - started
            self.hands_ms = self.hands_ms * 0.8 + elapsed * 200
            time.sleep(max(0.02, HAND_PASS_SECONDS - elapsed))

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
            was_active = self._zone_a_active()
            self._force_takes(now)
            self._expire_takes(now)
            recent_take = bool(self._takes)
            if not self.zone_a_ready:
                self.log("zona-A", f"nije spremna: {self.zone_a_waiting_reason()}")
                self._finish("rejected", "not_ready", "Kamera još uči praznu zonu A. Sačekajte trenutak.")
                return False
            if not self.zone_a_occupied and not recent_take:
                self._finish("rejected", "zone_a_empty", "Stavite korpu ili artikle u zonu A.")
                return False
            if not recent_take and not was_active and not self._zone_a_active():
                self.log("zona-A", "skenirano bez uzimanja iz zone A (ništa se ne dešava u zoni A)")
                self._finish("rejected", "not_taken", NOT_TAKEN_MESSAGE)
                return False
            if not any(self.latest(name) is not None for name in self.cameras_b):
                self._finish("rejected", "camera_b", "Kamera zone B nema sliku. Pozovite osoblje.")
                return False
            self.scores = "-"
            self._warm_references(product_code)
            if recent_take:
                takes, self._takes = self._takes, []
                self._wait_for_zone_b(takes)
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
            self._job_id += 1
            self._judging = False
            self._set("ready", "Prekinuto.")
            self._return_unscanned(self._scan_takes)
            self._scan_takes = []

    def approve(self) -> None:
        with self._lock:
            if not self.busy and self.state != "mismatch":
                return
            for watcher in self.watchers.values():
                watcher.disarm()
            self._pending_until = None
            self._job_id += 1
            self._judging = False
            self._finish("accepted", "staff", "Osoblje je odobrilo artikal.")
            self._return_unscanned(self._leftover_takes(self._scan_takes, self.last_taken_index))
            self._scan_takes = []

    def _wait_for_zone_b(self, takes: list) -> None:
        self._pending_until = None
        self._scan_takes = list(takes)
        self.last_taken_index = 0
        items = [take[0] for take in takes]
        self._taken_items = list(items)
        self._taken_befores = [take[1] for take in takes]
        self._taken_at = takes[-1][2]
        self._taken_signatures = {}
        self._warm_taken(self._taken_items)
        for index, item in enumerate(items):
            self.store.save("taken", self.barcode, self.product_code, self.product_name, f"A{index + 1}", crop_image=item)
        for name, watcher in self.watchers.items():
            frame = self.latest(name)
            if frame is None:
                continue
            roi, _ = crop(frame, self.zones.get(name))
            watcher.arm(roi)
        self._armed_at = time.monotonic()
        self._set("waiting_place", f"Odložite artikal u zonu B: {self.product_name or self.barcode}")
        self._dump("scan-armed-b", {"taken-item": items})

    def _warm_references(self, product_code: str | None) -> None:
        threading.Thread(target=self._reference_signatures, args=(product_code,), daemon=True).start()

    def _warm_taken(self, items: list[np.ndarray]) -> None:
        def work() -> None:
            for item in items:
                self._taken_signature(item)

        threading.Thread(target=work, daemon=True).start()

    def _taken_signature(self, item: np.ndarray) -> Signature:
        with self._reference_lock:
            cached = self._taken_signatures.get(id(item))
            if cached is not None and cached[0] is item:
                return cached[1]
            result = signature(item, rotations=False)
            self._taken_signatures[id(item)] = (item, result)
            return result

    def _judge(
        self, items: list[np.ndarray], change_ratio: float, taken_items: list[np.ndarray],
        taken_befores: list, product_code: str | None, placed_count: int = 1,
    ) -> tuple[str, list[str], float | None, float | None]:
        threshold = match_threshold()
        taken = [(index, self._taken_signature(item)) for index, item in enumerate(taken_items)
                 if item is not None and item.size]
        references = self._reference_signatures(product_code)

        def score(rotations: bool):
            queries = [signature(item, rotations=rotations) for item in items]
            best_taken = max(((compare(query, other), index) for query in queries for index, other in taken), default=None)
            scored = [(compare(query, reference), reference) for query in queries for reference in references]
            return queries, best_taken, max(scored, key=lambda pair: pair[0], default=None)

        queries, best_taken, best = score(False)
        score_taken = best_taken[0] if best_taken else None
        score_product = best[0] if best else None
        failing = score_taken is None or score_taken < threshold or (score_product is not None and score_product < threshold)
        rotated = False
        if failing and any(query.vectors for query in queries):
            queries, best_taken, best = score(True)
            score_taken = best_taken[0] if best_taken else None
            score_product = best[0] if best else None
            rotated = True
        taken_index = best_taken[1] if best_taken else 0
        self.last_taken_index = taken_index
        sizes = sorted(self.store.reference_sizes(product_code, since=self.references_since))
        old_references = self.store.old_reference_count(product_code, self.references_since)
        old_note = f", {old_references} starih ne računam" if old_references else ""
        middle = sizes[len(sizes) // 2] if sizes else 0
        size = f"{change_ratio / middle:.1f}x" if middle > 0 else "-"
        self.scores = (
            f"uzeto->odlozeno: {'-' if score_taken is None else f'{score_taken:.2f}'}   "
            f"skenirano->odlozeno: {'-' if score_product is None else f'{score_product:.2f}'} ({len(references)} ref{old_note})   "
            f"velicina: {size}   prag {threshold} ({method_name()}{', sa rotacijama' if rotated else ''})   "
            f"kamera A: {len(taken)}, B: {len(queries)}   artikala u zoni B: {placed_count}"
        )
        self.debug_number += 1
        self.debug = {
            "taken": taken_items[taken_index] if taken_items else None,
            "before": taken_befores[taken_index] if taken_index < len(taken_befores) else None,
            "placed": items[0] if items else None,
            "reference": best[1].image if best else None,
            "score_taken": score_taken,
            "score_product": score_product,
            "threshold": threshold,
        }
        problems = []
        if placed_count > 1:
            problems.append(MULTIPLE_PROBLEM)
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
        with self._reference_lock:
            result = []
            for path in self.store.reference_paths(product_code, limit=20, since=self.references_since):
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
        with self._hand_lock:
            cached = self._hand_cache.get(name)
        if cached is None or time.monotonic() - cached[2] > HAND_MAX_AGE or cached[0].shape[:2] != roi.shape[:2]:
            self.hand_shapes[name] = []
            return None
        self.hand_shapes[name] = cached[1]
        return cached[0]

    def _watch_zone_a(self) -> None:
        now = time.monotonic()
        for name, tracker in self.trackers.items():
            number = self.readers[name].frame_number
            if number == self._seen.get(name):
                continue
            frame = self.latest(name)
            if frame is None:
                continue
            self._seen[name] = number
            roi, offset = crop(frame, self.zones.get(name))
            event = tracker.update(roi, now, self._hand_mask(name, roi, offset))
            if event is not None:
                self._on_zone_a_event(name, event, now)

    def _force_takes(self, now: float, source: str | None = None, reason: str = "skeniranje") -> None:
        for name, tracker in self.trackers.items():
            if name == source or not tracker.moved or tracker.motion_ratio > tracker.motion_max * 3:
                continue
            frame = self.latest(name)
            if frame is None:
                continue
            roi, offset = crop(frame, self.zones.get(name))
            hands = self._hand_mask(name, roi, offset)
            if hands is not None and hands.any():
                self.log(f"zona-{name}", f"provjera na zahtjev preskočena: ruka je u zoni ({reason})")
                continue
            event = tracker.evaluate_now(roi, hands)
            if event is not None:
                self.log(f"zona-{name}", f"provjera na zahtjev ({reason}): {event.kind}")
                self._on_zone_a_event(name, event, now, sync=False)

    def _on_zone_a_event(self, camera: str, event, now: float, sync: bool = True) -> None:
        self.last_event_a = f"{camera} {event.kind}: {self.trackers[camera].last_note}"
        self.log(f"zona-{camera}", self.last_event_a)
        before = self.trackers[camera].last_before.copy() if event.kind == "taken" and self.trackers[camera].last_before is not None else None
        self._dump(f"zone-{camera}-{event.kind}", {f"{camera}-item": event.item, f"{camera}-before": before})
        if event.kind == "taken" and event.item is not None:
            height, width = event.item.shape[:2]
            self.log(f"zona-{camera}", f"izrez uzetog artikla {width}x{height} px")
        occupancy = max(tracker.occupancy for tracker in self.trackers.values())
        if event.kind == "empty":
            if self.zone_a_ready:
                self.basket_status = "prazna (pozadina naučena)"
                self._set("empty", "Stavite korpu ili artikle u zonu A.")
            return
        if event.kind == "added":
            self.basket_status = f"ima artikala ({occupancy:.0%})"
            if self._takes and not self.zone_b_armed and now - self._forgot_at > TAKE_MERGE_SECONDS:
                self._forgot_at = now
                self._forget_last_take(camera)
            if not self.busy and not self._takes:
                self._set("ready", "Uzmite artikal i skenirajte ga.")
            return
        self.basket_status = f"uzet artikal, ostalo {occupancy:.0%}"
        extras = [(item, None, now + 0.001 * (position + 1), camera) for position, item in enumerate(getattr(event, "extra", ()))]
        if extras:
            self.log(f"zona-{camera}", f"uzeto {len(extras) + 1} artikala odjednom")
        take = (event.item, before, now, camera)
        if self.zone_b_armed and now - self._taken_at <= TAKE_MERGE_SECONDS and not any(
                item[3] == camera for item in self._scan_takes):
            self._scan_takes.append(take)
            self._taken_items.append(event.item)
            self._taken_befores.append(before)
            self._warm_taken([event.item])
            self._takes.extend(extras)
            return
        if self._pending_until is not None:
            self._wait_for_zone_b([take])
            self._takes.extend(extras)
            if sync:
                self._force_takes(now, source=camera, reason=f"{camera} je vidjela uzimanje")
            return
        if self.zone_b_armed or self._judging:
            self._takes.extend([take] + extras)
            self._takes = self._takes[-MAX_TAKES:]
            self.log(f"zona-{camera}", f"uzimanje dok se čeka zona B, neskeniranih: {self.unscanned}")
            return
        self._takes.extend([take] + extras)
        self._takes = self._takes[-MAX_TAKES:]
        if sync:
            self._force_takes(now, source=camera, reason=f"{camera} je vidjela uzimanje")
        if self.unscanned > 1:
            self.log(f"zona-{camera}", f"{self.unscanned} neskenirana artikla — svaki se mora skenirati")
            self._set("taken", UNSCANNED_MESSAGE)
        else:
            self._set("taken", "Artikal uzet iz zone A. Skenirajte ga.")

    def _forget_last_take(self, camera: str) -> None:
        latest = max(take[2] for take in self._takes)
        kept, removed = [], set()
        for take in sorted(self._takes, key=lambda item: item[2], reverse=True):
            if take[3] not in removed and latest - take[2] <= TAKE_MERGE_SECONDS:
                removed.add(take[3])
                continue
            kept.append(take)
        self._takes = sorted(kept, key=lambda item: item[2])
        self.log(f"zona-{camera}", f"artikal vraćen u zonu A, neskeniranih: {self.unscanned}")
        if self._takes:
            self._set("taken", UNSCANNED_MESSAGE if self.unscanned > 1 else "Artikal uzet iz zone A. Skenirajte ga.")

    def _watch_zone_b(self) -> None:
        now = time.monotonic()
        placements = {}
        for name, watcher in self.watchers.items():
            number = self.readers[name].frame_number
            if number == self._seen.get(name):
                continue
            frame = self.latest(name)
            if frame is None:
                continue
            self._seen[name] = number
            roi, offset = crop(frame, self.zones.get(name))
            self._frames_b[name] = (frame, offset)
            hands = self._hand_mask(name, roi, offset)
            placement = watcher.update(roi, now, hands)
            if placement is not None:
                placements[name] = placement
            if self.zone_b_armed or self._judging or placement is not None:
                self._b_active_at = now
            idle_event = self.idle_b[name].update(roi, now, hands)
            if idle_event is not None:
                self._on_idle_b_event(name, idle_event, now)
        frames = dict(self._frames_b)
        if placements:
            self._on_placed(placements, frames, now)
        elif self.zone_b_armed and now - self._armed_at > TIMEOUT_SECONDS:
            for watcher in self.watchers.values():
                watcher.disarm()
            for name, (frame, _) in frames.items():
                self.store.save("timeout", self.barcode, self.product_code, self.product_name, name, full_image=frame)
            self._finish("timeout", "timeout", "Artikal nije odložen. Pozovite osoblje.")
            self._return_unscanned(self._scan_takes)
            self._scan_takes = []

    def _on_idle_b_event(self, camera: str, event, now: float) -> None:
        if event.kind == "empty":
            if self._placed_unscanned.pop(camera, 0):
                self.log(f"zona-{camera}", "zona B je prazna, neskenirani artikal je uklonjen")
                self._after_unscanned_change()
            return
        if self.zone_b_armed or self._judging or now - self._b_active_at < ZONE_B_QUIET_SECONDS:
            return
        if event.kind == "taken":
            if self._placed_unscanned.get(camera):
                self._placed_unscanned[camera] -= 1
                self.log(f"zona-{camera}", "neskenirani artikal uklonjen iz zone B")
                self._after_unscanned_change()
            return
        mask = self.idle_b[camera].last_mask
        if event.kind != "added" or mask is None or not separate_items(mask):
            return
        self._placed_unscanned[camera] = self._placed_unscanned.get(camera, 0) + 1
        self.log(f"zona-{camera}", f"artikal odložen u zonu B bez skeniranja ({self.idle_b[camera].last_note})")
        self._set("taken", PLACED_UNSCANNED_MESSAGE)

    def _after_unscanned_change(self) -> None:
        if self.busy:
            return
        if self.unscanned:
            self._set("taken", self._unscanned_message())
        else:
            self._set("ready", "Uzmite artikal i skenirajte ga.")

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
                found, watcher.parts = main_box(watcher.last_mask)
                watcher.count_items_now()
                if found is not None:
                    roi, _ = crop(frame, self.zones.get(name))
                    factor = roi.shape[1] / watcher.last_mask.shape[1]
                    box = tuple(round(value * factor) for value in found)
                    watcher.last_box = box
                    items.append((name, item_from(frame, offset, box), watcher.change_ratio))
            watcher.disarm()
        crops = [item for _, item, _ in items]
        counts = {name: len(self.watchers[name].items) for name, _, _ in items}
        placed_count = max(counts.values(), default=1)
        for name, count in counts.items():
            watcher = self.watchers[name]
            if count > 1:
                areas = ", ".join(str(area) for area, _ in watcher.items)
                self.log(f"zona-{name}", f"{count} odvojena artikla u zoni B (površine {areas} px)")
            elif watcher.parts > 1:
                self.log(f"zona-{name}", f"{watcher.parts} promjene u zoni B (pomjereni drugi artikli/sjena) — uzimam najveću")
        self._job_id += 1
        self._judging = True
        self._set("judging", "Provjeravam artikal...")
        snapshot = (list(self._taken_items), list(self._taken_befores), self.product_code)
        threading.Thread(
            target=self._judge_job, args=(self._job_id, items, crops, change_ratio, frames, now, snapshot, placed_count), daemon=True,
        ).start()

    def _judge_job(
        self, job: int, items: list, crops: list, change_ratio: float, frames: dict, now: float, snapshot: tuple,
        placed_count: int = 1,
    ) -> None:
        taken_items, taken_befores, product_code = snapshot
        started = time.monotonic()
        try:
            verdict, problems, score_taken, score_product = self._judge(
                crops, change_ratio, taken_items, taken_befores, product_code, placed_count,
            )
        except Exception as error:
            print(f"Poređenje: {error}")
            verdict, problems, score_taken, score_product = "mismatch", [f"greška u poređenju ({error})"], None, None
        self.judge_ms = (time.monotonic() - started) * 1000
        with self._lock:
            if job != self._job_id:
                return
            self._judging = False
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
                self._armed_at = time.monotonic()
                if MULTIPLE_PROBLEM in problems:
                    self._set("mismatch", MULTIPLE_MESSAGE)
                else:
                    self._set("mismatch", "Artikal ne odgovara: " + ", ".join(problems) + ". Uklonite ga i odložite skenirani artikal.")
                return
            message = "Artikal prvi put viđen, naučen." if verdict == "learned" else "Artikal odgovara."
            self._finish("accepted", verdict, message)
            self._return_unscanned(self._leftover_takes(self._scan_takes, self.last_taken_index))
            self._scan_takes = []

    def step(self) -> None:
        with self._lock:
            started = time.monotonic()
            self._watch_zone_a()
            self.zone_a_ms = self.zone_a_ms * 0.9 + (time.monotonic() - started) * 100
            if self._pending_until is not None and time.monotonic() > self._pending_until:
                self._pending_until = None
                self._finish("rejected", "not_taken", "Kamera nije vidjela da je artikal uzet iz zone A. Vratite ga i pokušajte ponovo.")
            started = time.monotonic()
            self._watch_zone_b()
            self.zone_b_ms = self.zone_b_ms * 0.9 + (time.monotonic() - started) * 100

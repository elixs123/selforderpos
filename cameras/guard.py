import threading
import time
from dataclasses import dataclass

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
LOOP_SECONDS = 0.04


@dataclass(frozen=True)
class Outcome:
    number: int
    kind: str
    verdict: str
    barcode: str
    product_code: str | None
    message: str


class CheckoutGuard:
    def __init__(self, readers: dict[str, CameraReader]) -> None:
        self.readers = readers
        self.zones = load_zones()
        self.watcher = ZoneWatcher()
        self.tracker = BasketTracker()
        self.store = SampleStore()
        self.hands = load_hand_detector()
        self.hand_shapes: dict[str, list[np.ndarray]] = {"A": [], "B": []}
        self.state = "learning"
        self.message = "Zona A mora biti prazna dok kamera uči pozadinu..."
        self.basket_status = "učim praznu zonu"
        self.last_event_a = "-"
        self.scores = "-"
        self.barcode = ""
        self.product_code: str | None = None
        self.product_name: str | None = None
        self.outcome: Outcome | None = None
        self._outcome_number = 0
        self._last_taken: tuple[np.ndarray, float] | None = None
        self._taken_item: np.ndarray | None = None
        self._pending_until: float | None = None
        self._armed_at = 0.0
        self._reference_cache: dict[str, Signature] = {}
        self._missing_references: set[str] = set()
        self._lock = threading.RLock()
        self._running = False

    def latest(self, name: str) -> np.ndarray | None:
        reader = self.readers.get(name)
        return reader.latest() if reader else None

    @property
    def busy(self) -> bool:
        return self.watcher.armed or self._pending_until is not None

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

    def _set(self, state: str, message: str) -> None:
        self.state = state
        self.message = message

    def _finish(self, kind: str, verdict: str, message: str) -> None:
        self._outcome_number += 1
        self.outcome = Outcome(self._outcome_number, kind, verdict, self.barcode, self.product_code, message)
        self._set(kind, message)

    def scan(self, barcode: str, product_code: str | None, product_name: str | None) -> bool:
        with self._lock:
            self.barcode, self.product_code, self.product_name = barcode, product_code, product_name
            if self.busy:
                self.message = "Prvo odložite prethodni artikal u zonu B."
                return False
            now = time.monotonic()
            recent_take = self._last_taken is not None and now - self._last_taken[1] <= TAKEN_MAX_AGE
            if not self.tracker.ready:
                self._finish("rejected", "not_ready", "Kamera još uči praznu zonu A. Sačekajte trenutak.")
                return False
            if not self.tracker.occupied and not recent_take:
                self._finish("rejected", "zone_a_empty", "Stavite korpu ili artikle u zonu A.")
                return False
            if self.latest("B") is None:
                self._finish("rejected", "camera_b", "Kamera B nema sliku. Pozovite osoblje.")
                return False
            self.scores = "-"
            if recent_take:
                item = self._last_taken[0]
                self._last_taken = None
                self._wait_for_zone_b(item)
                return True
            self._pending_until = now + TAKEN_WAIT
            self._set("waiting_take", "Čekam da kamera vidi koji je artikal uzet iz zone A...")
            return True

    def cancel(self) -> None:
        with self._lock:
            self.watcher.disarm()
            self._pending_until = None
            self._set("ready", "Prekinuto.")

    def approve(self) -> None:
        with self._lock:
            if not self.busy and self.state != "mismatch":
                return
            self.watcher.disarm()
            self._pending_until = None
            self._finish("accepted", "staff", "Osoblje je odobrilo artikal.")

    def _wait_for_zone_b(self, item: np.ndarray) -> None:
        self._pending_until = None
        self._taken_item = item
        self.store.save("taken", self.barcode, self.product_code, self.product_name, "A", crop_image=item)
        roi, _ = crop(self.latest("B"), self.zones.get("B"))
        self.watcher.arm(roi)
        self._armed_at = time.monotonic()
        self._set("waiting_place", f"Odložite artikal u zonu B: {self.product_name or self.barcode}")

    def _judge(self, item: np.ndarray, change_ratio: float) -> tuple[str, list[str], float | None, float | None]:
        query = signature(item)
        score_taken = None
        if self._taken_item is not None and self._taken_item.size:
            score_taken = compare(query, signature(self._taken_item, rotations=False))
        references = self._reference_signatures(self.product_code)
        score_product = max((compare(query, reference) for reference in references), default=None)
        threshold = match_threshold()
        sizes = sorted(self.store.reference_sizes(self.product_code))
        middle = sizes[len(sizes) // 2] if sizes else 0
        size = f"{change_ratio / middle:.1f}x" if middle > 0 else "-"
        self.scores = (
            f"uzeto->odlozeno: {'-' if score_taken is None else f'{score_taken:.2f}'}   "
            f"skenirano->odlozeno: {'-' if score_product is None else f'{score_product:.2f}'} ({len(references)} ref)   "
            f"velicina: {size}   prag {threshold} ({method_name()})"
        )
        problems = []
        if score_taken is None:
            problems.append("nije viđeno šta je uzeto iz zone A")
        elif score_taken < threshold:
            problems.append("nije isto što je uzeto iz zone A")
        if score_product is not None and score_product < threshold:
            problems.append("ne liči na skenirani artikal")
        if problems:
            return "mismatch", problems, score_taken, score_product
        if score_product is None:
            return "learned", [], score_taken, score_product
        return "ok", [], score_taken, score_product

    def _reference_signatures(self, product_code: str | None) -> list[Signature]:
        result = []
        for path in self.store.reference_paths(product_code):
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
        frame_a = self.latest("A")
        if frame_a is None:
            return
        roi, offset = crop(frame_a, self.zones.get("A"))
        now = time.monotonic()
        event = self.tracker.update(roi, now, self._hand_mask("A", roi, offset))
        if event is None:
            return
        self.last_event_a = f"{event.kind}: {self.tracker.last_note}"
        if event.kind == "empty":
            self.basket_status = "prazna (pozadina naučena)"
            self._set("empty", "Stavite korpu ili artikle u zonu A.")
            return
        if event.kind == "added":
            self.basket_status = f"ima artikala ({self.tracker.occupancy:.0%})"
            if not self.busy:
                self._set("ready", "Uzmite artikal i skenirajte ga.")
            return
        self.basket_status = f"uzet artikal, ostalo {self.tracker.occupancy:.0%}"
        if self._pending_until is not None:
            self._wait_for_zone_b(event.item)
        elif not self.watcher.armed:
            self._last_taken = (event.item, now)
            self._set("taken", "Artikal uzet iz zone A. Skenirajte ga.")

    def _watch_zone_b(self) -> None:
        frame_b = self.latest("B")
        if frame_b is None:
            return
        roi, (offset_x, offset_y) = crop(frame_b, self.zones.get("B"))
        now = time.monotonic()
        placement = self.watcher.update(roi, now, self._hand_mask("B", roi, (offset_x, offset_y)))
        if placement is not None:
            x, y, w, h = placement.box
            padding = 10
            left, top = max(0, offset_x + x - padding), max(0, offset_y + y - padding)
            item = frame_b[top:offset_y + y + h + padding, left:offset_x + x + w + padding].copy()
            verdict, problems, score_taken, score_product = self._judge(item, placement.change_ratio)
            self.store.save(
                "placed", self.barcode, self.product_code, self.product_name, "B",
                crop_image=item, full_image=frame_b, change_ratio=placement.change_ratio,
                verdict=verdict, score_taken=score_taken, score_product=score_product,
            )
            if verdict == "mismatch":
                self.watcher.rearm()
                self._armed_at = now
                self._set("mismatch", "Artikal ne odgovara: " + ", ".join(problems) + ". Uklonite ga i odložite skenirani artikal.")
                return
            message = "Artikal prvi put viđen, naučen." if verdict == "learned" else "Artikal odgovara."
            self._finish("accepted", verdict, message)
        elif self.watcher.armed and now - self._armed_at > TIMEOUT_SECONDS:
            self.watcher.disarm()
            self.store.save("timeout", self.barcode, self.product_code, self.product_name, "B", full_image=frame_b)
            self._finish("timeout", "timeout", "Artikal nije odložen. Pozovite osoblje.")

    def step(self) -> None:
        with self._lock:
            self._watch_zone_a()
            if self._pending_until is not None and time.monotonic() > self._pending_until:
                self._pending_until = None
                self._finish("rejected", "not_taken", "Kamera nije vidjela da je artikal uzet iz zone A. Vratite ga i pokušajte ponovo.")
            self._watch_zone_b()

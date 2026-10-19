import sys
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "cameras"))

import counter
import guard as guard_module
from guard import MULTIPLE_MESSAGE, CheckoutGuard
from watcher import BasketTracker


def test_iou_and_unmatched():
    first, same, other = np.array([0, 0, 10, 10]), np.array([1, 1, 10, 10]), np.array([50, 50, 60, 60])
    assert counter.iou(first, same) > 0.7
    assert counter.iou(first, other) == 0
    assert len(counter.unmatched([first, other], [same])) == 1


def test_counter_can_be_switched_off(monkeypatch):
    monkeypatch.setenv("CAM_COUNTER", "off")
    assert not counter.enabled()
    monkeypatch.setenv("CAM_COUNT_CAMERAS", "A2, B2")
    assert counter.counting_cameras() == {"A2", "B2"}


@pytest.mark.skipif(not (counter.MODELS_FOLDER / counter.MODEL_FILE).exists(), reason="nema YOLOX modela")
def test_real_model_finds_two_drawn_bottles():
    import cv2

    model = counter.ObjectCounter(counter.MODELS_FOLDER / counter.MODEL_FILE)
    assert model.detect(np.full((300, 300, 3), 230, np.uint8)) == []
    assert model.detect(np.zeros((0, 0, 3), np.uint8)) == []


class FakeCounter:
    def detect(self, image):
        boxes = []
        for x in range(0, image.shape[1] - 1, 4):
            if image[5, x, 2] == 255 and (x == 0 or image[5, x - 4, 2] != 255):
                boxes.append(np.array([x, 0, x + 40, 40], dtype=float))
        return boxes


class ControlledReader:
    def __init__(self) -> None:
        self.settings = SimpleNamespace(name="x", host="10.0.0.1")
        self.status = "uživo"
        self.frame_number = 0
        self.fps = 15.0
        self.frame = np.full((240, 320, 3), 80, dtype=np.uint8)

    def latest(self):
        return self.frame

    def stop(self) -> None:
        pass


def run(guard, readers, seconds):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        for reader in readers.values():
            reader.frame_number += 1
        guard.step()
        time.sleep(0.03)


def test_yolox_catches_two_touching_items_in_zone_b(monkeypatch, tmp_path):
    monkeypatch.setenv("SAMPLES_DIR", str(tmp_path))
    monkeypatch.setattr(guard_module, "get_counter", lambda: FakeCounter())
    readers = {"A": ControlledReader(), "B2": ControlledReader()}
    guard = CheckoutGuard(readers)
    guard.zones = {}
    guard.trackers = {"A": BasketTracker(stable_seconds=0.05)}
    guard._judge = lambda items, ratio, taken, befores, code, placed_count=1: (
        ("mismatch", ["odloženo je više artikala"], 0.9, None) if placed_count > 1 else ("ok", [], 0.9, None))
    for watcher in guard.watchers.values():
        watcher.stable_seconds = 0.15
    run(guard, readers, 0.4)
    guard._takes = [(np.full((40, 40, 3), (40, 90, 200), np.uint8), None, time.monotonic(), "A")]
    assert guard.scan("1001", None, "Test") is True
    frame = np.full((240, 320, 3), 80, dtype=np.uint8)
    frame[0:120, 100:140] = (40, 40, 255)
    frame[0:120, 140:180] = (40, 40, 255)
    frame[5, 140] = (0, 0, 254)
    frame[5, 136] = (0, 0, 254)
    readers["B2"].frame = frame
    end = time.monotonic() + 10
    while guard.state != "mismatch" and time.monotonic() < end:
        run(guard, readers, 0.1)
    assert guard.state == "mismatch"
    assert guard.message == MULTIPLE_MESSAGE


def test_yolox_catches_two_touching_items_taken_from_zone_a(monkeypatch, tmp_path):
    monkeypatch.setenv("SAMPLES_DIR", str(tmp_path))
    monkeypatch.setattr(guard_module, "get_counter", lambda: FakeCounter())
    readers = {"A2": ControlledReader(), "B": ControlledReader()}
    guard = CheckoutGuard(readers)
    guard.zones = {}
    guard.trackers = {"A2": BasketTracker(stable_seconds=0.2)}
    run(guard, readers, 0.5)

    def basket(count):
        image = np.full((240, 320, 3), 80, dtype=np.uint8)
        image[0:120, 20:60] = (40, 40, 255)
        for index in range(count):
            image[0:120, 100 + 40 * index:140 + 40 * index] = (40, 40, 255)
            image[5, 96 + 40 * index] = (0, 0, 254)
        image[5, 60] = (0, 0, 254)
        return image

    def show(frame):
        readers["A2"].frame = np.full((240, 320, 3), 250, dtype=np.uint8)
        run(guard, readers, 0.1)
        readers["A2"].frame = frame
        run(guard, readers, 0.6)

    show(basket(2))
    show(basket(0))
    assert guard._takes
    guard._takes = []
    guard._note_accepted()
    run(guard, readers, 0.4)
    assert guard.alert
    assert guard.unscanned == 1


class CountingCounter:
    def __init__(self):
        self.counts = {}

    def detect(self, image):
        return [np.array([0, 0, 1, 1])] * self.counts.get(int(image[0, 0, 0]), 0)


def test_count_loop_flags_extra_item_after_accept(monkeypatch, tmp_path):
    monkeypatch.setenv("SAMPLES_DIR", str(tmp_path))
    fake = CountingCounter()
    monkeypatch.setattr(guard_module, "get_counter", lambda: fake)
    readers = {"A2": ControlledReader(), "B2": ControlledReader()}
    guard = CheckoutGuard(readers)
    guard.zones = {}
    guard.trackers = {"A2": BasketTracker(stable_seconds=0.05)}
    run(guard, readers, 0.3)
    readers["A2"].frame[0, 0, 0] = 1
    readers["B2"].frame[0, 0, 0] = 2
    fake.counts = {1: 3, 2: 0}
    for _ in range(2):
        guard.count_once()
    assert guard.counting_a and guard.unscanned == 0
    fake.counts = {1: 1, 2: 0}
    for _ in range(2):
        guard.count_once()
    assert guard.unscanned == 2 and guard.alert
    guard._note_accepted()
    assert guard.unscanned == 1
    for _ in range(2):
        guard.count_once()
    assert guard.alert
    assert guard.message.startswith("Uzeli ste još jedan artikal")
    fake.counts = {1: 2, 2: 0}
    for _ in range(2):
        guard.count_once()
    assert guard.unscanned == 0 and not guard.alert

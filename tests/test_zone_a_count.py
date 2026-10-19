import sys
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "cameras"))

from guard import CheckoutGuard
from watcher import BasketTracker

COLORS = [(40, 160, 230), (200, 90, 60), (60, 200, 90), (180, 60, 200)]


def zone(*items) -> np.ndarray:
    image = np.full((240, 320, 3), 80, dtype=np.uint8)
    for index, (x, y) in enumerate(items):
        image[y:y + 50, x:x + 50] = COLORS[index % len(COLORS)]
    return image


class ControlledReader:
    def __init__(self) -> None:
        self.settings = SimpleNamespace(name="x", host="10.0.0.1")
        self.status = "uživo"
        self.frame_number = 0
        self.fps = 15.0
        self.frame = zone()

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


def show(guard, readers, frame):
    readers["A"].frame = np.full((240, 320, 3), 250, dtype=np.uint8)
    run(guard, readers, 0.1)
    readers["A"].frame = frame
    run(guard, readers, 0.6)


def make_guard(monkeypatch, tmp_path, basket):
    monkeypatch.setenv("SAMPLES_DIR", str(tmp_path))
    readers = {"A": ControlledReader(), "B": ControlledReader()}
    guard = CheckoutGuard(readers)
    guard.zones = {}
    guard.trackers = {"A": BasketTracker(stable_seconds=0.2)}
    run(guard, readers, 0.5)
    show(guard, readers, zone(*basket))
    return guard, readers


def sell_one(guard, readers, after, product="P"):
    show(guard, readers, after)
    assert guard._takes, "kamera nije vidjela uzimanje"
    guard._takes = []
    guard.product_code = product
    guard._note_accepted()
    run(guard, readers, 0.4)


def test_one_item_taken_and_scanned_is_fine(monkeypatch, tmp_path):
    guard, readers = make_guard(monkeypatch, tmp_path, [(20, 20), (130, 20), (240, 20)])
    sell_one(guard, readers, zone((20, 20), (130, 20)))
    assert not guard.alert
    assert guard.unscanned == 0
    assert not guard.checking


def test_two_items_in_one_grab_one_scanned_is_caught(monkeypatch, tmp_path):
    guard, readers = make_guard(monkeypatch, tmp_path, [(20, 20), (130, 20), (240, 20)])
    sell_one(guard, readers, zone((20, 20)))
    assert guard.alert
    assert guard.unscanned == 1
    assert guard.state == "taken"


def test_moved_neighbour_is_not_a_second_item(monkeypatch, tmp_path):
    guard, readers = make_guard(monkeypatch, tmp_path, [(20, 20), (130, 20), (240, 150)])
    after = zone((20, 20), (200, 120))
    after[:] = zone()
    after[20:70, 20:70] = COLORS[0]
    after[150:200, 200:250] = COLORS[2]
    sell_one(guard, readers, after)
    assert not guard.alert
    assert guard.unscanned == 0


def test_two_touching_items_are_caught_once_size_is_learned(monkeypatch, tmp_path):
    guard, readers = make_guard(monkeypatch, tmp_path, [(20, 20), (130, 100), (180, 100)])
    guard._sizes = {"P": {"A": [2500 / 76800] * 3}}
    sell_one(guard, readers, zone((20, 20)))
    assert guard.alert
    assert guard.unscanned == 1


def test_size_is_learned_from_normal_sales(monkeypatch, tmp_path):
    guard, readers = make_guard(monkeypatch, tmp_path, [(20, 20), (130, 20), (240, 20)])
    sell_one(guard, readers, zone((20, 20), (130, 20)))
    assert len(guard._sizes["P"]["A"]) == 1
    assert guard._sizes_path.exists()


def circles(*centers) -> np.ndarray:
    import cv2

    image = np.full((240, 320, 3), 80, dtype=np.uint8)
    for index, (x, y) in enumerate(centers):
        cv2.circle(image, (x, y), 28, COLORS[index % len(COLORS)], -1)
    return image


def test_two_touching_round_bottles_are_caught_without_learning(monkeypatch, tmp_path):
    monkeypatch.setenv("SAMPLES_DIR", str(tmp_path))
    readers = {"A": ControlledReader(), "B": ControlledReader()}
    guard = CheckoutGuard(readers)
    guard.zones = {}
    guard.trackers = {"A": BasketTracker(stable_seconds=0.2)}
    run(guard, readers, 0.5)
    show(guard, readers, circles((60, 60), (150, 150), (205, 150)))
    sell_one(guard, readers, circles((60, 60)))
    assert guard.alert
    assert guard.unscanned == 1


def test_one_long_box_is_one_item(monkeypatch, tmp_path):
    guard, readers = make_guard(monkeypatch, tmp_path, [(20, 20)])
    long_box = zone((20, 20))
    long_box[120:170, 100:240] = COLORS[1]
    show(guard, readers, long_box)
    sell_one(guard, readers, zone((20, 20)))
    assert not guard.alert
    assert guard.unscanned == 0


def test_two_identical_items_taken_next_to_a_third_identical_one(monkeypatch, tmp_path):
    monkeypatch.setenv("SAMPLES_DIR", str(tmp_path))
    readers = {"A": ControlledReader(), "B": ControlledReader()}
    guard = CheckoutGuard(readers)
    guard.zones = {}
    guard.trackers = {"A": BasketTracker(stable_seconds=0.2)}
    run(guard, readers, 0.5)

    def same(*items):
        image = np.full((240, 320, 3), 80, dtype=np.uint8)
        for x, y in items:
            image[y:y + 50, x:x + 50] = (60, 200, 90)
            image[y + 10:y + 20, x + 10:x + 40] = (250, 250, 250)
        return image

    show(guard, readers, same((20, 20), (90, 20), (160, 20)))
    sell_one(guard, readers, same((20, 20)))
    assert guard.alert

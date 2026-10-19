import sys
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "cameras"))

from guard import PLACED_UNSCANNED_MESSAGE, CheckoutGuard
from watcher import BasketTracker


def empty_zone() -> np.ndarray:
    return np.full((240, 320, 3), 80, dtype=np.uint8)


def with_items(*boxes) -> np.ndarray:
    image = empty_zone()
    for x, y, w, h in boxes:
        image[y:y + h, x:x + w] = (200, 90, 60)
    return image


class ControlledReader:
    def __init__(self) -> None:
        self.settings = SimpleNamespace(name="x", host="10.0.0.1")
        self.status = "uživo"
        self.frame_number = 0
        self.fps = 15.0
        self.frame = empty_zone()

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


def make_guard(monkeypatch, tmp_path):
    monkeypatch.setenv("SAMPLES_DIR", str(tmp_path))
    readers = {"A": ControlledReader(), "B": ControlledReader()}
    guard = CheckoutGuard(readers)
    guard.zones = {}
    guard.trackers = {name: BasketTracker(stable_seconds=0.05) for name in guard.cameras_a}
    guard.idle_b = {name: BasketTracker(stable_seconds=0.2) for name in guard.cameras_b}
    for watcher in guard.watchers.values():
        watcher.stable_seconds = 0.15
    run(guard, readers, 0.6)
    return guard, readers


def place(readers, frame):
    readers["B"].frame = frame.copy()
    readers["B"].frame[0:200, 0:200] = 250


def test_item_put_in_zone_b_without_scan_blocks_until_removed(monkeypatch, tmp_path):
    guard, readers = make_guard(monkeypatch, tmp_path)
    run(guard, readers, 2.2)
    place(readers, with_items((120, 90, 70, 80)))
    run(guard, readers, 0.2)
    readers["B"].frame = with_items((120, 90, 70, 80))
    run(guard, readers, 1.0)
    assert guard.unscanned == 1
    assert guard.message == PLACED_UNSCANNED_MESSAGE
    place(readers, empty_zone())
    run(guard, readers, 0.2)
    readers["B"].frame = empty_zone()
    run(guard, readers, 1.0)
    assert guard.unscanned == 0


def test_scanned_item_placed_in_zone_b_is_not_counted(monkeypatch, tmp_path):
    guard, readers = make_guard(monkeypatch, tmp_path)
    taken = with_items((120, 90, 70, 80))[80:180, 110:200].copy()
    guard._takes = [(taken, None, time.monotonic(), "A")]
    assert guard.scan("1001", None, "Test") is True
    place(readers, with_items((120, 90, 70, 80)))
    run(guard, readers, 0.2)
    readers["B"].frame = with_items((120, 90, 70, 80))
    run(guard, readers, 4.0)
    assert guard.state != "waiting_place"
    assert guard.unscanned_placed == 0

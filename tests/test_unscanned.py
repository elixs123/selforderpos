import sys
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "cameras"))

from guard import UNSCANNED_MESSAGE, CheckoutGuard
from vision_api import snapshot
from watcher import BasketEvent, BasketTracker


class StillReader:
    def __init__(self) -> None:
        self.settings = SimpleNamespace(name="x", host="10.0.0.1")
        self.status = "uživo"
        self.frame_number = 0
        self.fps = 15.0

    def latest(self):
        return np.full((240, 320, 3), 90, dtype=np.uint8)

    def stop(self) -> None:
        pass


def make_guard(monkeypatch, tmp_path):
    monkeypatch.setenv("SAMPLES_DIR", str(tmp_path))
    readers = {"A": StillReader(), "A2": StillReader(), "B": StillReader()}
    guard = CheckoutGuard(readers)
    guard.zones = {}
    guard.trackers = {name: BasketTracker(stable_seconds=0.05) for name in guard.cameras_a}
    for _ in range(8):
        for reader in readers.values():
            reader.frame_number += 1
        guard.step()
        time.sleep(0.03)
    return guard


def item(value: int) -> np.ndarray:
    return np.full((40, 30, 3), value, dtype=np.uint8)


def take(guard, camera, at, extra=()):
    guard._on_zone_a_event(camera, BasketEvent("taken", item(120), 0.1, extra), at, sync=False)


def accept(guard, index=0):
    guard._judge = lambda *args, **kwargs: (setattr(guard, "last_taken_index", index), ("ok", [], 0.9, None))[1]
    for watcher in guard.watchers.values():
        watcher.disarm()
    guard._judging = True
    guard._job_id += 1
    guard._judge_job(guard._job_id, [], [], 0.1, {}, time.monotonic(), ([], [], None))


def test_same_item_seen_by_two_cameras_is_one(monkeypatch, tmp_path):
    guard = make_guard(monkeypatch, tmp_path)
    take(guard, "A", 100.0)
    take(guard, "A2", 100.4)
    assert guard.unscanned == 1
    assert guard.state == "taken"


def test_two_takes_need_two_scans(monkeypatch, tmp_path):
    guard = make_guard(monkeypatch, tmp_path)
    take(guard, "A", 100.0)
    take(guard, "A2", 100.3)
    take(guard, "A", 110.0)
    assert guard.unscanned == 2
    assert guard.message == UNSCANNED_MESSAGE
    assert guard.scan("1001", None, "Test") is True
    accept(guard, index=0)
    assert guard.outcome.kind == "accepted"
    assert guard.unscanned == 1
    assert guard.state == "taken" and guard.message == UNSCANNED_MESSAGE
    assert guard.scan("1002", None, "Test 2") is True
    accept(guard, index=0)
    assert guard.unscanned == 0
    assert guard.state == "accepted"


def test_two_items_in_one_grab_count_twice(monkeypatch, tmp_path):
    guard = make_guard(monkeypatch, tmp_path)
    take(guard, "A", 100.0, extra=(item(60),))
    assert guard.unscanned == 2


def test_take_while_waiting_for_zone_b_stays_unscanned(monkeypatch, tmp_path):
    guard = make_guard(monkeypatch, tmp_path)
    take(guard, "A", time.monotonic())
    assert guard.scan("1001", None, "Test") is True
    take(guard, "A", time.monotonic() + 5)
    accept(guard, index=0)
    assert guard.unscanned == 1


def test_putting_item_back_removes_the_take(monkeypatch, tmp_path):
    guard = make_guard(monkeypatch, tmp_path)
    take(guard, "A", 100.0)
    take(guard, "A2", 100.3)
    guard._on_zone_a_event("A", BasketEvent("added", None, 0.1), 103.0, sync=False)
    guard._on_zone_a_event("A2", BasketEvent("added", None, 0.1), 103.2, sync=False)
    assert guard.unscanned == 0


def test_putting_back_one_of_two_keeps_one(monkeypatch, tmp_path):
    guard = make_guard(monkeypatch, tmp_path)
    take(guard, "A", 100.0)
    take(guard, "A", 110.0)
    guard._on_zone_a_event("A", BasketEvent("added", None, 0.1), 113.0, sync=False)
    assert guard.unscanned == 1


def test_cancelled_scan_gives_item_back_to_unscanned(monkeypatch, tmp_path):
    guard = make_guard(monkeypatch, tmp_path)
    take(guard, "A", time.monotonic())
    assert guard.scan("1001", None, "Test") is True
    assert guard.unscanned == 0
    guard.cancel()
    assert guard.unscanned == 1


def test_staff_can_forgive_and_api_reports_count(monkeypatch, tmp_path):
    guard = make_guard(monkeypatch, tmp_path)
    take(guard, "A", 100.0)
    take(guard, "A", 110.0)
    assert snapshot(guard, "boot")["unscanned"] == 2
    guard.forgive_unscanned()
    assert guard.unscanned == 0
    assert snapshot(guard, "boot")["unscanned"] == 0

import sys
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "cameras"))

from guard import NOT_TAKEN_MESSAGE, UNSCANNED_MESSAGE, CheckoutGuard
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
    image = np.full((40, 30, 3), value, dtype=np.uint8)
    image[:, :, 0] = 40
    return image


def blank() -> np.ndarray:
    return np.full((40, 30, 3), 170, dtype=np.uint8)


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


def test_extra_regions_in_one_grab_are_only_logged(monkeypatch, tmp_path):
    guard = make_guard(monkeypatch, tmp_path)
    take(guard, "A", 100.0, extra=(item(60),))
    assert guard.unscanned == 1
    assert not guard.alert


def test_many_events_for_one_take_count_as_one(monkeypatch, tmp_path):
    guard = make_guard(monkeypatch, tmp_path)
    for at, camera in ((100.0, "A"), (100.4, "A2"), (101.5, "A"), (103.0, "A2"), (104.2, "A")):
        take(guard, camera, at)
    assert guard.unscanned == 1
    assert not guard.alert
    assert guard.scan("1001", None, "Test") is True
    accept(guard, index=2)
    assert guard.unscanned == 0


def test_alert_only_for_a_real_second_item(monkeypatch, tmp_path):
    guard = make_guard(monkeypatch, tmp_path)
    take(guard, "A", 100.0)
    assert not guard.alert
    take(guard, "A", 120.0)
    assert guard.alert


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


def test_blank_surface_takes_are_not_counted(monkeypatch, tmp_path):
    guard = make_guard(monkeypatch, tmp_path)
    take(guard, "A", 100.0)
    for at in (110.0, 120.0, 130.0):
        guard._on_zone_a_event("A", BasketEvent("taken", blank(), 0.1), at, sync=False)
    assert guard.unscanned == 1


def test_scan_without_any_take_is_rejected_at_once(monkeypatch, tmp_path):
    guard = make_guard(monkeypatch, tmp_path)
    guard.trackers["A"].occupancy = 0.5
    assert guard.scan("1001", None, "Test") is False
    assert guard.outcome.verdict == "not_taken"
    assert guard.message == NOT_TAKEN_MESSAGE
    assert not guard.busy


def test_scan_while_something_moves_in_zone_a_waits_for_the_take(monkeypatch, tmp_path):
    guard = make_guard(monkeypatch, tmp_path)
    guard.trackers["A"].occupancy = 0.5
    guard.trackers["A"]._moved = True
    guard._force_takes = lambda *args, **kwargs: None
    assert guard.scan("1001", None, "Test") is True
    assert guard.state == "waiting_take"


def test_second_scan_of_a_single_take_is_rejected(monkeypatch, tmp_path):
    guard = make_guard(monkeypatch, tmp_path)
    guard.trackers["A"].occupancy = 0.5
    take(guard, "A", time.monotonic())
    assert guard.scan("1001", None, "Test") is True
    accept(guard, index=0)
    assert guard.scan("1001", None, "Test") is False
    assert guard.outcome.verdict == "not_taken"


def test_old_blank_take_cannot_license_a_scan(monkeypatch, tmp_path):
    guard = make_guard(monkeypatch, tmp_path)
    guard.trackers["A"].occupancy = 0.5
    guard._on_zone_a_event("A", BasketEvent("taken", blank(), 0.1), time.monotonic() - 120, sync=False)
    assert guard.scan("1001", None, "Test") is False
    assert guard.outcome.verdict == "not_taken"


def test_blank_leftovers_are_not_kept_after_accept(monkeypatch, tmp_path):
    guard = make_guard(monkeypatch, tmp_path)
    guard.trackers["A"].occupancy = 0.5
    now = time.monotonic()
    take(guard, "A", now)
    guard._on_zone_a_event("A2", BasketEvent("taken", blank(), 0.1), now + 5, sync=False)
    assert guard.scan("1001", None, "Test") is True
    accept(guard, index=0)
    assert guard._takes == []

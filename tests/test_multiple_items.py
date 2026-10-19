import sys
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "cameras"))

from guard import MULTIPLE_MESSAGE, MULTIPLE_PROBLEM, CheckoutGuard
from watcher import BasketTracker, ZoneWatcher, separate_items


def empty_zone() -> np.ndarray:
    return np.full((240, 320, 3), 80, dtype=np.uint8)


def with_items(*boxes: tuple[int, int, int, int]) -> np.ndarray:
    image = empty_zone()
    for x, y, w, h in boxes:
        image[y:y + h, x:x + w] = (200, 90, 60)
    return image


def placed_items(image: np.ndarray) -> int:
    watcher = ZoneWatcher(stable_seconds=0.3)
    watcher.arm(empty_zone())
    for step in range(8):
        watcher.update(image, step * 0.2)
    return len(watcher.items)


def test_one_item_is_one():
    assert placed_items(with_items((120, 90, 70, 80))) == 1


def test_two_separate_items_are_two():
    assert placed_items(with_items((40, 90, 70, 80), (210, 90, 70, 80))) == 2


def test_three_separate_items_are_three():
    assert placed_items(with_items((20, 20, 60, 70), (130, 130, 60, 70), (240, 30, 60, 70))) == 3


def test_item_split_by_thin_gap_stays_one():
    assert placed_items(with_items((120, 60, 70, 40), (120, 104, 70, 50))) == 1


def test_tiny_second_object_is_ignored():
    assert placed_items(with_items((60, 90, 90, 100), (230, 120, 14, 14))) == 1


def test_small_item_next_to_big_item_is_counted():
    assert placed_items(with_items((40, 70, 90, 110), (220, 110, 45, 45))) == 2


def test_noise_blobs_do_not_count():
    image = with_items((120, 90, 70, 80))
    random = np.random.default_rng(3)
    for _ in range(12):
        x, y = int(random.integers(0, 300)), int(random.integers(0, 220))
        image[y:y + 4, x:x + 4] = 140
    assert placed_items(image) == 1


def test_empty_mask_has_no_items():
    assert separate_items(np.zeros((100, 100), np.uint8)) == []


class ControlledReader:
    def __init__(self) -> None:
        self.settings = SimpleNamespace(name="x", host="10.0.0.1")
        self.status = "uživo"
        self.frame_number = 0
        self.frame = empty_zone()

    def latest(self):
        return self.frame

    def stop(self) -> None:
        pass


def run_steps(guard, readers, count, pause=0.03):
    for _ in range(count):
        for reader in readers.values():
            reader.frame_number += 1
        guard.step()
        time.sleep(pause)


def wait_for_judgement(guard, readers, before, limit=150):
    for _ in range(limit):
        run_steps(guard, readers, 1)
        if guard.debug_number > before and not guard._judging and guard.state != "judging":
            return
    raise AssertionError("poređenje nije završeno")


def test_two_items_in_zone_b_are_blocked_with_message_and_second_try_passes(monkeypatch, tmp_path):
    monkeypatch.setenv("SAMPLES_DIR", str(tmp_path))
    readers = {"A": ControlledReader(), "B": ControlledReader(), "B2": ControlledReader()}
    guard = CheckoutGuard(readers)
    guard.zones = {}
    guard.trackers = {name: BasketTracker(stable_seconds=0.05) for name in guard.cameras_a}
    for watcher in guard.watchers.values():
        watcher.stable_seconds = 0.15
    run_steps(guard, readers, 8)
    taken = with_items((120, 90, 70, 80))[80:180, 110:200].copy()
    guard._takes = [(taken, None, 10**9, "A")]
    assert guard.scan("1001", None, "Test") is True
    for name in ("B", "B2"):
        readers[name].frame = with_items((40, 90, 70, 80), (210, 90, 70, 80))
    wait_for_judgement(guard, readers, guard.debug_number)
    assert guard.state == "mismatch"
    assert guard.message == MULTIPLE_MESSAGE
    assert MULTIPLE_PROBLEM in guard.last_problems
    assert "artikala u zoni B: 2" in guard.scores
    before = guard.debug_number
    for name in ("B", "B2"):
        readers[name].frame = with_items((120, 90, 70, 80))
    wait_for_judgement(guard, readers, before)
    assert MULTIPLE_PROBLEM not in guard.last_problems
    assert "artikala u zoni B: 1" in guard.scores


def test_one_camera_seeing_two_is_enough(monkeypatch, tmp_path):
    monkeypatch.setenv("SAMPLES_DIR", str(tmp_path))
    readers = {"A": ControlledReader(), "B": ControlledReader(), "B2": ControlledReader()}
    guard = CheckoutGuard(readers)
    guard.zones = {}
    guard.trackers = {name: BasketTracker(stable_seconds=0.05) for name in guard.cameras_a}
    for watcher in guard.watchers.values():
        watcher.stable_seconds = 0.15
    run_steps(guard, readers, 8)
    guard._takes = [(with_items((120, 90, 70, 80))[80:180, 110:200].copy(), None, 10**9, "A")]
    assert guard.scan("1001", None, "Test") is True
    readers["B"].frame = with_items((120, 90, 70, 80))
    readers["B2"].frame = with_items((40, 90, 70, 80), (210, 90, 70, 80))
    wait_for_judgement(guard, readers, guard.debug_number)
    assert guard.state == "mismatch"
    assert guard.message == MULTIPLE_MESSAGE


def test_item_and_its_shadow_below_it_are_one():
    assert placed_items(with_items((130, 20, 60, 70), (110, 150, 100, 50))) == 1


def test_two_items_side_by_side_with_different_heights_stay_two():
    assert placed_items(with_items((20, 100, 70, 90), (220, 20, 70, 70))) == 2

import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "cameras"))

from guard import CheckoutGuard
from watcher import BasketTracker


class FakeReader:
    def __init__(self, live: bool = True, noisy: bool = False) -> None:
        self.settings = SimpleNamespace(name="x", host="10.0.0.1")
        self.status = "uživo" if live else "nema veze"
        self.live = live
        self.noisy = noisy
        self.frame_number = 0
        self.random = np.random.default_rng(1)

    def latest(self):
        if not self.live:
            return None
        if self.noisy:
            return self.random.integers(0, 255, (240, 320, 3), dtype=np.uint8)
        return np.full((240, 320, 3), 90, dtype=np.uint8)

    def stop(self) -> None:
        pass


def make_guard(monkeypatch, tmp_path, readers):
    monkeypatch.setenv("SAMPLES_DIR", str(tmp_path))
    guard = CheckoutGuard(readers)
    guard.trackers = {name: BasketTracker(stable_seconds=0.05) for name in guard.cameras_a}
    return guard


def run_steps(guard, readers, count=8):
    import time

    for _ in range(count):
        for reader in readers.values():
            reader.frame_number += 1
        guard.step()
        time.sleep(0.03)


def test_dead_second_camera_does_not_block_zone_a(monkeypatch, tmp_path):
    readers = {"A": FakeReader(), "A2": FakeReader(live=False), "B": FakeReader(), "B2": FakeReader()}
    guard = make_guard(monkeypatch, tmp_path, readers)
    run_steps(guard, readers)
    assert guard.zone_a_ready
    assert "A2: kamera nema sliku" in guard.zone_a_waiting_reason()


def test_moving_zone_reports_why_it_is_not_ready(monkeypatch, tmp_path):
    readers = {"A": FakeReader(noisy=True), "B": FakeReader()}
    guard = make_guard(monkeypatch, tmp_path, readers)
    run_steps(guard, readers)
    assert not guard.zone_a_ready
    assert "pokret u zoni" in guard.zone_a_waiting_reason()
    assert guard.scan("1001", None, None) is False
    assert guard.outcome.verdict == "not_ready"
    assert any("nije spremna: A: pokret u zoni" in event[3] for event in guard.events)


def test_scan_works_with_only_one_zone_b_camera(monkeypatch, tmp_path):
    readers = {"A": FakeReader(), "B": FakeReader(), "B2": FakeReader(live=False)}
    guard = make_guard(monkeypatch, tmp_path, readers)
    run_steps(guard, readers)
    guard._takes = [(np.full((40, 40, 3), 120, dtype=np.uint8), None, 10**9)]
    assert guard.scan("1001", None, None) is True
    assert guard.state == "waiting_place"
    assert guard.watchers["B"].armed and not guard.watchers["B2"].armed

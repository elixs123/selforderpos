import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "cameras"))

import tamper
from guard import UNSCANNED_MESSAGE, CheckoutGuard


class StillReader:
    def __init__(self) -> None:
        self.settings = SimpleNamespace(name="x", host="10.0.0.1")
        self.status = "uživo"
        self.frame_number = 0
        self.fps = 15.0
        self.frame = np.random.default_rng(3).integers(0, 255, (240, 320, 3), dtype=np.uint8)

    def latest(self):
        return self.frame

    def stop(self) -> None:
        pass


def make_guard(monkeypatch, tmp_path, clips="da"):
    monkeypatch.setenv("SAMPLES_DIR", str(tmp_path))
    monkeypatch.setenv("CAM_CLIPS", clips)
    readers = {"A2": StillReader(), "B2": StillReader()}
    return CheckoutGuard(readers), readers


def test_alarms_record_clips(monkeypatch, tmp_path):
    guard, _ = make_guard(monkeypatch, tmp_path)
    reasons = []
    guard.clips.record = reasons.append
    guard._set("taken", UNSCANNED_MESSAGE)
    guard._set("taken", UNSCANNED_MESSAGE)
    guard._set("mismatch", "Artikal ne liči na skenirani")
    guard._set("ready", "Uzmite artikal")
    assert reasons == [UNSCANNED_MESSAGE, "Artikal ne liči na skenirani"]


def test_clips_can_be_switched_off(monkeypatch, tmp_path):
    guard, _ = make_guard(monkeypatch, tmp_path, clips="ne")
    assert guard.clips is None
    guard.record_clip("alarm")


def test_covered_camera_is_reported_and_recorded(monkeypatch, tmp_path):
    guard, readers = make_guard(monkeypatch, tmp_path)
    reasons = []
    guard.clips.record = reasons.append
    frames = {name: reader.latest() for name, reader in readers.items()}
    guard.watch_tamper(frames, 0.0)
    covered = dict(frames, B2=np.full((240, 320, 3), 128, np.uint8))
    guard.watch_tamper(covered, 1.0)
    guard.watch_tamper(covered, 1.0 + tamper.PROBLEM_SECONDS)
    assert guard.tamper_problems == {"B2": tamper.COVERED}
    assert reasons == [f"kamera B2 {tamper.COVERED}"]
    guard.watch_tamper(frames, 30.0)
    assert guard.tamper_problems == {}

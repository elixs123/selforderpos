import sys
import time
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "cameras"))

import clips
from clips import ClipRecorder, mosaic, safe_name


def frames(value: int) -> dict:
    return {name: np.full((360, 640, 3), value, np.uint8) for name in ("A", "A2", "B", "B2", "C")}


def test_mosaic_has_all_cameras():
    image = mosaic(frames(100))
    assert image.shape == (2 * clips.TILE[1], 3 * clips.TILE[0], 3)


def test_alarm_writes_clip_with_frames_before_and_after(tmp_path):
    recorder = ClipRecorder(tmp_path)
    for step in range(20):
        recorder.add(frames(step * 10), now=100.0 + step / clips.FPS)
    recorder.record("Niste sve platili", now=110.0)
    recorder.record("drugi alarm odmah poslije", now=111.0)
    for step in range(20, 40):
        recorder.add(frames(step * 5), now=100.0 + step / clips.FPS)
    deadline = time.monotonic() + 5
    while not recorder.saved and time.monotonic() < deadline:
        time.sleep(0.05)
    assert len(recorder.saved) == 1
    path = recorder.saved[0]
    assert path.name.endswith("Niste-sve-platili.mp4")
    video = cv2.VideoCapture(str(path))
    count = int(video.get(cv2.CAP_PROP_FRAME_COUNT))
    video.release()
    assert count >= int((clips.BEFORE_SECONDS + clips.AFTER_SECONDS) * clips.FPS) - 2


def test_old_clips_are_deleted(tmp_path):
    (tmp_path / "2026-01-01").mkdir()
    (tmp_path / "2026-10-20").mkdir()
    ClipRecorder(tmp_path).cleanup(datetime(2026, 10, 26))
    assert not (tmp_path / "2026-01-01").exists()
    assert (tmp_path / "2026-10-20").exists()


def test_safe_name():
    assert safe_name("Liči na drugi artikal (Jamnica)") == "Lici-na-drugi-artikal-Jamnica"

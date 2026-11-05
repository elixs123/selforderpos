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
    (tmp_path / "2026-10-23").mkdir()
    (tmp_path / "2026-10-24").mkdir()
    ClipRecorder(tmp_path).cleanup(datetime(2026, 10, 26))
    assert not (tmp_path / "2026-01-01").exists()
    assert not (tmp_path / "2026-10-23").exists()
    assert (tmp_path / "2026-10-24").exists()


def test_safe_name():
    assert safe_name("Liči na drugi artikal (Jamnica)") == "Lici-na-drugi-artikal-Jamnica"


def test_same_alarm_is_recorded_once_per_minute(tmp_path):
    from clips import REPEAT_SECONDS, ClipRecorder

    recorder = ClipRecorder(tmp_path)
    recorder.record("kamera C2 pomjerena", now=0.0)
    recorder.record("kamera C2 pomjerena", now=20.0)
    recorder.record("Niste sve platili", now=30.0)
    recorder.record("kamera C2 pomjerena", now=REPEAT_SECONDS + 1)
    assert [reason for _, _, reason in recorder._pending] == ["kamera C2 pomjerena", "Niste sve platili", "kamera C2 pomjerena"]


def test_avc1_is_tried_once_then_mp4v(tmp_path, monkeypatch):
    import clips

    tried = []

    class Writer:
        def __init__(self, path, fourcc, fps, size):
            tried.append(fourcc)

        def isOpened(self):
            return tried[-1] != clips.cv2.VideoWriter_fourcc(*"avc1")

    monkeypatch.setattr(clips, "_avc1_works", None)
    monkeypatch.setattr(clips.cv2, "VideoWriter", Writer)
    assert clips.open_writer(tmp_path / "a.mp4", (10, 10))[1] is False
    assert clips.open_writer(tmp_path / "b.mp4", (10, 10))[1] is False
    assert tried.count(clips.cv2.VideoWriter_fourcc(*"avc1")) == 1


def test_without_ffmpeg_clip_stays(tmp_path, monkeypatch):
    import clips

    path = tmp_path / "a.mp4"
    path.write_bytes(b"mp4v")
    monkeypatch.setattr(clips.shutil, "which", lambda name: None)
    assert clips.to_h264(path) is False
    assert path.read_bytes() == b"mp4v"

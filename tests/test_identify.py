import sys
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "cameras"))

import guard as guard_module
from guard import CheckoutGuard


class StillReader:
    def __init__(self) -> None:
        self.settings = SimpleNamespace(name="x", host="10.0.0.1")
        self.status = "uživo"
        self.frame_number = 0
        self.fps = 15.0

    def latest(self):
        return np.full((240, 320, 3), 80, dtype=np.uint8)

    def stop(self) -> None:
        pass


def patched_guard(monkeypatch, tmp_path):
    monkeypatch.setenv("SAMPLES_DIR", str(tmp_path))
    monkeypatch.setenv("CAM_MATCH_THRESHOLD", "0.6")
    guard = CheckoutGuard({"A2": StillReader(), "B2": StillReader()})
    monkeypatch.setattr(guard_module, "signature", lambda image, rotations=False: SimpleNamespace(kind=int(image[0, 0, 0])))
    monkeypatch.setattr(guard_module, "compare", lambda query, other: 0.9 if query.kind == other.kind else 0.2)
    references = {"r1.png": 7, "r2.png": 9}
    monkeypatch.setattr(guard.store, "other_reference_paths",
                        lambda code, limit=60, since="": [("J1", "Jamnica 1,5 l", "r1.png"), ("K1", "Keks", "r2.png")])
    monkeypatch.setattr(guard.store, "load_image", lambda path: np.full((10, 10, 3), references[path], np.uint8))
    return guard


def test_identify_returns_most_similar_product(monkeypatch, tmp_path):
    guard = patched_guard(monkeypatch, tmp_path)
    assert guard.identify(np.full((10, 10, 3), 9, np.uint8)) == ("Keks", 0.9)
    assert guard.identify(np.full((10, 10, 3), 3, np.uint8)) is None


def test_guess_follows_unscanned_take(monkeypatch, tmp_path):
    guard = patched_guard(monkeypatch, tmp_path)
    monkeypatch.setattr(guard, "_item_like", lambda image: True)
    guard._takes = [(np.full((10, 10, 3), 7, np.uint8), None, time.monotonic(), "A2")]
    guard._update_guess()
    deadline = time.monotonic() + 3
    while not guard.unscanned_guess and time.monotonic() < deadline:
        time.sleep(0.01)
    assert guard.unscanned_guess == "Jamnica 1,5 l"
    guard._takes = []
    guard._update_guess()
    assert guard.unscanned_guess == ""

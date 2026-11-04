import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "cameras"))

from capture import CaptureSession

EMPTY = np.full((300, 400, 3), 90, dtype=np.uint8)


def with_item(tint: tuple[int, int, int], left: int = 120) -> np.ndarray:
    frame = EMPTY.copy()
    patch = np.random.default_rng(7).integers(0, 120, (160, 150, 3)).astype(np.uint8) + np.array(tint, dtype=np.uint8)
    frame[70:230, left:left + 150] = patch
    return frame


def tint_embed(image):
    # Strana artikla = boja etikete; isti otisak za istu stranu, drugačiji za drugu.
    return image.reshape(-1, 3).mean(axis=0) - 60


class Scene:
    def __init__(self):
        self.frame = EMPTY
        self.hand = False
        self.saved: list[tuple[str, tuple]] = []
        self.now = 0.0

    def session(self, target=3):
        return CaptureSession(lambda: {"B": self.frame}, lambda image: self.hand, tint_embed,
                              lambda camera, image: self.saved.append((camera, image.shape)), "DONAT", target)

    def show(self, session, frame, seconds=2.0):
        self.frame = frame
        for _ in range(int(seconds / 0.1)):
            self.now += 0.1
            session.step(self.now)


def test_captures_new_sides_and_refuses_the_same_side():
    scene = Scene()
    session = scene.session(target=2)
    scene.show(session, with_item((120, 0, 0)))
    assert session.views == 1 and session.state == "turn"
    assert "Uslikano 1 od 2" in session.message
    assert len(scene.saved) == 1 and min(scene.saved[0][1][:2]) >= 120

    scene.show(session, with_item((120, 0, 0), left=140))
    assert session.views == 1 and "već uslikana" in session.message

    scene.show(session, with_item((0, 0, 120), left=130))
    assert session.views == 2 and session.state == "done"
    assert session.status()["active"] is False


def test_no_picture_while_hand_is_in_zone():
    scene = Scene()
    session = scene.session()
    scene.hand = True
    scene.show(session, with_item((120, 0, 0)))
    assert session.views == 0 and "Sklonite ruku" in session.message
    scene.hand = False
    scene.show(session, with_item((120, 0, 0), left=140))
    assert session.views == 1


def test_guard_stops_sale_logic_while_capturing_and_resumes_when_done(monkeypatch, tmp_path):
    from guard import CheckoutGuard
    from test_guard_alarms import StillReader

    monkeypatch.setenv("SAMPLES_DIR", str(tmp_path))
    monkeypatch.setattr("guard._archive_embed", tint_embed)
    readers = {"A2": StillReader(), "B2": StillReader()}
    guard = CheckoutGuard(readers)
    guard.hands = None
    guard.zones = {}
    readers["B2"].frame = EMPTY
    status = guard.start_capture("3850102", "070864", "DONAT")
    assert status["active"] and status["target"] >= 1
    guard.capture.target = 1
    zone_a_steps = []
    monkeypatch.setattr(guard, "_watch_zone_a", lambda: zone_a_steps.append(1))

    readers["B2"].frame = with_item((120, 0, 0))
    for _ in range(40):
        time.sleep(0.1)
        guard.step()
        if guard.capture is None:
            break
    assert guard.capture is None
    assert zone_a_steps == []
    final = guard.capture_status()
    assert final["state"] == "done" and final["views"] == 1
    assert guard.capture_status() == {"active": False, "message": ""}
    paths = guard.store.reference_paths("070864", limit=10)
    assert len(paths) == 1

    guard.step()
    assert zone_a_steps == [1]

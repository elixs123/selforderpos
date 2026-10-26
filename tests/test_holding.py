import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "cameras"))

import holding
from holding import STILL_PASSES, HeldItemDetector, covered_share, iou, merged

PERSON = np.array([100.0, 100.0, 300.0, 300.0])
STATIC_BOTTLE = np.array([10.0, 10.0, 30.0, 40.0])


class FakeCounter:
    """Vraća unaprijed zadane detekcije za cijelu zonu; pločice ne nalaze ništa dodatno."""

    def __init__(self) -> None:
        self.whole: list = []

    def detections(self, image, min_confidence, skipped):
        if image.shape[:2] == (400, 400):
            return list(self.whole)
        return []


def check(detector, fake, items, person=True):
    fake.whole = ([(0, 0.9, PERSON)] if person else []) + [(39, 0.8, box) for box in items]
    return detector.check("C", np.zeros((400, 400, 3), np.uint8), None)


def test_geometry_helpers():
    assert iou(PERSON, PERSON) == 1.0
    assert covered_share(np.array([150.0, 150.0, 200.0, 200.0]), PERSON) == 1.0
    assert len(merged([PERSON, PERSON + 1, STATIC_BOTTLE])) == 2


def test_item_in_hand_is_found_but_item_on_counter_is_not(monkeypatch):
    fake = FakeCounter()
    monkeypatch.setattr(holding, "get_counter", lambda: fake)
    detector = HeldItemDetector()
    assert not check(detector, fake, [STATIC_BOTTLE], person=False).held
    in_hand = np.array([150.0, 150.0, 190.0, 220.0])
    result = check(detector, fake, [STATIC_BOTTLE, in_hand])
    assert result.held
    assert len(result.held_items) == 1 and np.allclose(result.held_items[0], in_hand)


def test_no_person_means_nothing_is_held(monkeypatch):
    fake = FakeCounter()
    monkeypatch.setattr(holding, "get_counter", lambda: fake)
    assert not check(HeldItemDetector(), fake, [np.array([150.0, 150.0, 190.0, 220.0])], person=False).held


def test_item_lying_still_next_to_person_stops_counting(monkeypatch):
    fake = FakeCounter()
    monkeypatch.setattr(holding, "get_counter", lambda: fake)
    detector = HeldItemDetector()
    lying = np.array([150.0, 150.0, 190.0, 220.0])
    results = [check(detector, fake, [lying]).held for _ in range(STILL_PASSES + 1)]
    assert results[0] and not results[-1]


def test_item_in_hand_is_reported_also_after_another_item_was_accepted(monkeypatch):
    import guard as guard_module
    from guard import CheckoutGuard, HELD_UNSCANNED_MESSAGE, HOLD_SCAN_SECONDS, HOLD_TAKEN_SECONDS

    guard = CheckoutGuard.__new__(CheckoutGuard)
    guard.cameras_c, guard.zones, guard.hold_results = ["C2"], {"C2": object()}, {}
    guard.held_message, guard._held_since, guard._held_seen, guard._held_state = "", None, -1000.0, ""
    guard.latest = lambda name: np.zeros((10, 10, 3), np.uint8)
    guard.holder = type("Holder", (), {"check": lambda self, name, frame, zone: holding.HoldResult(True)})()
    guard.log = lambda *args: None
    clock = [100.0]
    monkeypatch.setattr(guard_module.time, "monotonic", lambda: clock[0])
    guard.state = "accepted"
    guard.hold_once()
    assert guard.held_message == ""
    clock[0] += HOLD_SCAN_SECONDS
    guard.hold_once()
    assert guard.held_message == HELD_UNSCANNED_MESSAGE
    guard.state = "taken"
    guard.hold_once()
    assert guard.held_message == "", "artikal uzet iz zone A kupac smije duže držati dok traži barkod"
    clock[0] += HOLD_TAKEN_SECONDS
    guard.hold_once()
    assert guard.held_message == HELD_UNSCANNED_MESSAGE
    guard.state = "waiting_take"
    guard.hold_once()
    assert guard.held_message == ""


def test_timer_restarts_after_carrying_a_scanned_item(monkeypatch):
    import guard as guard_module
    from guard import CheckoutGuard, HOLD_SCAN_SECONDS

    guard = CheckoutGuard.__new__(CheckoutGuard)
    guard.cameras_c, guard.zones, guard.hold_results = ["C2"], {"C2": object()}, {}
    guard.held_message, guard._held_since, guard._held_seen, guard._held_state = "", None, -1000.0, ""
    guard.latest = lambda name: np.zeros((10, 10, 3), np.uint8)
    seen = [True]
    guard.holder = type("Holder", (), {"check": lambda self, name, frame, zone: holding.HoldResult(seen[0])})()
    guard.log = lambda *args: None
    clock = [100.0]
    monkeypatch.setattr(guard_module.time, "monotonic", lambda: clock[0])
    guard.state = "ready"
    guard.hold_once()
    clock[0] += 1.0
    guard.state, seen[0] = "judging", False
    guard.hold_once()
    clock[0] += 1.0
    guard.state, seen[0] = "accepted", True
    guard.hold_once()
    assert guard.held_message == "", "poslije prihvatanja brojanje kreće ispočetka"
    clock[0] += HOLD_SCAN_SECONDS
    guard.hold_once()
    assert guard.held_message != ""

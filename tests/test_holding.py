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

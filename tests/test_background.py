import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "cameras"))

from guard import CheckoutGuard
from watcher import BasketTracker

EMPTY = np.random.default_rng(1).integers(60, 120, (360, 640, 3), dtype=np.uint8)


def feed(tracker, image, seconds=3.0):
    events, moment = [], 0.0
    while moment < seconds:
        event = tracker.update(image.copy(), moment)
        if event:
            events.append(event.kind)
        moment += 0.1
    return events


def learned():
    tracker = BasketTracker()
    assert feed(tracker, EMPTY) == ["empty"] and tracker.fresh
    return tracker.saved_background()


def test_saved_background_is_reused_without_learning():
    tracker = BasketTracker()
    tracker.load_saved(*learned())
    assert feed(tracker, EMPTY) == ["empty"]
    assert tracker.ready and not tracker.fresh


def test_items_present_at_start_are_reported_as_added():
    with_item = EMPTY.copy()
    with_item[100:260, 200:400] = 230
    tracker = BasketTracker()
    tracker.load_saved(*learned())
    assert feed(tracker, with_item, 4.0) == ["empty", "added"]


def test_other_resolution_learns_again():
    tracker = BasketTracker()
    tracker.load_saved(*learned())
    assert feed(tracker, EMPTY[::2, ::2].copy()) == ["empty"]
    assert tracker.fresh


def test_forget_background():
    tracker = BasketTracker()
    tracker.load_saved(*learned())
    feed(tracker, EMPTY)
    tracker.forget_background()
    assert not tracker.ready


class Watcher:
    last_mask = None


def test_item_already_in_zone_b_is_not_counted_as_new():
    guard = CheckoutGuard.__new__(CheckoutGuard)
    watcher = Watcher()
    watcher.last_mask = np.zeros((100, 300), np.uint8)
    watcher.last_mask[40:90, 20:90] = 255
    guard.watchers = {"B2": watcher}
    new_item, old_item = np.array([40.0, 140.0, 270.0, 330.0]), np.array([520.0, 20.0, 700.0, 330.0])
    kept = guard._arrived_in_change("B2", (360, 846, 3), [new_item, old_item])
    assert len(kept) == 1 and kept[0] is new_item

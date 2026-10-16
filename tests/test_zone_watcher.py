import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "cameras"))

from watcher import ZoneWatcher
from zones import crop, to_pixels


def empty_zone() -> np.ndarray:
    return np.full((240, 320, 3), 80, dtype=np.uint8)


def zone_with_item() -> np.ndarray:
    image = empty_zone()
    image[100:160, 120:200] = 220
    return image


def test_not_armed_never_reports():
    watcher = ZoneWatcher()
    for second in range(5):
        assert watcher.update(zone_with_item(), second) is None


def test_reports_placement_after_item_is_still():
    watcher = ZoneWatcher(stable_seconds=0.5)
    watcher.arm(empty_zone())
    results = [watcher.update(zone_with_item(), step * 0.2) for step in range(6)]
    placements = [result for result in results if result is not None]
    assert len(placements) == 1
    x, y, w, h = placements[0].box
    assert 110 <= x <= 125 and 90 <= y <= 105
    assert not watcher.armed


def test_no_placement_without_change():
    watcher = ZoneWatcher(stable_seconds=0.5)
    watcher.arm(empty_zone())
    for step in range(10):
        assert watcher.update(empty_zone(), step * 0.2) is None
    assert watcher.armed


def test_moving_hand_delays_placement():
    watcher = ZoneWatcher(stable_seconds=0.5)
    watcher.arm(empty_zone())
    for step in range(6):
        moving = empty_zone()
        moving[50:150, step * 40:step * 40 + 60] = 200
        assert watcher.update(moving, step * 0.2) is None


def test_zone_pixels_and_crop():
    frame = np.zeros((100, 200, 3), dtype=np.uint8)
    assert to_pixels((0.5, 0.5, 0.25, 0.5), 200, 100) == (100, 50, 50, 50)
    region, offset = crop(frame, (0.5, 0.5, 0.25, 0.5))
    assert region.shape[:2] == (50, 50)
    assert offset == (100, 50)
    whole, origin = crop(frame, None)
    assert whole.shape[:2] == (100, 200) and origin == (0, 0)


def test_sample_store_saves_images_and_rows(tmp_path):
    from samples import SampleStore

    store = SampleStore(tmp_path)
    store.save("placed", "1001", "A1", "Mlijeko", "B", crop_image=zone_with_item(), full_image=empty_zone(), change_ratio=0.05)
    store.save("scan", "1001", None, None, "A")
    assert store.count() == 2
    assert len(list((tmp_path / "A1").glob("*.jpg"))) == 2


def textured(seed: int, color: tuple[int, int, int]) -> np.ndarray:
    generator = np.random.default_rng(seed)
    image = np.zeros((160, 160, 3), dtype=np.uint8)
    image[:] = color
    noise = generator.integers(0, 60, (160, 160, 1), dtype=np.uint8)
    return np.clip(image.astype(int) + noise, 0, 255).astype(np.uint8)


def test_same_item_is_similar():
    from similarity import classic_similarity

    item = textured(1, (30, 40, 200))
    assert classic_similarity(item, item.copy()) > 0.9


def test_different_items_are_not_similar():
    from similarity import COLOR_THRESHOLD, classic_similarity

    donut = textured(1, (30, 120, 220))
    water = textured(2, (220, 160, 40))
    assert classic_similarity(donut, water) < COLOR_THRESHOLD


def test_ai_ignores_rotation():
    import cv2
    import pytest
    from embedder import MODELS, MODELS_FOLDER, Embedder

    if not (MODELS_FOLDER / MODELS["mobilenet"].filename).exists():
        pytest.skip("AI model nije preuzet")
    embedder = Embedder("mobilenet")
    item = textured(3, (30, 120, 220))
    cv2.putText(item, "PENNY", (10, 90), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 0), 3)
    rotated = cv2.rotate(item, cv2.ROTATE_90_CLOCKWISE)
    target = embedder.embed(rotated)
    assert max(float(vector @ target) for vector in embedder.embed_rotations(item)) > 0.95


def test_changed_box_finds_removed_item():
    from watcher import changed_box

    before = zone_with_item()
    after = empty_zone()
    x, y, w, h = changed_box(before, after)
    assert 100 <= x <= 125 and 85 <= y <= 105
    assert changed_box(after, after.copy()) is None


def test_references_only_from_good_placements(tmp_path):
    from samples import SampleStore

    store = SampleStore(tmp_path)
    store.save("placed", "1001", "A1", "Mlijeko", "B", crop_image=zone_with_item(), verdict="learned")
    store.save("placed", "1001", "A1", "Mlijeko", "B", crop_image=zone_with_item(), verdict="mismatch")
    store.save("taken", "1001", "A1", "Mlijeko", "A", crop_image=zone_with_item())
    assert len(store.references("A1")) == 1
    assert store.references(None) == []


def test_rearm_waits_for_motion_then_reports_again():
    watcher = ZoneWatcher(stable_seconds=0.2)
    watcher.arm(empty_zone())
    wrong = zone_with_item()
    first = [watcher.update(wrong, step * 0.2) for step in range(4)]
    assert any(first)
    watcher.rearm()
    for step in range(4, 10):
        assert watcher.update(wrong, step * 0.2) is None
    moving = empty_zone()
    moving[20:120, 20:120] = 250
    watcher.update(moving, 2.2)
    right = empty_zone()
    right[40:100, 200:280] = 30
    later = [watcher.update(right, 2.4 + step * 0.2) for step in range(4)]
    placements = [result for result in later if result]
    assert len(placements) == 1
    assert placements[0].box[0] >= 190


def basket(items: list[tuple[int, int]]) -> np.ndarray:
    image = empty_zone()
    for x, y in items:
        image[y:y + 40, x:x + 40] = (40, 160, 230)
    return image


def feed(tracker, image, start, count=5, step=0.3):
    events = []
    for index in range(count):
        event = tracker.update(image, start + index * step)
        if event is not None:
            events.append(event)
    return events


def move_hand(tracker, image, at):
    hand = image.copy()
    hand[100:220, 150:300] = 250
    feed(tracker, hand, at, count=1)


def test_basket_tracker_sees_basket_then_taken_item():
    from watcher import BasketTracker

    tracker = BasketTracker(stable_seconds=0.5)
    assert [event.kind for event in feed(tracker, empty_zone(), 0)] == ["empty"]
    assert not tracker.occupied

    full = basket([(40, 40), (200, 150)])
    move_hand(tracker, empty_zone(), 2)
    assert [event.kind for event in feed(tracker, full, 3)] == ["added"]
    assert tracker.occupied

    move_hand(tracker, full, 5)
    events = feed(tracker, basket([(40, 40)]), 6)
    assert [event.kind for event in events] == ["taken"]
    taken = events[0].item
    assert taken.shape[0] >= 40 and taken.shape[1] >= 40
    assert taken.mean() > 100
    assert tracker.occupied


def test_single_item_without_basket():
    from watcher import BasketTracker

    tracker = BasketTracker(stable_seconds=0.5)
    feed(tracker, empty_zone(), 0)
    move_hand(tracker, empty_zone(), 2)
    assert [event.kind for event in feed(tracker, basket([(100, 100)]), 3)] == ["added"]
    move_hand(tracker, basket([(100, 100)]), 5)
    events = feed(tracker, empty_zone(), 6)
    assert [event.kind for event in events] == ["taken"]
    assert events[0].item.mean() > 100
    assert not tracker.occupied


def test_basket_tracker_ignores_still_basket():
    from watcher import BasketTracker

    tracker = BasketTracker(stable_seconds=0.5)
    feed(tracker, empty_zone(), 0)
    full = basket([(40, 40)])
    move_hand(tracker, empty_zone(), 2)
    feed(tracker, full, 3)
    assert feed(tracker, full, 8, count=10) == []


def test_ignored_hand_does_not_block_taking():
    from watcher import BasketTracker

    tracker = BasketTracker(stable_seconds=0.5)
    feed(tracker, empty_zone(), 0)
    full = basket([(40, 40), (200, 150)])
    move_hand(tracker, empty_zone(), 2)
    feed(tracker, full, 3)

    ignore = np.zeros(full.shape[:2], dtype=np.uint8)
    ignore[0:120, 120:320] = 255
    after = basket([(40, 40)])
    after[0:120, 120:320] = 250
    tracker.update(full, 5, ignore)
    moving = after.copy()
    moving[0:120, 120:320] = 10
    tracker.update(moving, 5.1, ignore)
    events = []
    for step in range(5):
        jitter = after.copy()
        jitter[0:120, 120:320] = 250 - step * 40
        event = tracker.update(jitter, 5.5 + step * 0.3, ignore)
        if event is not None:
            events.append(event)
    assert [event.kind for event in events] == ["taken"]


def test_taking_from_basket_reveals_basket_floor():
    from watcher import BasketTracker

    tracker = BasketTracker(stable_seconds=0.5)
    feed(tracker, empty_zone(), 0)

    def with_basket(items):
        image = empty_zone()
        image[20:220, 20:300] = (150, 150, 150)
        for x, y in items:
            image[y:y + 40, x:x + 40] = (40, 160, 230)
        return image

    full = with_basket([(40, 40), (200, 150)])
    move_hand(tracker, empty_zone(), 2)
    assert [event.kind for event in feed(tracker, full, 3)] == ["added"]
    move_hand(tracker, full, 5)
    events = feed(tracker, with_basket([(40, 40)]), 6)
    assert [event.kind for event in events] == ["taken"]
    assert events[0].item.mean() > 100
    move_hand(tracker, with_basket([(40, 40)]), 8)
    assert [event.kind for event in feed(tracker, with_basket([]), 9)] == ["taken"]
    move_hand(tracker, with_basket([]), 11)
    assert [event.kind for event in feed(tracker, empty_zone(), 12)] == ["taken"]


def test_taking_large_single_item():
    from watcher import BasketTracker

    tracker = BasketTracker(stable_seconds=0.5)
    feed(tracker, empty_zone(), 0)
    big = empty_zone()
    big[20:220, 20:280] = (40, 160, 230)
    move_hand(tracker, empty_zone(), 2)
    assert [event.kind for event in feed(tracker, big, 3)] == ["added"]
    move_hand(tracker, big, 5)
    events = feed(tracker, empty_zone(), 6)
    assert [event.kind for event in events] == ["taken"]
    assert events[0].item.shape[0] >= 190

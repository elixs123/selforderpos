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


def test_side_cameras_join_zones_but_do_not_count_placed_items(monkeypatch, tmp_path):
    monkeypatch.setenv("SAMPLES_DIR", str(tmp_path))
    readers = {name: StillReader() for name in ("A2", "A3", "B2", "B3")}
    guard = CheckoutGuard(readers)
    assert guard.cameras_a == ["A2", "A3"] and guard.cameras_b == ["B2", "B3"]
    jobs = []
    guard._judge_job = lambda *args: jobs.append(args)
    monkeypatch.setattr("guard.threading.Thread", lambda target, args, daemon: SimpleNamespace(start=lambda: target(*args)))
    guard.watchers["B2"].items = [(500, (0, 0, 10, 10))]
    guard.watchers["B3"].items = [(300, (0, 0, 10, 10)), (200, (20, 0, 10, 10))]
    frame = readers["B2"].latest()
    placement = SimpleNamespace(change_ratio=0.1, box=(10, 10, 40, 40))
    guard._on_placed({"B2": placement, "B3": placement}, {"B2": (frame, (0, 0)), "B3": (frame, (0, 0))}, 0.0)
    _, items, crops, *_, placed_count = jobs[0]
    assert [name for name, _, _ in items] == ["B2", "B3"] and len(crops) == 2
    assert placed_count == 1


class FakeHands:
    def __init__(self, found):
        self.found = found

    def find(self, image):
        return self.found


class FakeCounter:
    def __init__(self, classes):
        self.classes = classes

    def detections(self, image):
        return [(kind, 0.9, np.zeros(4)) for kind in self.classes]


def test_reference_needs_clean_image_that_looks_like_the_item(monkeypatch, tmp_path):
    guard, readers = make_guard(monkeypatch, tmp_path)
    image = readers["A2"].latest()
    monkeypatch.setattr("guard.get_counter", lambda: FakeCounter([]))
    monkeypatch.setenv("CAM_REFERENCE_MIN", "75")
    assert guard._reference_problem(image, 0.80) == ""
    assert guard._reference_problem(image, 0.70).startswith("slabo liči")
    assert guard._reference_problem(image, None).startswith("slabo liči")
    guard.hands = FakeHands([np.zeros((3, 1, 2), np.int32)])
    assert guard._reference_problem(image, 0.95) == "ruka na slici"
    guard.hands = None
    monkeypatch.setattr("guard.get_counter", lambda: FakeCounter([0]))
    assert guard._reference_problem(image, 0.95) == "osoba na slici"


def test_staff_learning_skips_images_with_hands_or_people(monkeypatch, tmp_path):
    guard, readers = make_guard(monkeypatch, tmp_path)
    monkeypatch.setattr("guard.get_counter", lambda: None)
    marked = []
    guard.store.mark_verified = marked.extend
    guard.last_problems = ["ne liči na skenirani artikal"]
    guard._placed_sample_ids = [1, 2, 3]
    guard._placed_problems = ["", "ruka na slici", "slabo liči na artikal (40%, treba 75%)"]
    guard._waive_taken = True
    guard._learn_verified()
    assert marked == [1, 3]


def test_scan_check_cannot_undo_a_take(monkeypatch, tmp_path):
    guard, readers = make_guard(monkeypatch, tmp_path)
    image = readers["A2"].latest()
    take = (image[:50, :50].copy(), None, 0.0, "A")
    guard._takes = [take]
    added = SimpleNamespace(kind="added", item=None)
    guard.trackers["A2"] = SimpleNamespace(moved=True, motion_ratio=0.0, motion_max=1.0, evaluate_now=lambda roi, hands: added)
    guard._force_takes(1.0, reason="skeniranje")
    assert guard._takes == [take]


def test_new_sale_forgets_previous_unscanned_items(monkeypatch, tmp_path):
    guard, readers = make_guard(monkeypatch, tmp_path)
    guard._takes = [(readers["A2"].latest()[:50, :50].copy(), None, 0.0, "A2")]
    guard._placed_unscanned = {"B2": 1}
    guard._zone_a_ignored = 2
    guard.new_sale()
    assert guard._takes == [] and guard._placed_unscanned == {} and guard._zone_a_ignored == 0
    assert guard.unscanned == 0 and guard.state == "ready"

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "cameras"))

import labels
from guard import SIZE_PROBLEM, CheckoutGuard
from test_guard_alarms import StillReader
from zones import Zone

CODE = "090822"
LEARNED = {"B2": [0.01] * 6, "B3": [0.02] * 6}
NORMAL = {"B2": 0.01, "B3": 0.02}
BIGGER = {"B2": 0.016, "B3": 0.032}


def make_guard(monkeypatch, tmp_path, check="da"):
    monkeypatch.setenv("SAMPLES_DIR", str(tmp_path))
    monkeypatch.setenv("CAM_SIZE_CHECK", check)
    monkeypatch.setattr("guard.get_counter", lambda: None)
    monkeypatch.setattr(labels, "read_crops", lambda crops: [set() for _ in crops])
    guard = CheckoutGuard({"A2": StillReader(), "B2": StillReader(), "B3": StillReader()})
    guard.hands = None
    guard.barcode, guard.product_code, guard.product_name = "387", CODE, "SARAJEVSKI KISELJAK 0.5 PET"
    guard._waive_taken = True
    guard._sizes = {CODE: {name: list(values) for name, values in LEARNED.items()}}
    monkeypatch.setattr(guard, "_judge", lambda *args, **kwargs: ("ok", [], 0.9, 0.9))
    monkeypatch.setattr(guard, "_label_crop_scores", lambda crops, scores, hits: scores)
    return guard


def place(guard, sizes):
    crop = np.full((200, 200, 3), 120, np.uint8)
    guard._placed_sizes = dict(sizes)
    guard._job_id += 1
    guard._judging = True
    frames = {name: (guard.readers[name].latest(), (0, 0)) for name in sizes}
    items = [(name, crop, 0.03) for name in sizes]
    guard._judge_job(guard._job_id, items, [crop] * len(items), 0.03, frames, 0.0, ([], [], CODE), 1)
    return guard.state


def test_measure_only_lets_customer_through_but_does_not_learn(monkeypatch, tmp_path):
    guard = make_guard(monkeypatch, tmp_path, check="ne")
    assert place(guard, BIGGER) == "accepted"
    assert guard._sizes[CODE] == LEARNED


def test_blocks_when_bigger_on_all_cameras(monkeypatch, tmp_path):
    guard = make_guard(monkeypatch, tmp_path)
    assert place(guard, BIGGER) == "mismatch"
    assert SIZE_PROBLEM in guard.message


def test_one_camera_seeing_bigger_is_not_enough(monkeypatch, tmp_path):
    guard = make_guard(monkeypatch, tmp_path)
    assert place(guard, {"B2": 0.03, "B3": 0.02}) == "accepted"


def test_no_check_until_enough_measurements(monkeypatch, tmp_path):
    guard = make_guard(monkeypatch, tmp_path)
    guard._sizes[CODE] = {"B2": [0.01] * 4, "B3": [0.02] * 4}
    assert place(guard, BIGGER) == "accepted"


def test_label_cannot_cancel_size_problem(monkeypatch, tmp_path):
    guard = make_guard(monkeypatch, tmp_path)
    monkeypatch.setattr(labels, "read_crops", lambda crops: [{"KISELJAK"} for _ in crops])
    assert place(guard, BIGGER) == "mismatch"


def test_normal_size_is_learned_and_bigger_is_not(monkeypatch, tmp_path):
    guard = make_guard(monkeypatch, tmp_path)
    assert place(guard, NORMAL) == "accepted"
    assert len(guard._sizes[CODE]["B2"]) == 7
    assert place(guard, BIGGER) == "mismatch"
    assert len(guard._sizes[CODE]["B2"]) == 7


def test_weighed_items_are_not_measured(monkeypatch, tmp_path):
    guard = make_guard(monkeypatch, tmp_path)
    guard._weighed = True
    assert place(guard, BIGGER) == "accepted"
    assert guard._sizes[CODE] == LEARNED


def test_staff_can_teach_a_bigger_size(monkeypatch, tmp_path):
    guard = make_guard(monkeypatch, tmp_path)
    assert place(guard, BIGGER) == "mismatch"
    guard.approve(learn=True)
    assert guard._sizes[CODE]["B2"][-1] == BIGGER["B2"]


def test_size_is_share_of_whole_frame(monkeypatch, tmp_path):
    guard = make_guard(monkeypatch, tmp_path)
    guard.zones["B2"] = Zone((0.0, 0.0, 0.5, 0.5))
    guard.watchers["B2"].items = [(100, (0, 0, 10, 10))]
    guard.watchers["B2"].last_mask = np.zeros((10, 100), np.uint8)
    assert guard._placed_size("B2") == 0.025

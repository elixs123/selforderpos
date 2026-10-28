import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "cameras"))

import labels
from guard import TAKEN_PROBLEM, CheckoutGuard
from test_guard_alarms import FakeHands, StillReader

PRODUCTS = {"090822": {"SARAJEVSKI", "KISELJAK", "VRELO", "PARK"}, "070864": {"DONAT", "OCASKASLATINA"}}


def test_ocr_mistakes_still_match_the_product_name():
    assert labels.normalize("SARAJEVSKI KISELJAK 0.5 PET") == ["SARAJEVSKI", "KISELJAK"]
    assert labels.similar("KISELAK", "KISELJAK") and labels.similar("KISEUAK", "KISELJAK")
    assert labels.similar("SLATINA", "OCASKASLATINA")
    assert not labels.similar("DONAT", "KISELJAK")


def test_label_confirms_scanned_or_reveals_other_product():
    assert labels.check({"KISELAK", "PARK"}, "090822", PRODUCTS) == ("match", "KISELAK", None)
    assert labels.check({"OCASKASLATINA"}, "090822", PRODUCTS) == ("other", "OCASKASLATINA", "070864")
    assert labels.check(set(), "090822", PRODUCTS)[0] == "unknown"
    assert labels.check({"NESTO"}, "090822", PRODUCTS)[0] == "unknown"


def test_words_shared_by_several_products_do_not_decide():
    products = {"1": {"JAMNICA", "LIMUN"}, "2": {"JAMNICA", "GREJP"}}
    assert labels.check({"JAMNICA"}, "1", products)[0] == "unknown"
    assert labels.check({"GREJP"}, "1", products) == ("other", "GREJP", "2")


def make_guard(monkeypatch, tmp_path):
    monkeypatch.setenv("SAMPLES_DIR", str(tmp_path))
    monkeypatch.setattr("guard.get_counter", lambda: None)
    guard = CheckoutGuard({"A2": StillReader(), "B2": StillReader()})
    guard.product_name = "SARAJEVSKI KISELJAK 0.5 PET"
    image = np.zeros((10, 10, 3), np.uint8)
    for code, name in (("070864", "DONAT MG 0.5L"),):
        guard.store.save("placed", "1", code, name, "B", crop_image=image, verdict="learned", label_text="OCASKASLATINA")
    return guard


def test_label_overrides_lookalike_and_hand_only_take(monkeypatch, tmp_path):
    guard = make_guard(monkeypatch, tmp_path)
    guard.hands = FakeHands([np.zeros((3, 1, 2), np.int32)])
    problems = ["liči na drugi artikal (DONAT MG 0.5L)", TAKEN_PROBLEM]
    hand = np.zeros((200, 200, 3), np.uint8)
    verdict, left, hits = guard._apply_label("mismatch", problems, None, [{"KISELAK"}, set()], "090822", [hand])
    assert (verdict, left, hits) == ("learned", [], [True, False])


def test_label_of_other_product_is_refused(monkeypatch, tmp_path):
    guard = make_guard(monkeypatch, tmp_path)
    verdict, problems, _ = guard._apply_label("ok", [], 0.9, [{"OCASKASLATINA"}], "090822")
    assert verdict == "mismatch" and problems == ["na etiketi piše OCASKASLATINA (DONAT MG 0.5L)"]


def test_nothing_read_changes_nothing(monkeypatch, tmp_path):
    guard = make_guard(monkeypatch, tmp_path)
    assert guard._apply_label("mismatch", ["ne liči na skenirani artikal"], 0.5, [set()], "090822")[:2] == (
        "mismatch", ["ne liči na skenirani artikal"])

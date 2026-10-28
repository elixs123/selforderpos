import os
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "cameras"))

from PySide6.QtWidgets import QApplication

import labels
from guard import CheckoutGuard
from samples import SampleStore
from screens.report_view import report_advice, report_lines
from test_guard_alarms import StillReader

APP = QApplication.instance() or QApplication([])
IMAGE = np.full((20, 20, 3), 100, np.uint8)


def test_events_are_counted_per_day(tmp_path):
    store = SampleStore(tmp_path)
    store.count_event("mismatch", "2026-10-28")
    store.count_event("mismatch", "2026-10-28")
    store.count_event("accepted:ok", "2026-10-28")
    store.count_event("accepted:ok", "2026-10-29")
    assert store.events_on("2026-10-28") == {"mismatch": 2, "accepted:ok": 1}


def test_report_text_and_advice():
    events = {"accepted:ok": 6, "mismatch": 4, "staff_call": 1, "novo": 2}
    lines = report_lines(events)
    assert lines[0] == "Artikal prihvaćen: 6" and "Kupac pozvao osoblje: 1" in lines and "novo: 2" in lines
    assert "40%" in report_advice(events) and "mnogo" in report_advice(events)
    assert report_advice({}) == ""


def test_staff_sees_and_deletes_item_images(tmp_path):
    store = SampleStore(tmp_path)
    good = store.save("placed", "1", "090822", "Kiseljak", "B3", crop_image=IMAGE, verdict="ok", quality=0.9)
    hand = store.save("placed", "1", "090822", "Kiseljak", "B2", crop_image=IMAGE, verdict="learned", quality=0.8)
    store.save("placed", "1", "090822", "Kiseljak", "B", crop_image=IMAGE, verdict="mismatch")
    assert store.reference_products() == [{"code": "090822", "name": "Kiseljak", "count": 2}]
    assert [image["id"] for image in store.reference_images("090822")] == [hand, good]
    assert store.crop_bytes(good)[:2] == b"\xff\xd8"
    assert store.delete_sample(hand) and not store.delete_sample(hand)
    assert store.reference_products()[0]["count"] == 1


def test_catalog_ignores_words_shared_by_many_articles():
    names = [(str(code), f"JAMNICA VODA {flavour}") for code, flavour in enumerate(["LIMUN", "GREJP", "JABUKA", "BRESKVA"])]
    names.append(("9", "DONAT MG 0.5L ROGASKA"))
    index = labels.CatalogIndex(names)
    assert index.other_product({"JAMNICA"}, "SARAJEVSKI KISELJAK") is None
    assert index.other_product({"ROGASKA"}, "SARAJEVSKI KISELJAK") == ("ROGASKA", "DONAT MG 0.5L ROGASKA")
    assert index.other_product({"KISELJAK"}, "SARAJEVSKI KISELJAK") is None


def make_guard(monkeypatch, tmp_path):
    monkeypatch.setenv("SAMPLES_DIR", str(tmp_path))
    monkeypatch.setattr("guard.get_counter", lambda: None)
    guard = CheckoutGuard({"A2": StillReader(), "B2": StillReader()})
    guard.catalog = SimpleNamespace(names=lambda: [("090844", "JAMNICA PRO SPORT GREJP-LIMUN"), ("090835", "VODA SENSATION LIMETA KIWANO")])
    guard.product_name = "VODA SENSATION LIMETA KIWANO"
    return guard


def test_new_item_with_label_of_another_article_is_not_learned(monkeypatch, tmp_path):
    guard = make_guard(monkeypatch, tmp_path)
    verdict, problems, _ = guard._apply_label("learned", [], None, [{"GREJP"}], "090835")
    assert verdict == "mismatch" and problems == ["na etiketi piše GREJP (JAMNICA PRO SPORT GREJP-LIMUN)"]


def test_new_item_is_still_learned_when_label_does_not_point_elsewhere(monkeypatch, tmp_path):
    guard = make_guard(monkeypatch, tmp_path)
    assert guard._apply_label("learned", [], None, [{"OBAVI", "TIJELO"}], "090835")[:2] == ("learned", [])
    assert guard._apply_label("learned", [], None, [set()], "090835")[:2] == ("learned", [])


def test_references_view_lists_products(monkeypatch, tmp_path):
    from screens.references_view import ReferencesView

    guard = SimpleNamespace(reference_products=lambda: [{"code": "1", "name": "Kiseljak", "count": 3}])
    view = ReferencesView(lambda: guard)
    shown = []
    monkeypatch.setattr(view, "_load", lambda job: view._show_loaded(job(guard)) or shown.append(True))
    view.begin()
    assert shown and view.rows.count() == 2 and "Kiseljak" in view.rows.itemAt(0).widget().text()

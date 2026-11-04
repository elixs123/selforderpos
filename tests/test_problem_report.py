import sys
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "cameras"))

from archive import ImageArchive
from problem_report import problem_articles, report_html
from samples import SampleStore

TODAY = date(2026, 11, 4)


def count(store, kind, code, name, times=1, day="2026-11-04"):
    for _ in range(times):
        store.count_product_event(kind, code, name, "38" + code, day)


def test_worst_articles_first_and_good_ones_left_out(tmp_path):
    store = SampleStore(tmp_path)
    count(store, "accepted:ok", "1", "KISELJAK", 20)
    count(store, "mismatch", "1", "KISELJAK", 2)
    count(store, "accepted:ok", "2", "DONAT", 3)
    count(store, "mismatch", "2", "DONAT", 3)
    count(store, "rejected:not_taken", "2", "DONAT", 1)
    count(store, "accepted:ok", "3", "JAMNICA", 10)
    count(store, "mismatch", "4", "STARO", 5, day="2026-10-01")

    rows = problem_articles(store, None, days=7, today=TODAY)
    assert [row["code"] for row in rows] == ["2", "1"]
    donat = rows[0]
    assert donat["problems"] == 4 and donat["good"] == 3
    assert donat["zone_a"] == {"kamera nije vidjela da je uzet iz zone A": 1}
    assert donat["barcode"] == "382"


def test_report_has_article_picture_and_advice(tmp_path, monkeypatch):
    monkeypatch.setenv("CAM_ARCHIVE_PER_ARTICLE", "50")
    store = SampleStore(tmp_path)
    archive = ImageArchive(tmp_path / "archive", None, background=False)
    source = tmp_path / "crop.jpg"
    cv2.imwrite(str(source), np.random.default_rng(1).integers(0, 255, (200, 160, 3), dtype=np.uint8))
    archive.add(source, "2", "382", "DONAT", "B", "placed", "ok", 0.9)
    archive.process_pending()
    count(store, "mismatch", "2", "DONAT <0.5L>", 2)

    text = report_html(store, archive, days=7, today=TODAY)
    assert "DONAT &lt;0.5L&gt;" in text
    assert "data:image/jpeg;base64," in text
    assert "uslikati sa svih strana (u arhivi 1 slika)" in text
    assert "2× odbijen u zoni B" in text


def test_empty_report(tmp_path):
    assert "nema artikala sa problemima" in report_html(SampleStore(tmp_path), None, today=TODAY)


def test_guard_counts_outcomes_per_article_but_not_system_rejections(monkeypatch, tmp_path):
    from guard import CheckoutGuard
    from test_guard_alarms import StillReader

    monkeypatch.setenv("SAMPLES_DIR", str(tmp_path))
    guard = CheckoutGuard({"A2": StillReader(), "B2": StillReader()})
    guard.barcode, guard.product_code, guard.product_name = "3850102", "079643", "MLIJEKO"
    guard._finish("rejected", "zone_a_empty", "Stavite korpu")
    guard._finish("rejected", "not_taken", "Taj artikal nije uzet")
    guard._finish("accepted", "ok", "Artikal odgovara.")
    events = guard.store.product_events_since("2000-01-01")
    assert events["079643"]["kinds"] == {"rejected:not_taken": 1, "accepted:ok": 1}
    assert "MLIJEKO" in guard.problem_report(7)

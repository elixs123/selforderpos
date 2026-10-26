import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QPushButton

from cart import Cart
from fiscal import FiscalResult
from screens.receipt import ReceiptScreen
from screens.staff import StaffScreen

APP = QApplication.instance() or QApplication([])


def wait_until(condition, seconds: float = 3.0) -> None:
    deadline = time.monotonic() + seconds
    while not condition() and time.monotonic() < deadline:
        APP.processEvents()
        time.sleep(0.01)


def test_failed_fiscal_can_be_retried():
    results = [FiscalResult(False, "printer nije dostupan"), FiscalResult(True, "<RacunOdgovor/>", "84366")]
    calls = []

    def job():
        calls.append(1)
        return results[len(calls) - 1]

    screen = ReceiptScreen(Cart())
    screen.begin("card", "2026-000001", job)
    wait_until(lambda: not screen.retry_button.isHidden())
    assert len(calls) == 1
    assert not screen.timer.isActive()

    screen.retry_button.click()
    wait_until(screen.timer.isActive)
    assert len(calls) == 2
    assert screen.retry_button.isHidden()
    screen.timer.stop()


def test_staff_lists_unprinted_and_removes_after_success():
    screen = StaffScreen(Cart())
    unprinted = [
        {"number": "2026-000001", "created_at": "2026-10-26T12:00:00", "total": 6.07},
        {"number": "2026-000002", "created_at": "2026-10-26T12:05:00", "total": 1.79},
    ]
    requested = []
    screen.reprint_requested.connect(requested.append)
    screen.begin(unprinted=unprinted)
    assert not screen.unprinted_title.isHidden()
    assert screen.unprinted_rows.count() == 2

    button = screen.unprinted_rows.itemAt(0).widget().findChild(QPushButton)
    button.click()
    assert requested == ["2026-000001"]
    assert not button.isEnabled()
    screen.reprint_done.emit("2026-000001", FiscalResult(False, "printer nije dostupan"))
    assert len(screen.unprinted) == 2
    screen.reprint_done.emit("2026-000001", FiscalResult(True, "<RacunOdgovor/>", "84366"))
    assert [receipt["number"] for receipt in screen.unprinted] == ["2026-000002"]


def test_staff_hides_unprinted_when_none():
    screen = StaffScreen(Cart())
    screen.begin()
    assert screen.unprinted_title.isHidden()

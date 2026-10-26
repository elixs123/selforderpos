import os
import sqlite3
from datetime import date, timedelta

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QPushButton

from cart import Cart
from catalog import Product
from receipts import ReceiptStore
from screens.receipts_view import ReceiptsView
from screens.settings import SettingsScreen
from settings import Settings

APP = QApplication.instance() or QApplication([])
MILK = Product("A1", "1001", "Mlijeko 1 l", 1.79)


def filled_cart() -> Cart:
    cart = Cart()
    cart.add(MILK, 2)
    return cart


def move_to_yesterday(store: ReceiptStore, number: str) -> None:
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    with sqlite3.connect(store.path) as connection:
        connection.execute("UPDATE receipts SET created_at = ? || substr(created_at, 11) WHERE number = ?", (yesterday, number))


def test_receipts_on_returns_one_day_newest_first(tmp_path):
    store = ReceiptStore(tmp_path / "kasa.db")
    old = store.save(filled_cart(), "card")
    first = store.save(filled_cart(), "card")
    second = store.save(filled_cart(), "qr")
    move_to_yesterday(store, old)
    assert [row["number"] for row in store.receipts_on(date.today())] == [second, first]
    assert [row["number"] for row in store.receipts_on(date.today() - timedelta(days=1))] == [old]


def test_view_lists_days_and_shows_items(tmp_path):
    store = ReceiptStore(tmp_path / "kasa.db")
    old = store.save(filled_cart(), "card")
    today = store.save(filled_cart(), "card")
    store.mark_fiscal(today, False, "printer nije dostupan")
    move_to_yesterday(store, old)

    view = ReceiptsView(store)
    view.begin()
    assert view.rows.count() == 2
    assert "1 račun ·" in view.summary.text() and "3,58 KM" in view.summary.text()
    assert "1 bez fiskalnog" in view.summary.text()
    assert not view.next_button.isEnabled()

    view.rows.itemAt(0).widget().click()
    assert view.pages.currentWidget() is view.detail_page
    assert view.detail_rows.count() == 2
    assert "3,58" in view.detail_total.text()

    view._move(-1)
    assert view.rows.count() == 2
    assert old in view.rows.itemAt(0).widget().text()
    view._move(-1)
    assert "Nema računa" in view.rows.itemAt(0).widget().text()


def test_settings_opens_receipts(tmp_path):
    screen = SettingsScreen(Settings(), ReceiptStore(tmp_path / "kasa.db"))
    [button for button in screen.findChildren(QPushButton) if button.text() == "Pregledaj prethodne račune"][0].click()
    assert screen.pages.currentWidget() is screen.receipts_page
    screen.receipts_page.closed.emit()
    assert screen.pages.currentWidget() is screen.form_page

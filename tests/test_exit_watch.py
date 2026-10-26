import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QWidget

import app as app_module
from cart import Cart
from catalog import Product
from receipts import ReceiptStore
from screens.unpaid import UnpaidScreen

APP = QApplication.instance() or QApplication([])
MILK = Product("A1", "1001", "Mlijeko 1 l", 1.79)


def paid_receipt(store: ReceiptStore) -> str:
    cart = Cart()
    cart.add(MILK)
    number = store.save(cart, "card")
    store.mark_fiscal(number, True, "", "84366")
    return number


def fake_window(tmp_path, clock):
    store = ReceiptStore(tmp_path / "kasa.db")
    number = paid_receipt(store)
    screens = SimpleNamespace(widget=None)
    screens.currentWidget = lambda: screens.widget
    screens.setCurrentWidget = lambda widget: setattr(screens, "widget", widget)
    window = SimpleNamespace(
        store=store, screens=screens, cart=Cart(), unpaid=UnpaidScreen(), welcome=QWidget(), receipt=QWidget(),
        guard=SimpleNamespace(unscanned=0, unscanned_guess=""),
        exit_watch={"number": number, "since": clock[0], "blocked": False, "guess": ""},
    )
    screens.setCurrentWidget(window.receipt)
    return window, number


def check(window):
    app_module.MainWindow.check_exit(window)


def test_unpaid_item_after_payment_blocks_gate_and_shows_item(tmp_path, monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(app_module.time, "monotonic", lambda: clock[0])
    window, number = fake_window(tmp_path, clock)
    check(window)
    assert window.screens.currentWidget() is window.receipt

    window.guard.unscanned, window.guard.unscanned_guess = 1, "Jamnica 1,5 l"
    check(window)
    assert window.screens.currentWidget() is window.unpaid
    assert "Jamnica" in window.unpaid.item_label.text()
    allowed, reason = window.store.claim_for_gate("84366")
    assert not allowed and "niste sve platili" in reason and "Jamnica" in reason


def test_returning_the_item_unblocks_gate(tmp_path, monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(app_module.time, "monotonic", lambda: clock[0])
    window, number = fake_window(tmp_path, clock)
    window.guard.unscanned = 1
    check(window)
    assert window.unpaid.item_label.text() == "Uzeli ste artikal koji nije plaćen."
    window.guard.unscanned = 0
    check(window)
    assert window.exit_watch is None
    assert window.screens.currentWidget() is window.welcome
    assert window.store.claim_for_gate("84366")[0]


def test_item_scanned_in_new_sale_keeps_old_receipt_blocked(tmp_path, monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(app_module.time, "monotonic", lambda: clock[0])
    window, number = fake_window(tmp_path, clock)
    window.guard.unscanned = 1
    check(window)
    window.cart.add(Product("J1", "2002", "Jamnica 1,5 l", 1.20))
    window.guard.unscanned = 0
    check(window)
    assert window.exit_watch is None
    assert not window.store.claim_for_gate("84366")[0]


def test_watch_ends_after_gate_or_timeout(tmp_path, monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(app_module.time, "monotonic", lambda: clock[0])
    window, number = fake_window(tmp_path, clock)
    assert window.store.claim_for_gate("84366")[0]
    check(window)
    assert window.exit_watch is None

    window, number = fake_window(tmp_path / "drugi", clock)
    clock[0] += app_module.EXIT_WATCH_SECONDS + 1
    window.guard.unscanned = 1
    check(window)
    assert window.exit_watch is None
    assert window.screens.currentWidget() is window.receipt

import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QWidget

import app as app_module
from cart import Cart
from catalog import Product
from screens.idle import IdleOverlay
from settings import Settings

APP = QApplication.instance() or QApplication([])


def fake_window(clock, items: int = 1):
    parent = QWidget()
    parent.resize(400, 600)
    cart = Cart()
    for index in range(items):
        cart.add(Product(f"A{index}", str(index), "Mlijeko", 1.79))
    screens = SimpleNamespace(widget=None)
    screens.currentWidget = lambda: screens.widget
    screens.setCurrentWidget = lambda widget: setattr(screens, "widget", widget)
    window = SimpleNamespace(
        settings=Settings(idle_seconds=120), screens=screens, cart=cart, guard=None, parent=parent,
        scan=QWidget(), drop=SimpleNamespace(waiting=False), payment=QWidget(), welcome=QWidget(), card=QWidget(),
        idle_overlay=IdleOverlay(parent), last_activity=clock[0], cancelled=[],
    )
    window.mark_activity = lambda: setattr(window, "last_activity", clock[0])

    def cancel_shopping():
        window.cancelled.append(True)
        window.cart.clear()
        screens.setCurrentWidget(window.welcome)

    window.cancel_shopping = cancel_shopping
    screens.setCurrentWidget(window.scan)
    return window


def check(window):
    app_module.MainWindow.check_idle(window)


def test_asks_then_cancels_abandoned_cart(monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(app_module.time, "monotonic", lambda: clock[0])
    window = fake_window(clock)
    clock[0] += 119
    check(window)
    assert window.idle_overlay.isHidden()
    clock[0] += 1
    check(window)
    assert not window.idle_overlay.isHidden()
    assert "30 s" in window.idle_overlay.countdown.text()
    clock[0] += app_module.IDLE_COUNTDOWN_SECONDS
    check(window)
    assert window.cancelled == [True]
    assert window.screens.currentWidget() is window.welcome
    assert window.idle_overlay.isHidden()


def test_customer_who_answers_keeps_cart(monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(app_module.time, "monotonic", lambda: clock[0])
    window = fake_window(clock)
    window.idle_overlay.stay.connect(window.mark_activity)
    clock[0] += 125
    check(window)
    assert not window.idle_overlay.isHidden()
    window.idle_overlay._on_stay()
    clock[0] += 60
    check(window)
    assert window.idle_overlay.isHidden()
    assert window.cancelled == [] and window.cart.item_count == 1


def test_empty_cart_returns_home_without_asking(monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(app_module.time, "monotonic", lambda: clock[0])
    window = fake_window(clock, items=0)
    clock[0] += 120
    check(window)
    assert window.cancelled == [True]
    assert window.idle_overlay.isHidden()


def test_card_payment_and_busy_cameras_are_never_interrupted(monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(app_module.time, "monotonic", lambda: clock[0])
    window = fake_window(clock)
    window.screens.setCurrentWidget(window.card)
    clock[0] += 1000
    check(window)
    assert window.cancelled == []

    window = fake_window(clock)
    window.guard = SimpleNamespace(busy=True)
    clock[0] += 1000
    check(window)
    assert window.cancelled == [] and window.idle_overlay.isHidden()


def test_activity_filter_marks_touch_and_keys():
    from PySide6.QtCore import QEvent

    from screens.idle import ActivityFilter

    seen = []
    activity = ActivityFilter(lambda: seen.append(1))
    assert activity.eventFilter(None, QEvent(QEvent.Type.KeyPress)) is False
    activity.eventFilter(None, QEvent(QEvent.Type.Paint))
    assert seen == [1]

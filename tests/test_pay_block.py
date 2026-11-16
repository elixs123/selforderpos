import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from cart import Cart
from catalog import Product
from screens.scan import ScanScreen, pay_enabled, payment_block_reason

APP = QApplication.instance() or QApplication([])
MILK = Product("A1", "1001", "Mlijeko 1 l", 1.79)


def guard(**values):
    base = dict(state="ready", unscanned=0, zone_a_left=0, checking=False, held_message="", alert=False, message="")
    return SimpleNamespace(**{**base, **values})


def test_reason_names_what_blocks_payment():
    assert payment_block_reason(guard()) == ""
    assert "zoni A" in payment_block_reason(guard(zone_a_left=1))
    assert "neskeniran" in payment_block_reason(guard(unscanned=1))
    assert "provjerava" in payment_block_reason(guard(checking=True))
    assert payment_block_reason(guard(held_message="Artikal je u ruci.")) == "Artikal je u ruci."


def test_pay_stays_green_and_explains_items_left_in_zone_a():
    screen = ScanScreen(Cart())
    screen.guard = guard(zone_a_left=1)
    screen.cart.add(MILK)
    screen._refresh()
    paid = []
    screen.pay_requested.connect(lambda: paid.append(True))
    assert screen.pay_button.isEnabled()
    screen.pay_button.click()
    assert not paid
    assert screen.alert.title.text() == "Prije plaćanja" and "zoni A" in screen.alert.text.text()
    screen.guard = guard()
    screen.pay_button.click()
    assert paid


def test_pay_grey_only_without_items_or_when_camera_server_is_down():
    assert not pay_enabled(guard(), has_items=False)
    assert pay_enabled(guard(zone_a_left=2), has_items=True)
    assert not pay_enabled(guard(state="offline"), has_items=True)
    assert pay_enabled(guard(state="offline"), has_items=True, allow_without_cameras=True)

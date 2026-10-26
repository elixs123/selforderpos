import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from cart import Cart
from screens.payment import PaymentScreen
from screens.terminal import PaymentWaitScreen
from settings import Settings

APP = QApplication.instance() or QApplication([])


def test_qr_option_hidden_without_demo():
    screen = PaymentScreen(Cart())
    screen.begin(demo=False)
    assert screen.qr_option.isHidden()
    screen.begin(demo=True)
    assert not screen.qr_option.isHidden()


def test_qr_simulation_does_not_pay_without_demo():
    screen = PaymentWaitScreen(Cart(), "qr")
    paid = []
    screen.paid.connect(paid.append)
    screen.begin(Settings(demo_payments=False))
    assert screen.simulate_button.isHidden()
    screen.simulate_button.click()
    assert paid == []


def test_qr_simulation_pays_in_demo():
    screen = PaymentWaitScreen(Cart(), "qr")
    paid = []
    screen.paid.connect(paid.append)
    screen.begin(Settings(demo_payments=True))
    assert not screen.simulate_button.isHidden()
    screen.simulate_button.click()
    assert paid == [{}]

import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLineEdit, QPushButton, QWidget

import app as app_module
from cart import Cart
from catalog import AGE_RESTRICTED_CATEGORIES, Product
from screens.age_warning import TOP_BAR, AgeWarning
from styles import px

APP = QApplication.instance() or QApplication([])

BEER = Product("B1", "2001", "Pivo 0,5 l", 2.0, category="PEN.25.34.")
MILK = Product("A1", "1001", "Mlijeko 1 l", 1.79, category="PEN.25.09.")


def window():
    parent = QWidget()
    parent.resize(820, 1360)
    screens = SimpleNamespace(widget=None)
    screens.currentWidget = lambda: screens.widget
    fake = SimpleNamespace(
        screens=screens, scan=object(), drop=object(), payment=object(), card=object(), qr=object(), receipt=object(),
        welcome=object(), cart=Cart(), scanned_age_restricted=False, age_warning=AgeWarning(parent), parent=parent,
    )
    parent.show()
    return fake


def update(fake, screen):
    fake.screens.widget = screen
    app_module.MainWindow.update_age_warning(fake)
    return fake.age_warning.isVisible()


def test_categories_match_request():
    assert AGE_RESTRICTED_CATEGORIES == {"PEN.25.121.", "PEN.25.47.", "PEN.25.46.", "PEN.25.34."}
    assert BEER.age_restricted and not MILK.age_restricted
    assert not Product("A", "1", "Bez kategorije", 1.0).age_restricted


def test_hidden_without_alcohol():
    fake = window()
    fake.cart.add(MILK)
    fake.cart.add(Product("C1", "3001", "Cigarete", 5.0, category="PEN.25.73."))
    assert not update(fake, fake.scan)


def test_shown_from_scan_while_item_waits_for_placing():
    fake = window()
    fake.scanned_age_restricted = True
    assert update(fake, fake.drop)


def test_stays_while_in_cart_and_goes_when_removed():
    fake = window()
    fake.cart.add(BEER)
    for screen in (fake.scan, fake.drop, fake.card, fake.qr):
        assert update(fake, screen)
    assert not update(fake, fake.payment)
    fake.cart.remove(BEER.code)
    assert not update(fake, fake.scan)


def test_hidden_after_payment_and_on_welcome():
    fake = window()
    fake.cart.add(BEER)
    assert not update(fake, fake.receipt)
    assert not update(fake, fake.welcome)


def test_sits_in_top_bar_inside_window():
    fake = window()
    fake.cart.add(BEER)
    update(fake, fake.scan)
    box = fake.age_warning.geometry()
    assert 0 < box.left() and box.right() < fake.parent.width()
    assert box.top() >= 0 and box.bottom() <= px(TOP_BAR)


def test_does_not_block_clicks_or_scanner():
    parent = QWidget()
    parent.resize(820, 1360)
    button = QPushButton("Dugme", parent)
    scanner = QLineEdit(parent)
    scanner.move(0, 0)
    warning = AgeWarning(parent)
    parent.show()
    scanner.setFocus()
    warning.set_visible_on_top(True)
    button.setGeometry(warning.geometry())
    warning.raise_()
    clicks = []
    button.clicked.connect(lambda: clicks.append(True))
    assert warning.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    assert warning.focusPolicy() == Qt.FocusPolicy.NoFocus
    target = parent.childAt(warning.geometry().center())
    assert target is button

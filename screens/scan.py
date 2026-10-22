import time

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from cart import Cart
from catalog import find_by_barcode
from database import DatabaseError
from formatting import format_amount, item_count_text
from screens.components import AlertPopup, GuideSteps, StepBar, TopBar
from styles import (
    BACKGROUND,
    BORDER,
    DARK_RED,
    FONT,
    GREEN,
    ICON_ALERT,
    ICON_ARROW,
    ICON_CHECK,
    ICON_HAND,
    ICON_SCANNER,
    LIGHT_GREEN,
    LIGHT_RED,
    MUTED_TEXT,
    RED,
    TEXT,
    WARNING_BACKGROUND,
    WARNING_TEXT,
    icon,
    px,
)


ALERT_SECONDS = 4.0


class ScanScreen(QWidget):
    pay_requested = Signal()
    staff_requested = Signal()
    place_requested = Signal(object, int)
    quit_requested = Signal()

    def __init__(self, cart: Cart) -> None:
        super().__init__()
        self.cart = cart
        self.guard = None
        self.guide_state = ""
        self._alert_until = 0.0
        self.guide_timer = QTimer(self)
        self.guide_timer.setInterval(200)
        self.guide_timer.timeout.connect(self._update_guide)
        self.setObjectName("root")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"#root {{ background: {BACKGROUND}; font-family: {FONT}; color: {TEXT}; }}")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        top_bar = TopBar()
        top_bar.staff_requested.connect(self.staff_requested.emit)
        layout.addWidget(top_bar)
        layout.addWidget(StepBar(active=1))
        layout.addWidget(self._body(), stretch=1)
        layout.addWidget(self._footer())
        self.alert = AlertPopup(self)

    def _set_card(self, title: str, subtitle: str, shape: str, highlighted: bool) -> None:
        self.card_title.setText(title)
        self.card_subtitle.setText(subtitle)
        self.card_icon.setPixmap(icon(shape, px(46), "#FFFFFF" if highlighted else "#2C5C14", 2 if highlighted else 1.8))
        self.card_icon.setStyleSheet(f"background: {GREEN if highlighted else LIGHT_GREEN}; border-radius: {px(42)}px;")
        border = f"border: {px(4)}px solid {GREEN};" if highlighted else "border: none;"
        self.scan_card.setStyleSheet(f"#scanCard {{ background: white; border-radius: {px(40)}px; {border} }}")

    def _update_guide(self) -> None:
        guard = self.guard
        self.guide.setVisible(guard is not None)
        if guard is None:
            return
        self.pay_button.setEnabled(self.cart.item_count > 0 and self._pay_allowed())
        if getattr(guard, "alert", False) and guard.state == "taken":
            self.alert.show_message(guard.message, "Imate neskeniran artikal")
        elif getattr(guard, "held_message", ""):
            self.alert.show_message(guard.held_message, "Artikal u ruci")
        elif time.monotonic() >= self._alert_until:
            self.alert.hide()
        state = guard.state
        left = getattr(guard, "zone_a_left", 0) > 0 and self.cart.item_count > 0
        key = (state, guard.message if state == "taken" else "", left)
        if key == self.guide_state:
            return
        self.guide_state = key
        if state == "learning":
            self.guide.set_step(0)
            self._set_card("Pripremam kamere…", "Trenutak, kasa se priprema", ICON_HAND, False)
        elif state == "empty":
            self.guide.set_step(0)
            self._set_card("Stavite korpu na polje", "Korpu ili artikle stavite na označeno mjesto", ICON_HAND, False)
        elif state == "offline":
            self.guide.set_step(0)
            self._set_card("Kamere nisu dostupne", "Pozovite osoblje", ICON_HAND, False)
        elif state == "taken":
            self.guide.set_step(1)
            subtitle = guard.message if getattr(guard, "unscanned", 0) > 0 else "Artikal je uzet iz korpe. Prislonite barkod na skener."
            self._set_card("Sad ga skenirajte", subtitle, ICON_SCANNER, True)
        else:
            self.guide.set_step(0)
            subtitle = ("U korpi još ima artikala. Skenirajte sve artikle prije plaćanja." if left
                        else "Zatim ga skenirajte i odložite na polje")
            self._set_card("Uzmite artikal iz korpe", subtitle, ICON_HAND, False)

    def begin(self) -> None:
        self.guide_state = ""
        self.guide_timer.start()
        self._update_guide()
        self.cart.clear()
        self.notice.hide()
        self._refresh()
        self.barcode_input.setFocus()

    def resume(self) -> None:
        self._refresh()
        self.barcode_input.setFocus()

    def _body(self) -> QWidget:
        body = QWidget()
        column = QVBoxLayout(body)
        column.setContentsMargins(px(40), px(12), px(40), px(20))
        column.setSpacing(px(18))
        column.addWidget(self._scan_card())

        self.notice = self._notice()
        policy = self.notice.sizePolicy()
        policy.setRetainSizeWhenHidden(True)
        self.notice.setSizePolicy(policy)
        self.notice.hide()
        column.addWidget(self.notice)

        column.addLayout(self._cart_header())
        column.addWidget(self._cart_list(), stretch=1)
        return body

    def _scan_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("scanCard")
        card.setStyleSheet(f"#scanCard {{ background: white; border-radius: {px(40)}px; }}")
        self.scan_card = card
        column = QVBoxLayout(card)
        column.setContentsMargins(px(28), px(26), px(28), px(26))
        column.setSpacing(px(20))

        top = QHBoxLayout()
        top.setSpacing(px(22))
        circle = QLabel()
        circle.setFixedSize(px(84), px(84))
        circle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        circle.setPixmap(icon(ICON_SCANNER, px(46)))
        circle.setStyleSheet(f"background: {LIGHT_GREEN}; border-radius: {px(42)}px;")
        self.card_icon = circle
        top.addWidget(circle)

        texts = QVBoxLayout()
        texts.setSpacing(px(4))
        title = QLabel("Skenirajte sljedeći artikal")
        title.setStyleSheet(f"font-size: {px(42)}px; font-weight: 800;")
        title.setWordWrap(True)
        title.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        subtitle = QLabel("Prislonite barkod na skener ispod ekrana")
        subtitle.setStyleSheet(f"font-size: {px(24)}px; color: {MUTED_TEXT};")
        subtitle.setWordWrap(True)
        subtitle.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.card_title, self.card_subtitle = title, subtitle
        texts.addWidget(title)
        texts.addWidget(subtitle)
        top.addLayout(texts, stretch=1)
        column.addLayout(top)

        self.guide = GuideSteps()
        self.guide.setVisible(False)
        column.addWidget(self.guide)

        self.barcode_input = QLineEdit()
        self.barcode_input.setPlaceholderText("Ili upišite barkod artikla")
        self.barcode_input.setFixedHeight(px(76))
        self.barcode_input.setStyleSheet(
            f"QLineEdit {{ background: {BACKGROUND}; border: {px(2)}px solid {BORDER};"
            f" border-radius: {px(38)}px; padding: 0 {px(28)}px; font-size: {px(26)}px; color: {TEXT}; }}"
        )
        self.barcode_input.returnPressed.connect(self._on_barcode_entered)
        column.addWidget(self.barcode_input)
        return card

    def _notice(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("notice")
        frame.setFixedHeight(px(92))
        row = QHBoxLayout(frame)
        row.setContentsMargins(px(24), 0, px(24), 0)
        row.setSpacing(px(16))

        self.notice_icon = QLabel()
        self.notice_icon.setFixedSize(px(48), px(48))
        self.notice_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row.addWidget(self.notice_icon)

        self.notice_message = QLabel()
        self.notice_message.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.notice_message.setStyleSheet(f"font-size: {px(27)}px; font-weight: 700; color: {TEXT};")
        row.addWidget(self.notice_message, stretch=1)

        self.notice_hint = QLabel("Odložite ga na polje  →")
        self.notice_hint.setFixedHeight(px(56))
        self.notice_hint.setStyleSheet(
            f"background: {WARNING_BACKGROUND}; color: {WARNING_TEXT}; border-radius: {px(28)}px;"
            f" padding: 0 {px(22)}px; font-size: {px(23)}px; font-weight: 800;"
        )
        row.addWidget(self.notice_hint)
        return frame

    def _show_notice(self, message: str, success: bool) -> None:
        background = LIGHT_GREEN if success else LIGHT_RED
        marker = GREEN if success else RED
        self.notice.setStyleSheet(f"#notice {{ background: {background}; border-radius: {px(30)}px; }}")
        self.notice_icon.setStyleSheet(f"background: {marker}; border-radius: {px(24)}px;")
        shape = ICON_CHECK if success else ICON_ALERT
        self.notice_icon.setPixmap(icon(shape, px(28), "#FFFFFF", 2.6))
        size = px(27) if len(message) <= 40 else px(21)
        self.notice_message.setWordWrap(len(message) > 40)
        self.notice_message.setStyleSheet(f"font-size: {size}px; font-weight: 700; color: {TEXT};")
        self.notice_message.setText(message)
        self.notice_hint.setVisible(success and self.guard is None)
        self.notice.show()

    def _cart_header(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setContentsMargins(px(8), px(6), px(8), 0)
        title = QLabel("Vaša korpa")
        title.setStyleSheet(f"font-size: {px(32)}px; font-weight: 800;")
        row.addWidget(title)
        row.addStretch()
        self.count_label = QLabel()
        self.count_label.setStyleSheet(f"font-size: {px(25)}px; font-weight: 600; color: {MUTED_TEXT};")
        row.addWidget(self.count_label)
        return row

    def _cart_list(self) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollArea > QWidget > QWidget { background: transparent; }"
        )
        content = QWidget()
        self.rows_layout = QVBoxLayout(content)
        self.rows_layout.setContentsMargins(0, 0, 0, 0)
        self.rows_layout.setSpacing(px(12))
        self.rows_layout.addStretch()
        scroll.setWidget(content)
        return scroll

    def _cart_row(self, item: dict) -> QFrame:
        row = QFrame()
        row.setObjectName("row")
        row.setFixedHeight(px(100))
        row.setStyleSheet(f"#row {{ background: white; border-radius: {px(30)}px; }}")
        layout = QHBoxLayout(row)
        layout.setContentsMargins(px(24), 0, px(24), 0)
        layout.setSpacing(px(18))

        texts = QVBoxLayout()
        texts.setSpacing(px(2))
        name = QLabel(item["name"])
        name.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        name.setStyleSheet(f"font-size: {px(28)}px; font-weight: 700;")
        unit = QLabel(f"{format_amount(item['price'])} KM po komadu")
        unit.setStyleSheet(f"font-size: {px(22)}px; color: {MUTED_TEXT};")
        texts.addStretch()
        texts.addWidget(name)
        texts.addWidget(unit)
        texts.addStretch()
        layout.addLayout(texts, stretch=1)

        quantity = QLabel(f"{item['quantity']} kom")
        quantity.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        quantity.setStyleSheet(f"font-size: {px(28)}px; font-weight: 700; color: {MUTED_TEXT};")
        layout.addWidget(quantity)

        amount = QLabel(format_amount(item["amount"]))
        amount.setFixedWidth(px(120))
        amount.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        amount.setStyleSheet(f"font-size: {px(30)}px; font-weight: 800;")
        layout.addWidget(amount)
        return row

    def _footer(self) -> QFrame:
        footer = QFrame()
        footer.setObjectName("footer")
        footer.setStyleSheet(
            f"#footer {{ background: white; border-top-left-radius: {px(48)}px;"
            f" border-top-right-radius: {px(48)}px; }}"
        )
        column = QVBoxLayout(footer)
        column.setContentsMargins(px(40), px(26), px(40), px(36))
        column.setSpacing(px(22))

        totals = QHBoxLayout()
        label = QLabel("Ukupno za platiti")
        label.setStyleSheet(f"font-size: {px(28)}px; font-weight: 700; color: {MUTED_TEXT};")
        totals.addWidget(label, alignment=Qt.AlignmentFlag.AlignBottom)
        totals.addStretch()
        self.total_label = QLabel()
        self.total_label.setStyleSheet(f"font-size: {px(68)}px; font-weight: 800;")
        totals.addWidget(self.total_label)
        column.addLayout(totals)

        buttons = QHBoxLayout()
        buttons.setSpacing(px(18))
        self.clear_button = QPushButton("Poništi sve")
        self.clear_button.setFixedSize(px(230), px(108))
        self.clear_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clear_button.setStyleSheet(
            f"QPushButton {{ background: white; color: {DARK_RED}; border: {px(3)}px solid {RED};"
            f" border-radius: {px(54)}px; font-size: {px(28)}px; font-weight: 800; }}"
            f"QPushButton:pressed {{ background: {LIGHT_RED}; }}"
            f"QPushButton:disabled {{ color: {BORDER}; border-color: {BORDER}; }}"
        )
        self.clear_button.clicked.connect(self.staff_requested.emit)
        buttons.addWidget(self.clear_button)

        self.pay_button = QPushButton("Plati  ")
        self.pay_button.setFixedHeight(px(108))
        self.pay_button.setIcon(QIcon(icon(ICON_ARROW, px(44), "#FFFFFF", 2.2)))
        self.pay_button.setIconSize(QSize(px(44), px(44)))
        self.pay_button.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.pay_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.pay_button.setStyleSheet(
            f"QPushButton {{ background: {GREEN}; color: white; border: none; border-radius: {px(54)}px;"
            f" font-size: {px(44)}px; font-weight: 800; }}"
            f"QPushButton:pressed {{ background: #2C5C14; }}"
            f"QPushButton:disabled {{ background: {BORDER}; }}"
        )
        self.pay_button.clicked.connect(self.pay_requested.emit)
        buttons.addWidget(self.pay_button, stretch=1)
        column.addLayout(buttons)

        quit_button = QPushButton("Zatvori aplikaciju (test)")
        quit_button.setFixedHeight(px(72))
        quit_button.setCursor(Qt.CursorShape.PointingHandCursor)
        quit_button.setStyleSheet(
            f"QPushButton {{ background: white; color: {MUTED_TEXT}; border: {px(2)}px solid {BORDER};"
            f" border-radius: {px(36)}px; font-size: {px(24)}px; font-weight: 700; }}"
            f"QPushButton:pressed {{ background: {BACKGROUND}; }}"
        )
        quit_button.clicked.connect(self.quit_requested.emit)
        column.addWidget(quit_button)
        return footer

    def _on_barcode_entered(self) -> None:
        barcode = self.barcode_input.text().strip()
        self.barcode_input.clear()
        if barcode:
            self._add_by_barcode(barcode)
        self.barcode_input.setFocus()

    def _add_by_barcode(self, barcode: str) -> None:
        try:
            product = find_by_barcode(barcode)
        except DatabaseError as error:
            self._show_notice(str(error), success=False)
            return
        if product is None:
            self._show_notice("Artikal nije pronađen. Pozovite osoblje.", success=False)
            return
        if self.guard is None:
            self.add_accepted(product)
            return
        seen = self.guard.outcome.number if self.guard.outcome else 0
        if not self.guard.scan(barcode, product.code, product.name):
            self._show_notice(self.guard.message, success=False)
            return
        self.place_requested.emit(product, seen)

    def add_accepted(self, product) -> None:
        self.cart.add(product)
        self._show_notice(f"Dodano: {product.name}", success=True)
        self._refresh()

    def show_rejected(self, message: str) -> None:
        self._show_notice(message, success=False)

    def _pay_allowed(self) -> bool:
        return self.guard is None or (getattr(self.guard, "unscanned", 0) == 0 and getattr(self.guard, "zone_a_left", 0) == 0
                                      and not getattr(self.guard, "checking", False) and not getattr(self.guard, "held_message", ""))

    def _refresh(self) -> None:
        data = self.cart.to_dict()
        while self.rows_layout.count() > 1:
            widget = self.rows_layout.takeAt(0).widget()
            if widget is not None:
                widget.deleteLater()
        if not data["items"]:
            empty = QLabel("Korpa je prazna. Skenirajte prvi artikal.")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setFixedHeight(px(100))
            empty.setStyleSheet(f"font-size: {px(26)}px; color: {MUTED_TEXT};")
            self.rows_layout.insertWidget(0, empty)
        for position, item in enumerate(data["items"]):
            self.rows_layout.insertWidget(position, self._cart_row(item))
        self.count_label.setText(item_count_text(data["item_count"]))
        self.total_label.setText(f"{format_amount(data['total'])} KM")
        has_items = data["item_count"] > 0
        self.pay_button.setEnabled(has_items and self._pay_allowed())
        self.clear_button.setEnabled(has_items)

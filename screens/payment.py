from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget

from cart import Cart
from formatting import format_amount, item_count_text
from screens.components import StepBar, TopBar
from styles import (
    BACKGROUND,
    BORDER,
    DARK_GREEN,
    FONT,
    GREEN,
    ICON_CARD,
    ICON_CHEVRON,
    ICON_QR,
    LIGHT_GREEN,
    LINE,
    MUTED_TEXT,
    TEXT,
    icon,
    px,
)


class PaymentScreen(QWidget):
    back_requested = Signal()
    staff_requested = Signal()
    card_selected = Signal()
    qr_selected = Signal()

    def __init__(self, cart: Cart) -> None:
        super().__init__()
        self.cart = cart
        self.setObjectName("root")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"#root {{ background: {BACKGROUND}; font-family: {FONT}; color: {TEXT}; }}")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        top_bar = TopBar(back_text="Natrag u korpu")
        top_bar.back_requested.connect(self.back_requested.emit)
        top_bar.staff_requested.connect(self.staff_requested.emit)
        layout.addWidget(top_bar)
        layout.addWidget(StepBar(active=2))
        layout.addWidget(self._body(), stretch=1)
        layout.addWidget(self._footer())

    def begin(self) -> None:
        data = self.cart.to_dict()
        self.count_label.setText(f"{item_count_text(data['item_count'])} u korpi")
        self.total_label.setText(f"{format_amount(data['total'])} KM")

    def _body(self) -> QWidget:
        body = QWidget()
        column = QVBoxLayout(body)
        column.setContentsMargins(px(40), px(20), px(40), 0)
        column.setSpacing(px(26))

        title = QLabel("Kako želite platiti?")
        title.setStyleSheet(f"font-size: {px(64)}px; font-weight: 800; padding: 0 {px(8)}px;")
        column.addWidget(title)
        column.addWidget(self._summary())

        card = self._option("cardOption", ICON_CARD, "Kartica", "Prislonite ili ubacite karticu na terminal", True)
        card.clicked.connect(self.card_selected.emit)
        column.addWidget(card, stretch=1)

        qr = self._option("qrOption", ICON_QR, "QR kod", "Skenirajte kod mobilnom bankarskom aplikacijom", False)
        qr.clicked.connect(self.qr_selected.emit)
        column.addWidget(qr, stretch=1)
        return body

    def _summary(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("summary")
        frame.setFixedHeight(px(156))
        frame.setStyleSheet(f"#summary {{ background: white; border-radius: {px(40)}px; }}")
        row = QHBoxLayout(frame)
        row.setContentsMargins(px(40), 0, px(40), 0)

        texts = QVBoxLayout()
        texts.setSpacing(px(4))
        texts.addStretch()
        label = QLabel("Ukupno za platiti")
        label.setStyleSheet(f"font-size: {px(28)}px; font-weight: 700; color: {MUTED_TEXT};")
        texts.addWidget(label)
        self.count_label = QLabel()
        self.count_label.setStyleSheet(f"font-size: {px(24)}px; color: {MUTED_TEXT};")
        texts.addWidget(self.count_label)
        texts.addStretch()
        row.addLayout(texts)
        row.addStretch()

        self.total_label = QLabel()
        self.total_label.setStyleSheet(f"font-size: {px(76)}px; font-weight: 800;")
        row.addWidget(self.total_label)
        return frame

    def _option(self, name: str, shape: str, title: str, description: str, highlighted: bool) -> QPushButton:
        border = GREEN if highlighted else LINE
        circle_background = LIGHT_GREEN if highlighted else BACKGROUND
        icon_color = DARK_GREEN if highlighted else TEXT
        chevron_color = GREEN if highlighted else MUTED_TEXT

        button = QPushButton()
        button.setObjectName(name)
        button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setStyleSheet(
            f"#{name} {{ background: white; border: {px(4)}px solid {border}; border-radius: {px(48)}px; }}"
            f"#{name}:pressed {{ background: {LIGHT_GREEN}; }}"
        )
        row = QHBoxLayout(button)
        row.setContentsMargins(px(44), 0, px(44), 0)
        row.setSpacing(px(36))

        circle = QLabel()
        circle.setFixedSize(px(150), px(150))
        circle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        circle.setPixmap(icon(shape, px(84), icon_color, 1.6))
        circle.setStyleSheet(f"background: {circle_background}; border-radius: {px(75)}px;")
        row.addWidget(circle)

        texts = QVBoxLayout()
        texts.setSpacing(px(8))
        texts.addStretch()
        title_label = QLabel(title)
        title_label.setStyleSheet(f"font-size: {px(56)}px; font-weight: 800; color: {TEXT};")
        texts.addWidget(title_label)
        description_label = QLabel(description)
        description_label.setWordWrap(True)
        description_label.setStyleSheet(f"font-size: {px(28)}px; color: {MUTED_TEXT};")
        texts.addWidget(description_label)
        texts.addStretch()
        row.addLayout(texts, stretch=1)

        chevron = QLabel()
        chevron.setPixmap(icon(ICON_CHEVRON, px(56), chevron_color, 2.4))
        row.addWidget(chevron)

        for label in (circle, title_label, description_label, chevron):
            label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        return button

    def _footer(self) -> QWidget:
        footer = QWidget()
        row = QHBoxLayout(footer)
        row.setContentsMargins(px(40), px(26), px(40), px(44))
        cancel = QPushButton("Odustani od plaćanja")
        cancel.setFixedHeight(px(96))
        cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel.setStyleSheet(
            f"QPushButton {{ background: white; color: {TEXT}; border: {px(3)}px solid {BORDER};"
            f" border-radius: {px(48)}px; font-size: {px(28)}px; font-weight: 800; }}"
            f"QPushButton:pressed {{ background: {BACKGROUND}; }}"
        )
        cancel.clicked.connect(self.back_requested.emit)
        row.addWidget(cancel)
        return footer

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

from screens.components import TopBar
from styles import BACKGROUND, BORDER, DARK_RED, FONT, GREEN, ICON_ALERT, LIGHT_RED, MUTED_TEXT, TEXT, icon, px


class UnpaidScreen(QWidget):
    """Poslije plaćanja je uzet neplaćen artikal: vrata se ne otvaraju dok se artikal ne vrati ili plati."""

    pay_requested = Signal()
    staff_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("root")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"#root {{ background: {BACKGROUND}; font-family: {FONT}; color: {TEXT}; }}")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(TopBar(show_staff=False))

        body = QVBoxLayout()
        body.setContentsMargins(px(40), px(70), px(40), px(40))
        body.setSpacing(px(26))
        mark = QLabel()
        mark.setFixedSize(px(176), px(176))
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mark.setPixmap(icon(ICON_ALERT, px(96), DARK_RED, 2.6))
        mark.setStyleSheet(f"background: {LIGHT_RED}; border-radius: {px(88)}px;")
        body.addWidget(mark, alignment=Qt.AlignmentFlag.AlignHCenter)

        title = QLabel("Niste sve platili")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(f"font-size: {px(68)}px; font-weight: 800; color: {DARK_RED};")
        body.addWidget(title)
        self.item_label = QLabel()
        self.item_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.item_label.setWordWrap(True)
        self.item_label.setStyleSheet(f"font-size: {px(36)}px; font-weight: 800;")
        body.addWidget(self.item_label)
        hint = QLabel("Vratite artikal u korpu na kasi ili ga skenirajte i platite. Vrata se neće otvoriti dok to ne uradite.")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setWordWrap(True)
        hint.setStyleSheet(f"font-size: {px(30)}px; color: {MUTED_TEXT};")
        body.addWidget(hint)
        body.addStretch()

        pay = QPushButton("Skeniraj i plati artikal")
        pay.setFixedHeight(px(112))
        pay.setCursor(Qt.CursorShape.PointingHandCursor)
        pay.setStyleSheet(
            f"QPushButton {{ background: {GREEN}; color: white; border: none; border-radius: {px(56)}px;"
            f" font-size: {px(38)}px; font-weight: 800; }}"
            f"QPushButton:pressed {{ background: #2C5C14; }}"
        )
        pay.clicked.connect(self.pay_requested.emit)
        body.addWidget(pay)
        staff = QPushButton("Pozovi osoblje")
        staff.setFixedHeight(px(96))
        staff.setCursor(Qt.CursorShape.PointingHandCursor)
        staff.setStyleSheet(
            f"QPushButton {{ background: white; color: {TEXT}; border: {px(3)}px solid {BORDER};"
            f" border-radius: {px(48)}px; font-size: {px(32)}px; font-weight: 800; }}"
            f"QPushButton:pressed {{ background: {BACKGROUND}; }}"
        )
        staff.clicked.connect(self.staff_requested.emit)
        body.addWidget(staff)
        layout.addLayout(body, stretch=1)

    def show_item(self, guess: str) -> None:
        self.item_label.setText(f"Uzeli ste: {guess}" if guess else "Uzeli ste artikal koji nije plaćen.")

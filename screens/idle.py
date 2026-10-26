from PySide6.QtCore import QEvent, QObject, Qt, Signal
from PySide6.QtWidgets import QFrame, QLabel, QPushButton, QVBoxLayout, QWidget

from styles import FONT, GREEN, MUTED_TEXT, TEXT, px

ACTIVITY_EVENTS = (QEvent.Type.MouseButtonPress, QEvent.Type.KeyPress, QEvent.Type.TouchBegin)


class ActivityFilter(QObject):
    """Svaki dodir, klik ili tipka (i sken, skener je tastatura) javlja da je kupac još tu."""

    def __init__(self, on_activity) -> None:
        super().__init__()
        self.on_activity = on_activity

    def eventFilter(self, watched, event) -> bool:
        if event.type() in ACTIVITY_EVENTS:
            self.on_activity()
        return False


class IdleOverlay(QWidget):
    """'Jeste li još tu?' preko cijelog ekrana, s odbrojavanjem do poništavanja kupovine."""

    stay = Signal()

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setObjectName("overlay")
        self.setStyleSheet(f"#overlay {{ background: rgba(22, 33, 26, 170); font-family: {FONT}; }}")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(px(48), 0, px(48), 0)
        layout.addStretch()
        card = QFrame()
        card.setObjectName("card")
        card.setStyleSheet(f"#card {{ background: white; border-radius: {px(44)}px; }}")
        column = QVBoxLayout(card)
        column.setContentsMargins(px(40), px(44), px(40), px(40))
        column.setSpacing(px(22))
        title = QLabel("Jeste li još tu?")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(f"font-size: {px(60)}px; font-weight: 800; color: {TEXT};")
        column.addWidget(title)
        self.countdown = QLabel()
        self.countdown.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.countdown.setWordWrap(True)
        self.countdown.setStyleSheet(f"font-size: {px(30)}px; color: {MUTED_TEXT};")
        column.addWidget(self.countdown)
        button = QPushButton("Da, nastavljam")
        button.setFixedHeight(px(112))
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setStyleSheet(
            f"QPushButton {{ background: {GREEN}; color: white; border: none; border-radius: {px(56)}px;"
            f" font-size: {px(42)}px; font-weight: 800; }}"
            f"QPushButton:pressed {{ background: #2C5C14; }}"
        )
        button.clicked.connect(self._on_stay)
        column.addWidget(button)
        layout.addWidget(card)
        layout.addStretch()
        self.hide()

    def show_countdown(self, seconds: int) -> None:
        self.countdown.setText(f"Kupovina će biti poništena za {seconds} s.")
        self.setGeometry(self.parentWidget().rect())
        if self.isHidden():
            self.show()
        self.raise_()

    def _on_stay(self) -> None:
        self.hide()
        self.stay.emit()

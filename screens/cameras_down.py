from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

from screens.components import TopBar
from styles import BACKGROUND, BORDER, DARK_RED, FONT, LIGHT_RED, MUTED_TEXT, TEXT, ICON_ALERT, icon, px


class CamerasDownScreen(QWidget):
    """Kasa je zaključana dok kamere ne rade; samo administrator (Postavke) može dozvoliti rad bez kamera."""

    settings_requested = Signal()

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
        body.setContentsMargins(px(40), px(80), px(40), px(40))
        body.setSpacing(px(28))
        mark = QLabel()
        mark.setFixedSize(px(176), px(176))
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mark.setPixmap(icon(ICON_ALERT, px(96), DARK_RED, 2.6))
        mark.setStyleSheet(f"background: {LIGHT_RED}; border-radius: {px(88)}px;")
        body.addWidget(mark, alignment=Qt.AlignmentFlag.AlignHCenter)

        title = QLabel("Kamere nisu dostupne")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setWordWrap(True)
        title.setStyleSheet(f"font-size: {px(64)}px; font-weight: 800;")
        body.addWidget(title)
        subtitle = QLabel("Kasa trenutno ne radi. Kontaktirajte administratora.")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet(f"font-size: {px(32)}px; color: {MUTED_TEXT};")
        body.addWidget(subtitle)
        self.reason = QLabel()
        self.reason.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.reason.setWordWrap(True)
        self.reason.setStyleSheet(f"font-size: {px(22)}px; color: {MUTED_TEXT};")
        body.addWidget(self.reason)
        body.addStretch()

        settings = QPushButton("Postavke")
        settings.setFixedHeight(px(96))
        settings.setCursor(Qt.CursorShape.PointingHandCursor)
        settings.setStyleSheet(
            f"QPushButton {{ background: white; color: {TEXT}; border: {px(3)}px solid {BORDER};"
            f" border-radius: {px(48)}px; font-size: {px(32)}px; font-weight: 800; }}"
            f"QPushButton:pressed {{ background: {BACKGROUND}; }}"
        )
        settings.clicked.connect(self.settings_requested.emit)
        body.addWidget(settings)
        layout.addLayout(body, stretch=1)

    def show_reason(self, reason: str) -> None:
        self.reason.setText(reason)

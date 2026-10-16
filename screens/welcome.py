from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from styles import (
    BACKGROUND,
    FONT,
    GREEN,
    ICON_ARROW,
    ICON_BOX,
    ICON_CARD,
    ICON_HEADSET,
    ICON_SCANNER,
    LIGHT_GREEN,
    MUTED_TEXT,
    RED,
    TEXT,
    icon,
    px,
    rounded_logo,
)


class WelcomeScreen(QWidget):
    started = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("root")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"#root {{ background: {BACKGROUND}; font-family: {FONT}; color: {TEXT}; }}")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._red_section())
        layout.addSpacing(px(128))
        layout.addLayout(self._steps())
        layout.addStretch()
        layout.addLayout(self._footer())

        self.start_button = QPushButton("Dodirnite za početak  ", self)
        self.start_button.setIcon(QIcon(icon(ICON_ARROW, px(48), "#FFFFFF", 2.2)))
        self.start_button.setIconSize(QSize(px(48), px(48)))
        self.start_button.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.start_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.start_button.setGeometry(px(64), px(700 - 72), px(820 - 128), px(144))
        self.start_button.setStyleSheet(
            f"QPushButton {{ background: {GREEN}; color: white; border: none;"
            f" border-radius: {px(72)}px; font-size: {px(44)}px; font-weight: 800; }}"
            f"QPushButton:pressed {{ background: #2C5C14; }}"
        )
        self.start_button.clicked.connect(self.started.emit)
        self.start_button.raise_()

    def _red_section(self) -> QFrame:
        frame = QFrame()
        frame.setFixedHeight(px(700))
        frame.setStyleSheet(
            f"QFrame {{ background: {RED}; border-bottom-left-radius: {px(72)}px;"
            f" border-bottom-right-radius: {px(72)}px; }}"
        )
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(px(64), px(48), px(64), px(72 + 8))
        layout.setSpacing(px(28))
        layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        tile = QFrame()
        tile.setFixedSize(px(232), px(232))
        tile.setStyleSheet(f"QFrame {{ background: white; border-radius: {px(56)}px; }}")
        tile_layout = QVBoxLayout(tile)
        tile_layout.setContentsMargins(px(14), px(14), px(14), px(14))
        logo = QLabel()
        logo.setPixmap(rounded_logo(px(204), px(44)))
        logo.setStyleSheet("background: transparent;")
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tile_layout.addWidget(logo)
        layout.addWidget(tile, alignment=Qt.AlignmentFlag.AlignHCenter)

        title = QLabel("Dobrodošli")
        title.setStyleSheet(f"background: transparent; color: white; font-size: {px(84)}px; font-weight: 800;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        subtitle = QLabel("Skenirajte artikle, odložite ih i platite. Bez čekanja u redu.")
        subtitle.setWordWrap(True)
        subtitle.setMaximumWidth(px(660))
        subtitle.setMinimumHeight(px(100))
        subtitle.setStyleSheet(f"background: transparent; color: white; font-size: {px(32)}px; font-weight: 500;")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(subtitle, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addStretch()
        return frame

    def _steps(self) -> QVBoxLayout:
        column = QVBoxLayout()
        column.setContentsMargins(px(64), 0, px(64), 0)
        column.setSpacing(px(28))

        heading = QLabel("KAKO FUNKCIONIŠE")
        heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        heading.setStyleSheet(f"color: {MUTED_TEXT}; font-size: {px(26)}px; font-weight: 700; background: transparent;")
        column.addWidget(heading)

        row = QHBoxLayout()
        row.setSpacing(px(24))
        row.addWidget(self._step_card(ICON_SCANNER, "1. Skenirajte", "Prislonite barkod na skener"))
        row.addWidget(self._step_card(ICON_BOX, "2. Odložite", "Stavite artikal na označeno polje"))
        row.addWidget(self._step_card(ICON_CARD, "3. Platite", "Karticom ili QR kodom"))
        column.addLayout(row)
        return column

    def _step_card(self, icon_shape: str, title: str, description: str) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        card.setStyleSheet(f"#card {{ background: white; border-radius: {px(32)}px; }}")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(px(20), px(32), px(20), px(32))
        layout.setSpacing(px(18))

        circle = QLabel()
        circle.setFixedSize(px(96), px(96))
        circle.setStyleSheet(f"background: {LIGHT_GREEN}; border-radius: {px(48)}px;")
        circle.setPixmap(icon(icon_shape, px(48)))
        circle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(circle, alignment=Qt.AlignmentFlag.AlignHCenter)

        title_label = QLabel(title)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setStyleSheet(f"font-size: {px(30)}px; font-weight: 800; background: transparent;")
        layout.addWidget(title_label)

        description_label = QLabel(description)
        description_label.setWordWrap(True)
        description_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        description_label.setStyleSheet(f"font-size: {px(24)}px; color: {MUTED_TEXT}; background: transparent;")
        layout.addWidget(description_label)
        layout.addStretch()
        return card

    def _footer(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, px(48))
        row.setSpacing(px(14))
        row.addStretch()
        headset = QLabel()
        headset.setPixmap(icon(ICON_HEADSET, px(32), MUTED_TEXT))
        row.addWidget(headset)
        text = QLabel("Treba vam pomoć? Osoblje je u blizini.")
        text.setStyleSheet(f"font-size: {px(26)}px; font-weight: 600; color: {MUTED_TEXT}; background: transparent;")
        row.addWidget(text)
        row.addStretch()
        return row

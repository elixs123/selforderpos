from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget

from styles import (
    BORDER,
    DARK_GREEN,
    GREEN,
    ICON_BACK,
    ICON_CHECK,
    ICON_HEADSET,
    LIGHT_GREEN,
    LINE,
    MUTED_TEXT,
    TEXT,
    icon,
    px,
    rounded_logo,
)

STEP_NAMES = ("Skeniranje", "Plaćanje", "Račun")


class TopBar(QWidget):
    staff_requested = Signal()
    back_requested = Signal()

    def __init__(self, back_text: str | None = None, show_staff: bool = True) -> None:
        super().__init__()
        self.setFixedHeight(px(112))
        layout = QHBoxLayout(self)
        layout.setContentsMargins(px(40), 0, px(40), 0)
        layout.setSpacing(px(18))

        if back_text is None:
            logo = QLabel()
            logo.setPixmap(rounded_logo(px(68), px(18)))
            layout.addWidget(logo)
            title = QLabel("Samouslužna kasa")
            title.setStyleSheet(f"font-size: {px(30)}px; font-weight: 800; color: {TEXT};")
            layout.addWidget(title)
        else:
            back = self._pill_button(back_text, ICON_BACK, 2.2)
            back.clicked.connect(self.back_requested.emit)
            layout.addWidget(back)
        layout.addStretch()

        if show_staff:
            staff = self._pill_button("Pozovi osoblje", ICON_HEADSET, 1.9)
            staff.clicked.connect(self.staff_requested.emit)
            layout.addWidget(staff)

    def _pill_button(self, text: str, shape: str, stroke_width: float) -> QPushButton:
        button = QPushButton(text)
        button.setIcon(QIcon(icon(shape, px(30), TEXT, stroke_width)))
        button.setIconSize(QSize(px(30), px(30)))
        button.setFixedHeight(px(68))
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setStyleSheet(
            f"QPushButton {{ background: white; color: {TEXT}; border: {px(2)}px solid {LINE};"
            f" border-radius: {px(34)}px; padding: 0 {px(28)}px; font-size: {px(26)}px; font-weight: 700; }}"
        )
        return button


class StepBar(QWidget):
    def __init__(self, active: int) -> None:
        super().__init__()
        self.setFixedHeight(px(80))
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(px(18))
        layout.addStretch()
        for number, name in enumerate(STEP_NAMES, start=1):
            if number > 1:
                layout.addWidget(self._connector(reached=number <= active))
            layout.addWidget(self._step(number, name, active))
        layout.addStretch()

    def _connector(self, reached: bool) -> QWidget:
        line = QWidget()
        line.setFixedSize(px(56), px(4))
        color = GREEN if reached else LINE
        line.setStyleSheet(f"background: {color}; border-radius: {px(2)}px;")
        return line

    def _step(self, number: int, name: str, active: int) -> QWidget:
        step = QWidget()
        layout = QHBoxLayout(step)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(px(12))

        circle = QLabel()
        circle.setFixedSize(px(48), px(48))
        circle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        radius = px(24)
        if number < active:
            circle.setPixmap(icon(ICON_CHECK, px(26), DARK_GREEN, 3))
            circle.setStyleSheet(f"background: {LIGHT_GREEN}; border-radius: {radius}px;")
        elif number == active:
            circle.setText(str(number))
            circle.setStyleSheet(
                f"background: {GREEN}; color: white; border-radius: {radius}px;"
                f" font-size: {px(26)}px; font-weight: 800;"
            )
        else:
            circle.setText(str(number))
            circle.setStyleSheet(
                f"border: {px(3)}px solid {BORDER}; color: {MUTED_TEXT}; border-radius: {radius}px;"
                f" font-size: {px(26)}px; font-weight: 800;"
            )
        layout.addWidget(circle)

        label = QLabel(name)
        if number == active:
            label.setStyleSheet(f"font-size: {px(27)}px; font-weight: 800; color: {TEXT};")
        else:
            label.setStyleSheet(f"font-size: {px(27)}px; font-weight: 600; color: {MUTED_TEXT};")
        layout.addWidget(label)
        return step


class PinPad(QWidget):
    accepted = Signal()
    cancelled = Signal()

    def __init__(self, title: str, subtitle: str, checker, length: int = 8) -> None:
        super().__init__()
        self.checker = checker
        self.length = length
        self.entered = ""
        column = QVBoxLayout(self)
        column.setContentsMargins(px(40), px(20), px(40), px(40))
        column.setSpacing(px(24))

        heading = QLabel(title)
        heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        heading.setStyleSheet(f"font-size: {px(60)}px; font-weight: 800; color: {TEXT};")
        column.addWidget(heading)
        detail = QLabel(subtitle)
        detail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        detail.setWordWrap(True)
        detail.setStyleSheet(f"font-size: {px(30)}px; color: {MUTED_TEXT};")
        column.addWidget(detail)

        self.display = QLabel()
        self.display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.display.setFixedHeight(px(110))
        self.display.setStyleSheet(f"background: white; border-radius: {px(36)}px; font-size: {px(48)}px; font-weight: 800; color: {TEXT};")
        column.addWidget(self.display)

        self.error = QLabel()
        self.error.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.error.setWordWrap(True)
        self.error.setStyleSheet(f"font-size: {px(26)}px; font-weight: 700; color: #B8101F;")
        column.addWidget(self.error)

        grid = QGridLayout()
        grid.setSpacing(px(16))
        for index, key in enumerate(["1", "2", "3", "4", "5", "6", "7", "8", "9", "Obriši", "0", "OK"]):
            grid.addWidget(self._key(key), index // 3, index % 3)
        column.addLayout(grid, stretch=1)

        cancel = QPushButton("Odustani")
        cancel.setFixedHeight(px(96))
        cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel.setStyleSheet(
            f"QPushButton {{ background: white; color: {TEXT}; border: {px(3)}px solid {BORDER};"
            f" border-radius: {px(48)}px; font-size: {px(28)}px; font-weight: 800; }}"
        )
        cancel.clicked.connect(self.cancelled.emit)
        column.addWidget(cancel)
        self.reset()

    def reset(self) -> None:
        self.entered = ""
        self.error.setText("")
        self._update()

    def _key(self, key: str) -> QPushButton:
        button = QPushButton(key)
        button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        button.setMinimumHeight(px(100))
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        background, color = (GREEN, "white") if key == "OK" else ("white", TEXT)
        size = px(30) if key == "Obriši" else px(46)
        button.setStyleSheet(
            f"QPushButton {{ background: {background}; color: {color}; border: none; border-radius: {px(36)}px;"
            f" font-size: {size}px; font-weight: 800; }}"
            f"QPushButton:pressed {{ background: {BORDER}; }}"
        )
        button.clicked.connect(lambda _checked=False: self._press(key))
        return button

    def _press(self, key: str) -> None:
        if key == "Obriši":
            self.entered = self.entered[:-1]
        elif key == "OK":
            self._submit()
            return
        elif len(self.entered) < self.length:
            self.entered += key
        self.error.setText("")
        self._update()

    def _update(self) -> None:
        self.display.setText("●" * len(self.entered) if self.entered else "Unesite šifru")

    def _submit(self) -> None:
        try:
            valid = self.checker(self.entered)
        except Exception as error:
            self.error.setText(str(error))
            return
        self.entered = ""
        self._update()
        if not valid:
            self.error.setText("Pogrešna šifra")
            return
        self.accepted.emit()

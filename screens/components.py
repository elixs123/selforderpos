from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon
from PySide6.QtWidgets import QFrame, QGraphicsDropShadowEffect, QGridLayout, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget

from styles import (
    BORDER,
    DARK_GREEN,
    GREEN,
    ICON_BACK,
    ICON_ALERT,
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
ALERT_TONES = {
    "warning": ("#FFF8E8", "#E8A317", "#5C3B00", "#7A5410"),
    "error": ("#FFF1F2", "#D5182A", "#5E0B14", "#7F1D2A"),
}


class AlertPopup(QFrame):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("alertPopup")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(px(48))
        shadow.setOffset(0, px(10))
        shadow.setColor(QColor(22, 33, 26, 60))
        self.setGraphicsEffect(shadow)
        row = QHBoxLayout(self)
        row.setContentsMargins(px(34), px(28), px(40), px(28))
        row.setSpacing(px(26))
        self.badge = QLabel()
        self.badge.setFixedSize(px(76), px(76))
        self.badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row.addWidget(self.badge, alignment=Qt.AlignmentFlag.AlignTop)
        column = QVBoxLayout()
        column.setSpacing(px(6))
        self.title = QLabel("")
        self.text = QLabel("")
        self.text.setWordWrap(True)
        column.addWidget(self.title)
        column.addWidget(self.text)
        row.addLayout(column, stretch=1)
        self.tone = ""
        self.hide()
        parent.installEventFilter(self)

    def eventFilter(self, watched, event) -> bool:
        if watched is self.parent() and event.type() == event.Type.Resize and self.isVisible():
            self._place()
        return False

    def _paint(self, tone: str) -> None:
        if tone == self.tone:
            return
        self.tone = tone
        background, accent, title_color, text_color = ALERT_TONES.get(tone, ALERT_TONES["warning"])
        self.setStyleSheet(
            f"#alertPopup {{ background: {background}; border: {px(2)}px solid {accent}; "
            f"border-left: {px(14)}px solid {accent}; border-radius: {px(28)}px; }}"
        )
        self.badge.setPixmap(icon(ICON_ALERT, px(44), "#FFFFFF", 2.2))
        self.badge.setStyleSheet(f"background: {accent}; border-radius: {px(38)}px;")
        self.title.setStyleSheet(f"color: {title_color}; font-size: {px(36)}px; font-weight: 800; background: transparent;")
        self.text.setStyleSheet(f"color: {text_color}; font-size: {px(30)}px; font-weight: 500; background: transparent;")

    def _place(self) -> None:
        parent = self.parent()
        width = min(parent.width() - px(80), px(960))
        self.setFixedWidth(width)
        self.adjustSize()
        self.move((parent.width() - width) // 2, px(250))

    def show_message(self, text: str, title: str = "Pažnja", tone: str = "warning") -> None:
        if self.isVisible() and self.text.text() == text and self.title.text() == title and self.tone == tone:
            return
        self._paint(tone)
        self.title.setText(title)
        self.text.setText(text)
        self.show()
        self._place()
        self.raise_()


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


GUIDE_STEPS = ("Uzmite", "Skenirajte", "Odložite")


class GuideSteps(QWidget):
    def __init__(self) -> None:
        super().__init__()
        from styles import ICON_DOWN, ICON_HAND, ICON_SCANNER

        self.shapes = (ICON_HAND, ICON_SCANNER, ICON_DOWN)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(px(10))
        self.pills: list[tuple[QWidget, QLabel, QLabel]] = []
        for index, name in enumerate(GUIDE_STEPS):
            if index:
                arrow = QLabel("›")
                arrow.setStyleSheet(f"font-size: {px(34)}px; font-weight: 800; color: {BORDER};")
                layout.addWidget(arrow)
            pill = QFrame()
            pill.setObjectName(f"guide{index}")
            pill.setFixedHeight(px(72))
            row = QHBoxLayout(pill)
            row.setContentsMargins(px(10), 0, px(16), 0)
            row.setSpacing(px(10))
            circle = QLabel()
            circle.setFixedSize(px(48), px(48))
            circle.setAlignment(Qt.AlignmentFlag.AlignCenter)
            row.addWidget(circle)
            label = QLabel(name)
            row.addWidget(label, stretch=1)
            layout.addWidget(pill, stretch=1)
            self.pills.append((pill, circle, label))
        self.set_step(0)

    def set_step(self, active: int) -> None:
        for index, (pill, circle, label) in enumerate(self.pills):
            if index < active:
                background, text, circle_background = LIGHT_GREEN, DARK_GREEN, GREEN
                circle.setPixmap(icon(ICON_CHECK, px(26), "#FFFFFF", 3))
            elif index == active:
                background, text, circle_background = GREEN, "#FFFFFF", "#FFFFFF"
                circle.setPixmap(icon(self.shapes[index], px(28), GREEN, 2))
            else:
                background, text, circle_background = "#FFFFFF", MUTED_TEXT, LIGHT_GREEN
                circle.setPixmap(icon(self.shapes[index], px(28), MUTED_TEXT, 1.8))
            pill.setStyleSheet(
                f"#{pill.objectName()} {{ background: {background}; border-radius: {px(36)}px;"
                f" border: {px(2)}px solid {GREEN if index <= active else LINE}; }}"
            )
            circle.setStyleSheet(f"background: {circle_background}; border-radius: {px(24)}px;")
            label.setStyleSheet(f"font-size: {px(24)}px; font-weight: 800; color: {text}; background: transparent;")

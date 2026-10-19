from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from formatting import format_amount
from screens.components import AlertPopup, GuideSteps, StepBar, TopBar
from styles import (
    BACKGROUND,
    BORDER,
    DARK_GREEN,
    FONT,
    GREEN,
    ICON_BOX,
    ICON_CHECK,
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

POLL_MS = 150


def customer_problem(message: str) -> tuple[str, str]:
    if "više artikala" in message:
        return "Više artikala u zoni B", "Višak vratite u zonu A. U zoni B ostavite samo artikal koji ste skenirali."
    if message.startswith("Artikal ne odgovara"):
        return "Artikal ne odgovara", "Uklonite ga iz zone B i odložite artikal koji ste skenirali."
    return "Pažnja", message


class DropScreen(QWidget):
    accepted = Signal(object)
    rejected = Signal(str)
    staff_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.guard = None
        self.product = None
        self.seen_outcome = 0
        self.timer = QTimer(self)
        self.timer.setInterval(POLL_MS)
        self.timer.timeout.connect(self._poll)
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

    @property
    def waiting(self) -> bool:
        return self.product is not None

    def begin(self, product, guard, seen_outcome: int) -> None:
        self.product, self.guard, self.seen_outcome = product, guard, seen_outcome
        self.name_label.setText(product.name)
        self.price_label.setText(f"{format_amount(product.price)} KM")
        self._poll()
        self.timer.start()

    def resume(self) -> None:
        if self.waiting:
            self.timer.start()

    def cancel(self) -> None:
        self._stop()

    def _stop(self) -> None:
        self.alert.hide()
        self.timer.stop()
        self.product = None

    def _poll(self) -> None:
        guard = self.guard
        if guard is None or self.product is None:
            return
        outcome = guard.outcome
        if outcome is not None and outcome.number > self.seen_outcome:
            product = self.product
            if outcome.kind == "accepted":
                self._stop()
                self.accepted.emit(product)
                return
            if outcome.kind == "rejected":
                self._stop()
                self.rejected.emit(outcome.message)
                return
            self.seen_outcome = outcome.number
            self._paint("problem", outcome.message)
            self.staff_requested.emit()
            return
        if guard.state == "mismatch":
            self._paint("problem", guard.message)
            if "više artikala" in guard.message:
                title, text = customer_problem(guard.message)
                self.alert.show_message(text, title)
            else:
                self.alert.hide()
            return
        self.alert.hide()
        if guard.state == "judging":
            self.guide.set_step(2)
            self._paint("ok", "Provjeravam artikal…")
        elif guard.state == "waiting_take":
            self.guide.set_step(0)
            self._paint("wait", "Uzmite artikal iz korpe i izvucite ruku...")
        else:
            self.guide.set_step(2)
            self._paint("ok", "Čekam da odložite artikal…")

    def _paint(self, mode: str, message: str) -> None:
        colors = {
            "ok": (LIGHT_GREEN, GREEN, DARK_GREEN),
            "wait": (WARNING_BACKGROUND, WARNING_TEXT, WARNING_TEXT),
            "problem": (LIGHT_RED, RED, "#B8101F"),
        }
        background, border, text = colors[mode]
        self.zone.setStyleSheet(
            f"#zone {{ background: {background}; border: {px(6)}px dashed {border}; border-radius: {px(60)}px; }}"
        )
        self.zone_title.setStyleSheet(f"font-size: {px(44)}px; font-weight: 800; color: {text};")
        self.zone_title.setText("Artikal ne odgovara" if mode == "problem" else "Polje za odlaganje")
        self.status_label.setText(message)
        self.status_label.setStyleSheet(f"font-size: {px(28)}px; font-weight: 700; color: {text if mode == 'problem' else TEXT};")

    def _body(self) -> QWidget:
        body = QWidget()
        column = QVBoxLayout(body)
        column.setContentsMargins(px(40), px(12), px(40), px(12))
        column.setSpacing(px(18))

        title = QLabel("Odložite artikal")
        title.setStyleSheet(f"font-size: {px(60)}px; font-weight: 800;")
        column.addWidget(title)
        self.guide = GuideSteps()
        self.guide.set_step(2)
        column.addWidget(self.guide)

        card = QFrame()
        card.setObjectName("scanned")
        card.setFixedHeight(px(130))
        card.setStyleSheet(f"#scanned {{ background: white; border-radius: {px(40)}px; }}")
        row = QHBoxLayout(card)
        row.setContentsMargins(px(28), 0, px(28), 0)
        row.setSpacing(px(20))
        check = QLabel()
        check.setFixedSize(px(64), px(64))
        check.setAlignment(Qt.AlignmentFlag.AlignCenter)
        check.setPixmap(icon(ICON_CHECK, px(34), "#FFFFFF", 2.6))
        check.setStyleSheet(f"background: {GREEN}; border-radius: {px(32)}px;")
        row.addWidget(check)
        texts = QVBoxLayout()
        texts.addStretch()
        caption = QLabel("Upravo skenirano")
        caption.setStyleSheet(f"font-size: {px(23)}px; font-weight: 600; color: {MUTED_TEXT};")
        texts.addWidget(caption)
        self.name_label = QLabel()
        self.name_label.setStyleSheet(f"font-size: {px(36)}px; font-weight: 800;")
        texts.addWidget(self.name_label)
        texts.addStretch()
        row.addLayout(texts, stretch=1)
        self.price_label = QLabel()
        self.price_label.setStyleSheet(f"font-size: {px(36)}px; font-weight: 800;")
        row.addWidget(self.price_label)
        column.addWidget(card)

        self.zone = QFrame()
        self.zone.setObjectName("zone")
        zone_column = QVBoxLayout(self.zone)
        zone_column.setSpacing(px(18))
        zone_column.addStretch()
        box = QLabel()
        box.setAlignment(Qt.AlignmentFlag.AlignCenter)
        box.setPixmap(icon(ICON_BOX, px(176), DARK_GREEN, 1.2))
        zone_column.addWidget(box)
        self.zone_title = QLabel("Polje za odlaganje")
        self.zone_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        zone_column.addWidget(self.zone_title)
        hint = QLabel("Stavite artikal na označeno polje")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setStyleSheet(f"font-size: {px(27)}px; font-weight: 600; color: {DARK_GREEN};")
        zone_column.addWidget(hint)
        zone_column.addStretch()
        column.addWidget(self.zone, stretch=1)

        self.status_label = QLabel()
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setWordWrap(True)
        column.addWidget(self.status_label)
        self._paint("ok", "Čekam da odložite artikal…")
        return body

    def _footer(self) -> QWidget:
        footer = QWidget()
        column = QVBoxLayout(footer)
        column.setContentsMargins(px(40), px(12), px(40), px(40))
        cancel = QPushButton("Vratio sam artikal, ne kupujem ga")
        cancel.setFixedHeight(px(96))
        cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel.setStyleSheet(
            f"QPushButton {{ background: white; color: {TEXT}; border: {px(3)}px solid {BORDER};"
            f" border-radius: {px(48)}px; font-size: {px(28)}px; font-weight: 800; }}"
        )
        cancel.clicked.connect(self._cancel)
        column.addWidget(cancel)
        return footer

    def _cancel(self) -> None:
        if self.guard is not None:
            self.guard.cancel()
        self._stop()
        self.rejected.emit("Artikal nije dodan.")

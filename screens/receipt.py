import threading

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from cart import Cart
from formatting import format_amount
from screens.components import StepBar, TopBar
from styles import (
    BACKGROUND,
    FONT,
    GREEN,
    ICON_CHECK,
    ICON_PRINTER,
    LINE,
    MUTED_TEXT,
    TEXT,
    icon,
    px,
)

RETURN_SECONDS = 20
PAYMENT_METHOD_NAMES = {"card": "Kartica", "qr": "QR kod"}


class ReceiptScreen(QWidget):
    done = Signal()
    fiscal_done = Signal(object)

    def __init__(self, cart: Cart) -> None:
        super().__init__()
        self.cart = cart
        self.seconds_left = RETURN_SECONDS
        self.return_seconds = RETURN_SECONDS
        self.fiscal_job = None
        self.fiscal_done.connect(self._on_fiscal_done)
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._tick)

        self.setObjectName("root")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"#root {{ background: {BACKGROUND}; font-family: {FONT}; color: {TEXT}; }}")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(TopBar(show_staff=False))
        layout.addWidget(StepBar(active=3))
        layout.addWidget(self._body(), stretch=1)
        layout.addWidget(self._footer())

    def begin(self, payment_method: str, number: str, fiscal_job=None, return_seconds: int = RETURN_SECONDS) -> None:
        self.count_value.setText(str(self.cart.item_count))
        self.method_value.setText(PAYMENT_METHOD_NAMES[payment_method])
        self.number_value.setText(number)
        self.paid_value.setText(f"{format_amount(self.cart.total)} KM")
        self.return_seconds = max(5, return_seconds)
        self.seconds_left = self.return_seconds
        self._update_countdown()
        self.fiscal_job = fiscal_job
        self.retry_button.setVisible(False)
        if fiscal_job is None:
            self.printing_text.setStyleSheet(f"font-size: {px(26)}px; font-weight: 600; color: {MUTED_TEXT};")
            self.printing_text.setText("Hvala, ponesite artikle sa zone B.")
            self.timer.start()
            return
        self._print_fiscal()

    def _print_fiscal(self) -> None:
        job = self.fiscal_job
        self.retry_button.setVisible(False)
        self.printing_text.setStyleSheet(f"font-size: {px(26)}px; font-weight: 600; color: {MUTED_TEXT};")
        self.printing_text.setText("Fiskalni račun se štampa...")
        threading.Thread(target=lambda: self.fiscal_done.emit(job()), daemon=True).start()

    def _on_fiscal_done(self, result) -> None:
        if result.ok:
            self.printing_text.setText("Račun se štampa ispod ekrana")
            self.timer.start()
        else:
            self.printing_text.setText("Fiskalni račun nije odštampan. Pokušajte ponovo ili pozovite osoblje.")
            self.printing_text.setStyleSheet(f"font-size: {px(26)}px; font-weight: 800; color: #B8101F;")
            self.retry_button.setVisible(True)

    def _tick(self) -> None:
        self.seconds_left -= 1
        if self.seconds_left <= 0:
            self._finish()
            return
        self._update_countdown()

    def _update_countdown(self) -> None:
        self.countdown_label.setText(f"Ekran se automatski vraća na početak za {self.seconds_left} s")

    def _finish(self) -> None:
        self.timer.stop()
        self.done.emit()

    def _body(self) -> QWidget:
        body = QWidget()
        column = QVBoxLayout(body)
        column.setContentsMargins(px(40), px(28), px(40), 0)
        column.setSpacing(px(28))

        check = QLabel()
        check.setFixedSize(px(176), px(176))
        check.setAlignment(Qt.AlignmentFlag.AlignCenter)
        check.setPixmap(icon(ICON_CHECK, px(96), "#FFFFFF", 2.4))
        check.setStyleSheet(f"background: {GREEN}; border-radius: {px(88)}px;")
        column.addWidget(check, alignment=Qt.AlignmentFlag.AlignHCenter)

        title = QLabel("Plaćanje je uspjelo")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(f"font-size: {px(68)}px; font-weight: 800;")
        column.addWidget(title)
        thanks = QLabel("Hvala što kupujete u Penny.")
        thanks.setAlignment(Qt.AlignmentFlag.AlignCenter)
        thanks.setStyleSheet(f"font-size: {px(32)}px; color: {MUTED_TEXT};")
        column.addWidget(thanks)

        column.addWidget(self._summary())

        printing = QHBoxLayout()
        printing.setSpacing(px(14))
        printing.addStretch()
        printer = QLabel()
        printer.setPixmap(icon(ICON_PRINTER, px(32), MUTED_TEXT))
        printing.addWidget(printer)
        self.printing_text = QLabel("Račun se štampa ispod ekrana")
        self.printing_text.setWordWrap(True)
        self.printing_text.setStyleSheet(f"font-size: {px(26)}px; font-weight: 600; color: {MUTED_TEXT};")
        printing.addWidget(self.printing_text)
        printing.addStretch()
        column.addLayout(printing)
        column.addStretch()
        return body

    def _summary(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("summary")
        frame.setStyleSheet(f"#summary {{ background: white; border-radius: {px(44)}px; }}")
        column = QVBoxLayout(frame)
        column.setContentsMargins(px(40), px(36), px(40), px(36))
        column.setSpacing(px(22))

        self.count_value = self._summary_row(column, "Broj artikala")
        self.method_value = self._summary_row(column, "Način plaćanja")
        self.number_value = self._summary_row(column, "Račun br.")

        divider = QFrame()
        divider.setFixedHeight(px(2))
        divider.setStyleSheet(f"background: {LINE};")
        column.addWidget(divider)

        row = QHBoxLayout()
        label = QLabel("Plaćeno")
        label.setStyleSheet(f"font-size: {px(30)}px; font-weight: 700;")
        row.addWidget(label, alignment=Qt.AlignmentFlag.AlignBottom)
        row.addStretch()
        self.paid_value = QLabel()
        self.paid_value.setStyleSheet(f"font-size: {px(68)}px; font-weight: 800;")
        row.addWidget(self.paid_value)
        column.addLayout(row)
        return frame

    def _summary_row(self, column: QVBoxLayout, title: str) -> QLabel:
        row = QHBoxLayout()
        label = QLabel(title)
        label.setStyleSheet(f"font-size: {px(28)}px; font-weight: 600; color: {MUTED_TEXT};")
        row.addWidget(label)
        row.addStretch()
        value = QLabel()
        value.setStyleSheet(f"font-size: {px(30)}px; font-weight: 800;")
        row.addWidget(value)
        column.addLayout(row)
        return value

    def _footer(self) -> QWidget:
        footer = QWidget()
        column = QVBoxLayout(footer)
        column.setContentsMargins(px(40), px(26), px(40), px(40))
        column.setSpacing(px(16))

        self.retry_button = QPushButton("Pokušaj ponovo")
        self.retry_button.setFixedHeight(px(112))
        self.retry_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.retry_button.setStyleSheet(
            f"QPushButton {{ background: white; color: {TEXT}; border: {px(3)}px solid {LINE}; border-radius: {px(56)}px;"
            f" font-size: {px(40)}px; font-weight: 800; }}"
            f"QPushButton:pressed {{ background: {BACKGROUND}; }}"
        )
        self.retry_button.clicked.connect(self._print_fiscal)
        self.retry_button.setVisible(False)
        column.addWidget(self.retry_button)

        finish = QPushButton("Gotovo")
        finish.setFixedHeight(px(112))
        finish.setCursor(Qt.CursorShape.PointingHandCursor)
        finish.setStyleSheet(
            f"QPushButton {{ background: {GREEN}; color: white; border: none; border-radius: {px(56)}px;"
            f" font-size: {px(44)}px; font-weight: 800; }}"
            f"QPushButton:pressed {{ background: #2C5C14; }}"
        )
        finish.clicked.connect(self._finish)
        column.addWidget(finish)

        self.countdown_label = QLabel()
        self.countdown_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.countdown_label.setStyleSheet(f"font-size: {px(24)}px; font-weight: 600; color: {MUTED_TEXT};")
        column.addWidget(self.countdown_label)
        return footer

import threading

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from cart import Cart
from formatting import format_amount
from printec import APPROVED, DECLINED, FAILED, PENDING, RETRY, UNREACHABLE, PrintecClient, amount_minor
from screens.components import TopBar
from styles import (
    BACKGROUND,
    BORDER,
    DARK_GREEN,
    FONT,
    GREEN,
    ICON_CARD,
    LIGHT_GREEN,
    MUTED_TEXT,
    TEXT,
    icon,
    px,
)

TEXTS = {
    "card": ("Platite karticom", "Prislonite ili ubacite karticu na terminal ispod ekrana."),
    "qr": ("Platite QR kodom", "Otvorite bankarsku aplikaciju i skenirajte kod."),
}


class PaymentWaitScreen(QWidget):
    cancelled = Signal()
    staff_requested = Signal()
    paid = Signal(object)
    result_ready = Signal(object)

    def __init__(self, cart: Cart, method: str) -> None:
        super().__init__()
        self.cart = cart
        self.method = method
        self.settings = None
        self.invoice_id = ""
        self.in_progress = False
        self.must_retry = False
        self.result_ready.connect(self._on_result)
        self.setObjectName("root")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"#root {{ background: {BACKGROUND}; font-family: {FONT}; color: {TEXT}; }}")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        top_bar = TopBar()
        top_bar.staff_requested.connect(self.staff_requested.emit)
        layout.addWidget(top_bar)
        layout.addWidget(self._body(), stretch=1)
        layout.addWidget(self._footer())

    @property
    def locked(self) -> bool:
        return self.in_progress or self.must_retry

    @property
    def live(self) -> bool:
        return self.method == "card" and self.settings is not None and not self.settings.demo_payments

    @property
    def demo(self) -> bool:
        return self.settings is not None and self.settings.demo_payments

    def begin(self, settings=None, invoice_id: str = "") -> None:
        self.settings = settings
        self.total_label.setText(f"{format_amount(self.cart.total)} KM")
        if self.method != "card":
            self.simulate_button.setVisible(self.demo)
            return
        if invoice_id != self.invoice_id:
            self.must_retry = False
        self.invoice_id = invoice_id
        if self.live:
            self._start_payment()
        else:
            self._show_state("Čekam karticu…", "Demo način: terminal se ne koristi.", cancel=True, retry=False)
            self.simulate_button.setVisible(True)

    def _show_state(self, title: str, detail: str, cancel: bool, retry: bool, problem: bool = False) -> None:
        background, text = ("#FDE8EA", "#B8101F") if problem else (LIGHT_GREEN, DARK_GREEN)
        self.card_panel.setStyleSheet(f"#panel {{ background: {background}; border-radius: {px(56)}px; }}")
        self.state_title.setStyleSheet(f"font-size: {px(42)}px; font-weight: 800; color: {text};")
        self.state_detail.setStyleSheet(f"font-size: {px(26)}px; font-weight: 600; color: {text};")
        self.state_title.setText(title)
        self.state_detail.setText(detail)
        self.cancel_button.setVisible(cancel)
        self.retry_button.setVisible(retry)
        self.simulate_button.setVisible(False)

    def _start_payment(self) -> None:
        self.in_progress = True
        self._show_state("Čekam karticu…", "Pratite poruke na terminalu. Za odustajanje pritisnite Cancel na terminalu.", cancel=False, retry=False)
        client = PrintecClient(self.settings.terminal_url, self.settings.terminal_api_key)
        invoice_id, amount = self.invoice_id, amount_minor(self.cart.total)
        print_slip, copies = self.settings.terminal_print_slip, self.settings.terminal_slip_copies

        def job() -> None:
            self.result_ready.emit(client.purchase(invoice_id, amount, print_slip, max(1, copies)))

        threading.Thread(target=job, daemon=True).start()

    def _on_result(self, result) -> None:
        self.in_progress = False
        self.must_retry = result.outcome in (RETRY, PENDING)
        detail = result.message
        if result.outcome == APPROVED:
            self.paid.emit({**result.data, "invoice_id": self.invoice_id})
        elif result.outcome == DECLINED:
            self._show_state("Plaćanje nije uspjelo", detail or "Kartica je odbijena.", cancel=True, retry=True, problem=True)
        elif result.outcome == RETRY:
            self._show_state("Terminal nije odgovorio", "Pozovite osoblje da provjeri terminal, pa pokušajte ponovo.", cancel=False, retry=True, problem=True)
        elif result.outcome == PENDING:
            self._show_state("Plaćanje mora provjeriti osoblje", "Ne plaćajte ponovo. Osoblje provjerava terminal.", cancel=False, retry=False, problem=True)
        elif result.outcome == UNREACHABLE:
            self._show_state("Terminal nije dostupan", "Ništa nije naplaćeno. Pozovite osoblje.", cancel=True, retry=True, problem=True)
        else:
            self._show_state("Greška u postavkama terminala", detail, cancel=True, retry=False, problem=True)

    def _simulate_paid(self) -> None:
        if self.demo:
            self.paid.emit({})

    def _retry(self) -> None:
        if self.live:
            self._start_payment()

    def _body(self) -> QWidget:
        body = QWidget()
        column = QVBoxLayout(body)
        column.setContentsMargins(px(40), px(20), px(40), 0)
        column.setSpacing(px(28))

        title_text, subtitle_text = TEXTS[self.method]
        title = QLabel(title_text)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(f"font-size: {px(64)}px; font-weight: 800;")
        column.addWidget(title)
        subtitle = QLabel(subtitle_text)
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet(f"font-size: {px(30)}px; color: {MUTED_TEXT};")
        column.addWidget(subtitle)

        column.addWidget(self._amount())
        panel = self._card_panel() if self.method == "card" else self._qr_panel()
        self.card_panel = panel
        column.addWidget(panel, stretch=1)
        return body

    def _amount(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("amount")
        frame.setFixedHeight(px(150))
        frame.setStyleSheet(f"#amount {{ background: white; border-radius: {px(40)}px; }}")
        row = QHBoxLayout(frame)
        row.setContentsMargins(px(40), 0, px(40), 0)
        label = QLabel("Za platiti")
        label.setStyleSheet(f"font-size: {px(28)}px; font-weight: 700; color: {MUTED_TEXT};")
        row.addWidget(label)
        row.addStretch()
        self.total_label = QLabel()
        self.total_label.setStyleSheet(f"font-size: {px(76)}px; font-weight: 800;")
        row.addWidget(self.total_label)
        return frame

    def _card_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("panel")
        panel.setStyleSheet(f"#panel {{ background: {LIGHT_GREEN}; border-radius: {px(56)}px; }}")
        column = QVBoxLayout(panel)
        column.setSpacing(px(34))
        column.addStretch()

        rings = QWidget()
        rings.setFixedSize(px(340), px(340))
        outer = QFrame(rings)
        outer.setGeometry(0, 0, px(340), px(340))
        outer.setStyleSheet(f"border: {px(4)}px solid rgba(60, 122, 30, 46); border-radius: {px(170)}px;")
        inner = QFrame(rings)
        inner.setGeometry(px(36), px(36), px(268), px(268))
        inner.setStyleSheet(f"border: {px(4)}px solid rgba(60, 122, 30, 82); border-radius: {px(134)}px;")
        center = QLabel(rings)
        center.setGeometry(px(85), px(85), px(170), px(170))
        center.setAlignment(Qt.AlignmentFlag.AlignCenter)
        center.setPixmap(icon(ICON_CARD, px(92), "#FFFFFF", 1.6))
        center.setStyleSheet(f"background: {GREEN}; border-radius: {px(85)}px;")
        column.addWidget(rings, alignment=Qt.AlignmentFlag.AlignHCenter)

        self.state_title = QLabel("Čekam karticu…")
        self.state_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.state_title.setWordWrap(True)
        self.state_title.setStyleSheet(f"font-size: {px(42)}px; font-weight: 800; color: {DARK_GREEN};")
        column.addWidget(self.state_title)
        self.state_detail = QLabel("Pratite poruke na terminalu")
        self.state_detail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.state_detail.setWordWrap(True)
        self.state_detail.setContentsMargins(px(30), 0, px(30), 0)
        self.state_detail.setStyleSheet(f"font-size: {px(26)}px; font-weight: 600; color: {DARK_GREEN};")
        column.addWidget(self.state_detail)
        column.addStretch()
        return panel

    def _qr_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("panel")
        panel.setStyleSheet(f"#panel {{ background: white; border-radius: {px(56)}px; }}")
        column = QVBoxLayout(panel)
        column.setSpacing(px(30))
        column.addStretch()

        self.qr_label = QLabel("mjesto za QR kod")
        self.qr_label.setFixedSize(px(420), px(420))
        self.qr_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.qr_label.setStyleSheet(
            f"border: {px(4)}px solid {TEXT}; border-radius: {px(36)}px;"
            f" font-size: {px(24)}px; font-weight: 700; color: {MUTED_TEXT};"
        )
        column.addWidget(self.qr_label, alignment=Qt.AlignmentFlag.AlignHCenter)

        waiting = QLabel("Čekam potvrdu uplate…")
        waiting.setAlignment(Qt.AlignmentFlag.AlignCenter)
        waiting.setStyleSheet(f"font-size: {px(30)}px; font-weight: 700;")
        column.addWidget(waiting)
        column.addStretch()
        return panel

    def _footer(self) -> QWidget:
        footer = QWidget()
        column = QVBoxLayout(footer)
        column.setContentsMargins(px(40), px(26), px(40), px(40))
        column.setSpacing(px(14))

        self.retry_button = QPushButton("Pokušaj ponovo")
        self.retry_button.setFixedHeight(px(100))
        self.retry_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.retry_button.setStyleSheet(
            f"QPushButton {{ background: {GREEN}; color: white; border: none;"
            f" border-radius: {px(50)}px; font-size: {px(32)}px; font-weight: 800; }}"
        )
        self.retry_button.clicked.connect(self._retry)
        self.retry_button.setVisible(False)
        column.addWidget(self.retry_button)

        self.cancel_button = QPushButton("Odustani i vrati se na izbor")
        self.cancel_button.setFixedHeight(px(100))
        self.cancel_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_button.setStyleSheet(
            f"QPushButton {{ background: white; color: {TEXT}; border: {px(3)}px solid {BORDER};"
            f" border-radius: {px(50)}px; font-size: {px(28)}px; font-weight: 800; }}"
            f"QPushButton:pressed {{ background: {BACKGROUND}; }}"
        )
        self.cancel_button.clicked.connect(self.cancelled.emit)
        column.addWidget(self.cancel_button)

        self.simulate_button = QPushButton("Prototip: plaćanje je uspjelo →")
        self.simulate_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.simulate_button.setStyleSheet(
            f"QPushButton {{ background: transparent; border: none; color: {MUTED_TEXT};"
            f" font-size: {px(22)}px; font-weight: 600; padding: {px(6)}px; }}"
        )
        self.simulate_button.clicked.connect(self._simulate_paid)
        self.simulate_button.setVisible(False)
        column.addWidget(self.simulate_button)
        return footer

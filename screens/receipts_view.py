from datetime import date, datetime, timedelta

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from formatting import format_amount, item_count_text, receipt_count_text
from receipts import ReceiptStore
from styles import BACKGROUND, BORDER, DARK_RED, GREEN, MUTED_TEXT, TEXT, px

PAYMENT_METHOD_NAMES = {"card": "Kartica", "qr": "QR kod"}


def fiscal_text(receipt: dict) -> str:
    if receipt.get("fiscal_printed"):
        return f"BF {receipt['fiscal_number']}" if receipt.get("fiscal_number") else "fiskalni odštampan"
    if receipt.get("fiscal_message"):
        return "fiskalni NIJE odštampan"
    return "bez fiskalnog"


class ReceiptsView(QWidget):
    """Pregled prethodnih računa po danima; klik na račun prikazuje stavke."""

    closed = Signal()

    def __init__(self, store: ReceiptStore | None) -> None:
        super().__init__()
        self.store = store
        self.day = date.today()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.pages = QStackedWidget()
        self.list_page = self._list_page()
        self.detail_page = self._detail_page()
        self.pages.addWidget(self.list_page)
        self.pages.addWidget(self.detail_page)
        layout.addWidget(self.pages)

    def begin(self) -> None:
        self.day = date.today()
        self._load()
        self.pages.setCurrentWidget(self.list_page)

    def _list_page(self) -> QWidget:
        page = QWidget()
        column = QVBoxLayout(page)
        column.setContentsMargins(px(40), px(10), px(40), px(30))
        column.setSpacing(px(14))
        title = QLabel("Prethodni računi")
        title.setStyleSheet(f"font-size: {px(56)}px; font-weight: 800;")
        column.addWidget(title)

        days = QHBoxLayout()
        days.setSpacing(px(14))
        previous = self._button("‹ Prethodni dan")
        previous.clicked.connect(lambda: self._move(-1))
        days.addWidget(previous)
        self.day_label = QLabel()
        self.day_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.day_label.setStyleSheet(f"font-size: {px(30)}px; font-weight: 800;")
        days.addWidget(self.day_label, stretch=1)
        self.next_button = self._button("Sljedeći dan ›")
        self.next_button.clicked.connect(lambda: self._move(1))
        days.addWidget(self.next_button)
        column.addLayout(days)

        self.summary = QLabel()
        self.summary.setWordWrap(True)
        self.summary.setStyleSheet(f"font-size: {px(24)}px; font-weight: 600; color: {MUTED_TEXT};")
        column.addWidget(self.summary)

        self.rows = QVBoxLayout()
        column.addWidget(self._scroll(self.rows), stretch=1)

        close = self._button("Zatvori")
        close.clicked.connect(self.closed.emit)
        column.addWidget(close)
        return page

    def _detail_page(self) -> QWidget:
        page = QWidget()
        column = QVBoxLayout(page)
        column.setContentsMargins(px(40), px(10), px(40), px(30))
        column.setSpacing(px(14))
        self.detail_title = QLabel()
        self.detail_title.setStyleSheet(f"font-size: {px(48)}px; font-weight: 800;")
        column.addWidget(self.detail_title)
        self.detail_info = QLabel()
        self.detail_info.setWordWrap(True)
        self.detail_info.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.detail_info.setStyleSheet(f"font-size: {px(24)}px; color: {MUTED_TEXT};")
        column.addWidget(self.detail_info)
        self.detail_rows = QVBoxLayout()
        column.addWidget(self._scroll(self.detail_rows), stretch=1)
        self.detail_total = QLabel()
        self.detail_total.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.detail_total.setStyleSheet(f"font-size: {px(44)}px; font-weight: 800;")
        column.addWidget(self.detail_total)
        back = self._button("Nazad na listu")
        back.clicked.connect(lambda: self.pages.setCurrentWidget(self.list_page))
        column.addWidget(back)
        return page

    def _scroll(self, rows: QVBoxLayout) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollArea > QWidget > QWidget { background: transparent; }"
        )
        content = QWidget()
        content.setLayout(rows)
        rows.setContentsMargins(0, 0, 0, 0)
        rows.setSpacing(px(10))
        rows.addStretch()
        scroll.setWidget(content)
        return scroll

    def _button(self, text: str) -> QPushButton:
        button = QPushButton(text)
        button.setFixedHeight(px(76))
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setStyleSheet(
            f"QPushButton {{ background: white; color: {TEXT}; border: {px(3)}px solid {BORDER};"
            f" border-radius: {px(38)}px; font-size: {px(24)}px; font-weight: 800; padding: 0 {px(20)}px; }}"
            f"QPushButton:pressed {{ background: {BACKGROUND}; }}"
            f"QPushButton:disabled {{ color: {BORDER}; }}"
        )
        return button

    def _clear(self, rows: QVBoxLayout) -> None:
        while rows.count() > 1:
            widget = rows.takeAt(0).widget()
            if widget is not None:
                widget.deleteLater()

    def _move(self, days: int) -> None:
        self.day = min(date.today(), self.day + timedelta(days=days))
        self._load()

    def _load(self) -> None:
        self.day_label.setText("Danas" if self.day == date.today() else f"{self.day:%d.%m.%Y.}")
        self.next_button.setEnabled(self.day < date.today())
        receipts = self.store.receipts_on(self.day) if self.store is not None else []
        self._clear(self.rows)
        if not receipts:
            empty = QLabel("Nema računa za ovaj dan.")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setFixedHeight(px(100))
            empty.setStyleSheet(f"font-size: {px(26)}px; color: {MUTED_TEXT};")
            self.rows.insertWidget(0, empty)
        for position, receipt in enumerate(receipts):
            self.rows.insertWidget(position, self._receipt_row(receipt))
        totals = {}
        for receipt in receipts:
            totals[receipt["payment_method"]] = totals.get(receipt["payment_method"], 0.0) + receipt["total"]
        parts = [receipt_count_text(len(receipts)), f"ukupno {format_amount(sum(totals.values()))} KM"]
        parts += [f"{PAYMENT_METHOD_NAMES.get(method, method)} {format_amount(total)} KM" for method, total in sorted(totals.items())]
        unprinted = sum(1 for receipt in receipts if not receipt.get("fiscal_printed") and receipt.get("fiscal_message"))
        if unprinted:
            parts.append(f"{unprinted} bez fiskalnog računa")
        self.summary.setText(" · ".join(parts))

    def _receipt_row(self, receipt: dict) -> QPushButton:
        when = receipt["created_at"][11:16]
        method = PAYMENT_METHOD_NAMES.get(receipt["payment_method"], receipt["payment_method"])
        failed = not receipt.get("fiscal_printed") and receipt.get("fiscal_message")
        row = QPushButton(
            f"{when}   {receipt['number']}   {format_amount(receipt['total'])} KM\n"
            f"{item_count_text(receipt['item_count'])} · {method} · {fiscal_text(receipt)}"
        )
        row.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        row.setFixedHeight(px(110))
        row.setCursor(Qt.CursorShape.PointingHandCursor)
        row.setStyleSheet(
            f"QPushButton {{ background: white; color: {DARK_RED if failed else TEXT}; border: none;"
            f" border-radius: {px(30)}px; font-size: {px(24)}px; font-weight: 700; text-align: left; padding: 0 {px(24)}px; }}"
            f"QPushButton:pressed {{ background: {BORDER}; }}"
        )
        row.clicked.connect(lambda _checked=False: self.show_receipt(receipt))
        return row

    def show_receipt(self, receipt: dict) -> None:
        self.detail_title.setText(f"Račun {receipt['number']}")
        info = [
            datetime.fromisoformat(receipt["created_at"]).strftime("%d.%m.%Y. u %H:%M:%S"),
            f"Plaćanje: {PAYMENT_METHOD_NAMES.get(receipt['payment_method'], receipt['payment_method'])}",
            f"Fiskalni račun: {fiscal_text(receipt)}",
        ]
        if receipt.get("card_number"):
            info.append(f"Kartica: {receipt['card_number']}")
        if receipt.get("approval_code"):
            info.append(f"Autorizacija: {receipt['approval_code']}")
        if receipt.get("rrn"):
            info.append(f"RRN: {receipt['rrn']}")
        self.detail_info.setText("\n".join(info))
        self._clear(self.detail_rows)
        for position, item in enumerate(self.store.items(receipt["number"]) if self.store is not None else []):
            self.detail_rows.insertWidget(position, self._item_row(item))
        self.detail_total.setText(f"Ukupno {format_amount(receipt['total'])} KM")
        self.pages.setCurrentWidget(self.detail_page)

    def _item_row(self, item: dict) -> QFrame:
        row = QFrame()
        row.setObjectName("row")
        row.setFixedHeight(px(90))
        row.setStyleSheet(f"#row {{ background: white; border-radius: {px(26)}px; }}")
        layout = QHBoxLayout(row)
        layout.setContentsMargins(px(24), 0, px(24), 0)
        name = QLabel(f"{item['name']}\n{item['quantity']} × {format_amount(item['price'])} KM · {item['barcode']}")
        name.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        name.setStyleSheet(f"font-size: {px(22)}px; font-weight: 700;")
        layout.addWidget(name, stretch=1)
        amount = QLabel(f"{format_amount(item['amount'])} KM")
        amount.setStyleSheet(f"font-size: {px(26)}px; font-weight: 800; color: {GREEN};")
        layout.addWidget(amount)
        return row

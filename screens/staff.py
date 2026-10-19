from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from cart import Cart
from formatting import format_amount, item_count_text
from screens.components import TopBar
from staff_auth import StaffPinMissing, check_pin
from styles import (
    BACKGROUND,
    BORDER,
    DARK_RED,
    FONT,
    GREEN,
    ICON_MINUS,
    ICON_PLUS,
    ICON_TRASH,
    LIGHT_RED,
    MUTED_TEXT,
    RED,
    TEXT,
    icon,
    px,
)

PIN_LENGTH = 8


class StaffScreen(QWidget):
    closed = Signal()
    approve_requested = Signal()
    forgive_requested = Signal()
    settings_requested = Signal()

    def __init__(self, cart: Cart) -> None:
        super().__init__()
        self.cart = cart
        self.entered = ""
        self.setObjectName("root")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"#root {{ background: {BACKGROUND}; font-family: {FONT}; color: {TEXT}; }}")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(TopBar(show_staff=False))
        self.pages = QStackedWidget()
        self.pin_page = self._pin_page()
        self.panel_page = self._panel_page()
        self.pages.addWidget(self.pin_page)
        self.pages.addWidget(self.panel_page)
        layout.addWidget(self.pages, stretch=1)

    def begin(self, can_approve: bool = False, unscanned: int = 0) -> None:
        self.approve_button.setVisible(can_approve)
        self.forgive_button.setVisible(unscanned > 0)
        self.forgive_button.setText(f"Poništi neskenirana uzimanja ({unscanned})")
        self.entered = ""
        self.pin_error.setText("")
        self._update_pin_display()
        self.pages.setCurrentWidget(self.pin_page)

    def _pin_page(self) -> QWidget:
        page = QWidget()
        column = QVBoxLayout(page)
        column.setContentsMargins(px(40), px(20), px(40), px(40))
        column.setSpacing(px(24))

        title = QLabel("Osoblje je pozvano")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(f"font-size: {px(64)}px; font-weight: 800;")
        column.addWidget(title)
        subtitle = QLabel("Molimo sačekajte, neko iz osoblja dolazi.")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet(f"font-size: {px(30)}px; color: {MUTED_TEXT};")
        column.addWidget(subtitle)

        self.pin_display = QLabel()
        self.pin_display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.pin_display.setFixedHeight(px(110))
        self.pin_display.setStyleSheet(
            f"background: white; border-radius: {px(36)}px; font-size: {px(48)}px; font-weight: 800; letter-spacing: {px(12)}px;"
        )
        column.addWidget(self.pin_display)

        self.pin_error = QLabel()
        self.pin_error.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.pin_error.setStyleSheet(f"font-size: {px(26)}px; font-weight: 700; color: {DARK_RED};")
        column.addWidget(self.pin_error)

        keypad = QGridLayout()
        keypad.setSpacing(px(16))
        keys = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "Obriši", "0", "OK"]
        for index, key in enumerate(keys):
            button = self._key_button(key)
            keypad.addWidget(button, index // 3, index % 3)
        column.addLayout(keypad, stretch=1)

        cancel = QPushButton("Odustani")
        cancel.setFixedHeight(px(96))
        cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel.setStyleSheet(self._outline_style(BORDER, TEXT))
        cancel.clicked.connect(self.closed.emit)
        column.addWidget(cancel)
        return page

    def _key_button(self, key: str) -> QPushButton:
        button = QPushButton(key)
        button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        button.setMinimumHeight(px(110))
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        if key == "OK":
            style = (
                f"QPushButton {{ background: {GREEN}; color: white; border: none; border-radius: {px(36)}px;"
                f" font-size: {px(40)}px; font-weight: 800; }}"
                f"QPushButton:pressed {{ background: #2C5C14; }}"
            )
        else:
            size = px(30) if key == "Obriši" else px(48)
            style = (
                f"QPushButton {{ background: white; color: {TEXT}; border: none; border-radius: {px(36)}px;"
                f" font-size: {size}px; font-weight: 800; }}"
                f"QPushButton:pressed {{ background: {BORDER}; }}"
            )
        button.setStyleSheet(style)
        button.clicked.connect(lambda _checked=False: self._on_key(key))
        return button

    def _on_key(self, key: str) -> None:
        if key == "Obriši":
            self.entered = self.entered[:-1]
        elif key == "OK":
            self._submit_pin()
            return
        elif len(self.entered) < PIN_LENGTH:
            self.entered += key
        self.pin_error.setText("")
        self._update_pin_display()

    def _update_pin_display(self) -> None:
        self.pin_display.setText("●" * len(self.entered) if self.entered else "Unesite PIN")

    def _submit_pin(self) -> None:
        try:
            valid = check_pin(self.entered)
        except StaffPinMissing as error:
            self.pin_error.setText(str(error))
            return
        self.entered = ""
        self._update_pin_display()
        if not valid:
            self.pin_error.setText("Pogrešan PIN")
            return
        self._refresh_panel()
        self.pages.setCurrentWidget(self.panel_page)

    def _panel_page(self) -> QWidget:
        page = QWidget()
        column = QVBoxLayout(page)
        column.setContentsMargins(px(40), px(20), px(40), px(40))
        column.setSpacing(px(20))

        title = QLabel("Način rada za osoblje")
        title.setStyleSheet(f"font-size: {px(56)}px; font-weight: 800;")
        column.addWidget(title)
        self.panel_summary = QLabel()
        self.panel_summary.setStyleSheet(f"font-size: {px(28)}px; font-weight: 600; color: {MUTED_TEXT};")
        column.addWidget(self.panel_summary)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollArea > QWidget > QWidget { background: transparent; }"
        )
        content = QWidget()
        self.panel_rows = QVBoxLayout(content)
        self.panel_rows.setContentsMargins(0, 0, 0, 0)
        self.panel_rows.setSpacing(px(12))
        self.panel_rows.addStretch()
        scroll.setWidget(content)
        column.addWidget(scroll, stretch=1)

        extra = QHBoxLayout()
        extra.setSpacing(px(18))
        self.approve_button = QPushButton("Odobri skenirani artikal")
        self.approve_button.setFixedHeight(px(96))
        self.approve_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.approve_button.setStyleSheet(self._outline_style(GREEN, GREEN))
        self.approve_button.clicked.connect(self._on_approve)
        extra.addWidget(self.approve_button, stretch=1)
        self.forgive_button = QPushButton("Poništi neskenirana uzimanja")
        self.forgive_button.setFixedHeight(px(96))
        self.forgive_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.forgive_button.setStyleSheet(self._outline_style(BORDER, TEXT))
        self.forgive_button.clicked.connect(self._on_forgive)
        self.forgive_button.setVisible(False)
        extra.addWidget(self.forgive_button, stretch=1)
        settings = QPushButton("Postavke")
        settings.setFixedHeight(px(96))
        settings.setCursor(Qt.CursorShape.PointingHandCursor)
        settings.setStyleSheet(self._outline_style(BORDER, TEXT))
        settings.clicked.connect(self.settings_requested.emit)
        extra.addWidget(settings)
        column.addLayout(extra)

        buttons = QHBoxLayout()
        buttons.setSpacing(px(18))
        clear = QPushButton("Poništi korpu")
        clear.setFixedHeight(px(108))
        clear.setCursor(Qt.CursorShape.PointingHandCursor)
        clear.setStyleSheet(self._outline_style(RED, DARK_RED, LIGHT_RED))
        clear.clicked.connect(self._on_clear)
        buttons.addWidget(clear, stretch=1)

        done = QPushButton("Zatvori")
        done.setFixedHeight(px(108))
        done.setCursor(Qt.CursorShape.PointingHandCursor)
        done.setStyleSheet(
            f"QPushButton {{ background: {GREEN}; color: white; border: none; border-radius: {px(54)}px;"
            f" font-size: {px(40)}px; font-weight: 800; }}"
            f"QPushButton:pressed {{ background: #2C5C14; }}"
        )
        done.clicked.connect(self.closed.emit)
        buttons.addWidget(done, stretch=1)
        column.addLayout(buttons)
        return page

    def _refresh_panel(self) -> None:
        data = self.cart.to_dict()
        while self.panel_rows.count() > 1:
            widget = self.panel_rows.takeAt(0).widget()
            if widget is not None:
                widget.deleteLater()
        if not data["items"]:
            empty = QLabel("Korpa je prazna.")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setFixedHeight(px(100))
            empty.setStyleSheet(f"font-size: {px(26)}px; color: {MUTED_TEXT};")
            self.panel_rows.insertWidget(0, empty)
        for position, item in enumerate(data["items"]):
            self.panel_rows.insertWidget(position, self._panel_row(item))
        self.panel_summary.setText(f"{item_count_text(data['item_count'])} · {format_amount(data['total'])} KM")

    def _panel_row(self, item: dict) -> QFrame:
        row = QFrame()
        row.setObjectName("row")
        row.setFixedHeight(px(100))
        row.setStyleSheet(f"#row {{ background: white; border-radius: {px(30)}px; }}")
        layout = QHBoxLayout(row)
        layout.setContentsMargins(px(24), 0, px(24), 0)
        layout.setSpacing(px(14))

        name = QLabel(item["name"])
        name.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        name.setStyleSheet(f"font-size: {px(28)}px; font-weight: 700;")
        layout.addWidget(name, stretch=1)

        code = item["code"]
        layout.addWidget(self._round_button(ICON_MINUS, TEXT, lambda _checked=False: self._change(code, -1)))
        quantity = QLabel(str(item["quantity"]))
        quantity.setFixedWidth(px(44))
        quantity.setAlignment(Qt.AlignmentFlag.AlignCenter)
        quantity.setStyleSheet(f"font-size: {px(30)}px; font-weight: 800;")
        layout.addWidget(quantity)
        layout.addWidget(self._round_button(ICON_PLUS, TEXT, lambda _checked=False: self._change(code, 1)))
        layout.addWidget(self._round_button(ICON_TRASH, DARK_RED, lambda _checked=False: self._remove(code)))
        return row

    def _round_button(self, shape: str, color: str, handler) -> QPushButton:
        button = QPushButton()
        button.setFixedSize(px(56), px(56))
        button.setIcon(QIcon(icon(shape, px(26), color, 2.2)))
        button.setIconSize(QSize(px(26), px(26)))
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setStyleSheet(
            f"QPushButton {{ background: white; border: {px(2)}px solid {BORDER}; border-radius: {px(28)}px; }}"
            f"QPushButton:pressed {{ background: {BACKGROUND}; }}"
        )
        button.clicked.connect(handler)
        return button

    def _outline_style(self, border: str, color: str, pressed: str = BACKGROUND) -> str:
        return (
            f"QPushButton {{ background: white; color: {color}; border: {px(3)}px solid {border};"
            f" border-radius: {px(48)}px; font-size: {px(28)}px; font-weight: 800; }}"
            f"QPushButton:pressed {{ background: {pressed}; }}"
        )

    def _change(self, code: str, delta: int) -> None:
        self.cart.change_quantity(code, delta)
        self._refresh_panel()

    def _remove(self, code: str) -> None:
        self.cart.remove(code)
        self._refresh_panel()

    def _on_approve(self) -> None:
        self.approve_button.setVisible(False)
        self.approve_requested.emit()
        self.closed.emit()

    def _on_forgive(self) -> None:
        self.forgive_button.setVisible(False)
        self.forgive_requested.emit()
        self.closed.emit()

    def _on_clear(self) -> None:
        self.cart.clear()
        self._refresh_panel()

import os
import threading
from dataclasses import fields, replace

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from fiscal import FiscalPrinter
from printec import PrintecClient
from qr_slip import print_gate_slip
from screens.components import PinPad, TopBar
from screens.receipts_view import ReceiptsView
from settings import Settings
from staff_auth import check_admin_pin
from styles import BACKGROUND, BORDER, FONT, GREEN, MUTED_TEXT, TEXT, px

SECTIONS = [
    ("Kasa", ["register_id", "fullscreen", "demo_payments", "receipt_return_seconds", "idle_seconds"]),
    ("Artikli i barkodovi (centralni server)", ["db_server", "db_port", "db_name", "db_user", "db_password", "article_sync_minutes"]),
    ("Kartični terminal (PrintecECR)", ["terminal_url", "terminal_api_key", "terminal_print_slip", "terminal_slip_copies"]),
    ("Fiskalni printer (Tring)", ["fiscal_enabled", "fiscal_url", "fiscal_unit", "fiscal_tax_label", "fiscal_card_payment", "fiscal_qr_payment"]),
    ("QR slip za vrata (test)", ["qr_slip_enabled", "qr_slip_printer", "qr_slip_ibfm"]),
    ("Kamere", ["cameras_enabled", "allow_without_cameras", "lock_on_moved_camera", "yolox_enabled", "alarm_clips", "customer_monitor", "customer_monitor_camera", "vision_server_url", "camera_a_host", "camera_a2_host", "camera_a3_host", "camera_b_host", "camera_b2_host", "camera_b3_host", "camera_c_host", "camera_c2_host", "camera_channel", "camera_model", "match_threshold", "reference_min_percent", "label_reading"]),
]

LABELS = {
    "register_id": "Oznaka kase",
    "fullscreen": "Cijeli ekran (nakon ponovnog pokretanja)",
    "demo_payments": "Demo plaćanje (bez terminala)",
    "receipt_return_seconds": "Povratak na početak nakon računa (s)",
    "idle_seconds": "Pitaj 'Jeste li još tu?' poslije neaktivnosti (s, 0 = isključeno)",
    "article_sync_minutes": "Sinhronizacija artikala svakih (min, 0 = isključeno)",
    "db_server": "Adresa servera (IP ili ime)",
    "db_port": "Port",
    "db_name": "Baza",
    "db_user": "Korisnik",
    "db_password": "Lozinka",
    "terminal_url": "Adresa servisa",
    "terminal_api_key": "API ključ",
    "terminal_print_slip": "Štampaj slip kartice",
    "terminal_slip_copies": "Broj kopija slipa",
    "fiscal_enabled": "Štampaj fiskalni račun",
    "fiscal_url": "Adresa printera",
    "fiscal_unit": "Jedinica mjere",
    "fiscal_tax_label": "Poreska stopa",
    "fiscal_card_payment": "Oznaka plaćanja karticom",
    "fiscal_qr_payment": "Oznaka plaćanja QR kodom",
    "qr_slip_enabled": "Štampaj slip s QR kodom za vrata poslije fiskalnog računa",
    "qr_slip_printer": "Ime Windows printera za slip (prazno = zadani printer)",
    "qr_slip_ibfm": "IBFM u QR kodu",
    "cameras_enabled": "Kamere uključene",
    "yolox_enabled": "Brojanje artikala (YOLOX)",
    "lock_on_moved_camera": "Zaključaj kasu kad se kamera pomjeri",
    "alarm_clips": "Snimci kod alarma (8 s prije i 5 s poslije, čuvaju se 30 dana)",
    "customer_monitor": "Ekran 'Snimate se' prema kupcu (drugi monitor)",
    "customer_monitor_camera": "Kamera za ekran prema kupcu",
    "allow_without_cameras": "Dozvoli rad kase kad kamere ne rade (bez provjere kamerama)",
    "vision_server_url": "Adresa servera kamera (prazno = kamere na ovom računaru)",
    "camera_a_host": "IP kamere A (korpa)",
    "camera_a2_host": "IP druge kamere A (prazno = nema)",
    "camera_a3_host": "IP bočne kamere A (prazno = nema)",
    "camera_b_host": "IP kamere B (odlaganje)",
    "camera_b2_host": "IP druge kamere B (prazno = nema)",
    "camera_b3_host": "IP bočne kamere B (prazno = nema)",
    "camera_c_host": "IP kamere C (praćenje kupca, prazno = nema)",
    "camera_c2_host": "IP druge kamere C (prazno = nema)",
    "camera_channel": "Kanal (101 ili 102)",
    "camera_model": "AI model",
    "match_threshold": "Prag sličnosti (0 = iz .env ili zadano)",
    "label_reading": "Čitaj tekst sa etikete artikla (OCR)",
    "reference_min_percent": "Slika se pamti za učenje ako artikal liči bar (%)",
}

CHOICES = {"camera_model": ["dinov2", "dinov2-base", "clip", "mobilenet"], "customer_monitor_camera": ["C", "C2", "A", "A2", "A3", "B", "B2", "B3"]}
SECRET = {"terminal_api_key", "db_password"}


class SettingsScreen(QWidget):
    closed = Signal()
    saved = Signal(object)
    restart_requested = Signal(object)
    quit_requested = Signal(object)
    sync_requested = Signal(object)
    test_finished = Signal(str)

    def __init__(self, settings: Settings, store=None) -> None:
        super().__init__()
        self.settings = settings
        self.editors: dict[str, QWidget] = {}
        self.setObjectName("root")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"#root {{ background: {BACKGROUND}; font-family: {FONT}; color: {TEXT}; }}")
        self.test_finished.connect(self._show_test_result)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(TopBar(show_staff=False))
        self.pages = QStackedWidget()
        self.pin = PinPad("Postavke", "Unesite administratorsku šifru.", check_admin_pin)
        self.pin.accepted.connect(self._open_form)
        self.pin.cancelled.connect(self.closed.emit)
        self.form_page = self._form_page()
        self.receipts_page = ReceiptsView(store)
        self.receipts_page.closed.connect(lambda: self.pages.setCurrentWidget(self.form_page))
        self.pages.addWidget(self.pin)
        self.pages.addWidget(self.form_page)
        self.pages.addWidget(self.receipts_page)
        layout.addWidget(self.pages, stretch=1)

    def begin(self, settings: Settings) -> None:
        self.settings = settings
        self.pin.reset()
        self.pages.setCurrentWidget(self.pin)

    def _open_form(self) -> None:
        for name, editor in self.editors.items():
            self._write(editor, getattr(self.settings, name))
        self.status.setText("")
        self.pages.setCurrentWidget(self.form_page)

    def _form_page(self) -> QWidget:
        page = QWidget()
        column = QVBoxLayout(page)
        column.setContentsMargins(px(40), px(10), px(40), px(30))
        column.setSpacing(px(12))
        title = QLabel("Postavke")
        title.setStyleSheet(f"font-size: {px(56)}px; font-weight: 800;")
        column.addWidget(title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollArea > QWidget > QWidget { background: transparent; }"
        )
        content = QWidget()
        sections = QVBoxLayout(content)
        sections.setSpacing(px(18))
        types = {item.name: type(getattr(self.settings, item.name)) for item in fields(Settings)}
        for heading, names in SECTIONS:
            sections.addWidget(self._section(heading, names, types))
        sections.addStretch()
        scroll.setWidget(content)
        column.addWidget(scroll, stretch=1)

        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.setStyleSheet(f"font-size: {px(24)}px; color: {MUTED_TEXT};")
        column.addWidget(self.status)

        receipts = self._button("Pregledaj prethodne račune", primary=False)
        receipts.clicked.connect(self._show_receipts)
        column.addWidget(receipts)

        tests = QHBoxLayout()
        tests.setSpacing(px(14))
        terminal_test = self._button("Testiraj terminal", primary=False)
        terminal_test.clicked.connect(self._test_terminal)
        tests.addWidget(terminal_test)
        printer_test = self._button("Testiraj printer", primary=False)
        printer_test.clicked.connect(self._test_printer)
        tests.addWidget(printer_test)
        column.addLayout(tests)
        sync_now = self._button("Sinhronizuj artikle odmah", primary=False)
        sync_now.clicked.connect(self._sync_now)
        column.addWidget(sync_now)
        slip_test = self._button("Testiraj QR slip", primary=False)
        slip_test.clicked.connect(self._test_qr_slip)
        column.addWidget(slip_test)
        cameras_test = self._button("Testiraj kamere", primary=False)
        cameras_test.clicked.connect(self._test_cameras)
        column.addWidget(cameras_test)

        actions = QHBoxLayout()
        actions.setSpacing(px(14))
        close = self._button("Zatvori", primary=False)
        close.clicked.connect(self.closed.emit)
        actions.addWidget(close)
        save = self._button("Spremi", primary=True)
        save.clicked.connect(self._save)
        actions.addWidget(save)
        column.addLayout(actions)
        restart = self._button("Spremi i restartuj aplikaciju", primary=False)
        restart.clicked.connect(self._save_and_restart)
        column.addWidget(restart)
        quit_button = self._button("Spremi i ugasi aplikaciju", primary=False)
        quit_button.clicked.connect(self._save_and_quit)
        column.addWidget(quit_button)
        return page

    def _section(self, heading: str, names: list[str], types: dict) -> QFrame:
        frame = QFrame()
        frame.setObjectName("section")
        frame.setStyleSheet(f"#section {{ background: white; border-radius: {px(30)}px; }}")
        column = QVBoxLayout(frame)
        column.setContentsMargins(px(28), px(22), px(28), px(22))
        title = QLabel(heading)
        title.setStyleSheet(f"font-size: {px(30)}px; font-weight: 800;")
        column.addWidget(title)
        form = QFormLayout()
        form.setVerticalSpacing(px(12))
        form.setHorizontalSpacing(px(20))
        for name in names:
            editor = self._editor(name, types[name])
            self.editors[name] = editor
            label = QLabel(LABELS.get(name, name))
            label.setWordWrap(True)
            label.setStyleSheet(f"font-size: {px(24)}px; color: {MUTED_TEXT};")
            form.addRow(label, editor)
        column.addLayout(form)
        return frame

    def _editor(self, name: str, kind: type) -> QWidget:
        font = f"font-size: {px(24)}px; min-height: {px(56)}px;"
        if kind is bool:
            editor = QCheckBox()
            editor.setStyleSheet(f"QCheckBox::indicator {{ width: {px(40)}px; height: {px(40)}px; }}")
        elif kind is int:
            editor = QSpinBox()
            editor.setRange(0, 3600)
        elif kind is float:
            editor = QDoubleSpinBox()
            editor.setRange(0.0, 1.0)
            editor.setSingleStep(0.05)
            editor.setDecimals(2)
        elif name in CHOICES:
            editor = QComboBox()
            editor.addItems(CHOICES[name])
        else:
            editor = QLineEdit()
            if name in SECRET:
                editor.setEchoMode(QLineEdit.EchoMode.Password)
        if kind is not bool:
            editor.setStyleSheet(f"{font} padding: 0 {px(12)}px; border: {px(2)}px solid {BORDER}; border-radius: {px(14)}px; background: white;")
        return editor

    def _write(self, editor: QWidget, value) -> None:
        if isinstance(editor, QCheckBox):
            editor.setChecked(bool(value))
        elif isinstance(editor, (QSpinBox, QDoubleSpinBox)):
            editor.setValue(value)
        elif isinstance(editor, QComboBox):
            editor.setCurrentText(str(value))
        else:
            editor.setText(str(value))

    def _read(self, editor: QWidget):
        if isinstance(editor, QCheckBox):
            return editor.isChecked()
        if isinstance(editor, (QSpinBox, QDoubleSpinBox)):
            return editor.value()
        if isinstance(editor, QComboBox):
            return editor.currentText()
        return editor.text().strip()

    def current(self) -> Settings:
        return replace(self.settings, **{name: self._read(editor) for name, editor in self.editors.items()})

    def _button(self, text: str, primary: bool) -> QPushButton:
        button = QPushButton(text)
        button.setFixedHeight(px(76))
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        if primary:
            style = f"background: {GREEN}; color: white; border: none;"
        else:
            style = f"background: white; color: {TEXT}; border: {px(3)}px solid {BORDER};"
        button.setStyleSheet(
            f"QPushButton {{ {style} border-radius: {px(38)}px; font-size: {px(26)}px; font-weight: 800; }}"
        )
        return button

    def _save(self) -> None:
        self.settings = self.current()
        self.saved.emit(self.settings)
        self.status.setText("Postavke su spremljene.")

    def _save_and_restart(self) -> None:
        self.settings = self.current()
        self.restart_requested.emit(self.settings)

    def _save_and_quit(self) -> None:
        self.settings = self.current()
        self.quit_requested.emit(self.settings)

    def _show_receipts(self) -> None:
        self.receipts_page.begin()
        self.pages.setCurrentWidget(self.receipts_page)

    def _sync_now(self) -> None:
        self.status.setText("Povlačim artikle sa servera...")
        self.sync_requested.emit(self.current())

    def _run_test(self, job) -> None:
        self.status.setText("Provjeravam...")
        threading.Thread(target=lambda: self.test_finished.emit(job()), daemon=True).start()

    def _test_terminal(self) -> None:
        settings = self.current()

        def job() -> str:
            try:
                data = PrintecClient(settings.terminal_url, settings.terminal_api_key).status()
            except Exception as error:
                return f"Terminal: servis nije dostupan ({error})."
            terminal = data.get("terminal") or {}
            if data.get("payment_in_progress"):
                return "Terminal: plaćanje je u toku."
            if terminal.get("ready"):
                return f"Terminal: spreman ({terminal.get('status_text', '')})."
            return f"Terminal: servis radi, terminal nije spreman ({terminal.get('status_text') or terminal.get('error') or '-'})."

        self._run_test(job)

    def _test_printer(self) -> None:
        settings = self.current()
        self._run_test(lambda: "Printer: " + FiscalPrinter(settings.fiscal_url).reachable().message)

    def _test_qr_slip(self) -> None:
        settings = self.current()

        def job() -> str:
            try:
                print_gate_slip(settings.qr_slip_ibfm, "000000", 0.0, settings.qr_slip_printer)
            except Exception as error:
                return f"QR slip: nije odštampan ({error})."
            return "QR slip: poslano na printer (testni BF 000000, vrata ga ne prihvataju)."

        self._run_test(job)

    def _test_cameras(self) -> None:
        url = self.current().vision_server_url
        token = os.environ.get("CAM_SERVER_TOKEN", "")

        def job() -> str:
            if not url:
                return "Kamere: nema adrese servera, kamere rade na ovom računaru."
            if not token:
                return "Kamere: upišite CAM_SERVER_TOKEN u .env."
            from remote_guard import RemoteGuard

            return "Kamere: " + RemoteGuard(url, token).ping()

        self._run_test(job)

    def _show_test_result(self, text: str) -> None:
        self.status.setText(text)

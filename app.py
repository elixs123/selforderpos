import os
import sys
from datetime import datetime
from pathlib import Path

if getattr(sys, "frozen", False):
    import faulthandler
    import traceback

    try:
        LOG_FILE = open(Path(sys.executable).resolve().parent / "kasa.log", "a", encoding="utf-8", buffering=1)
    except OSError:
        LOG_FILE = open(Path(os.environ.get("TEMP", ".")) / "kasa.log", "a", encoding="utf-8", buffering=1)
    LOG_FILE.write(f"\n=== Pokretanje {datetime.now():%Y-%m-%d %H:%M:%S} ===\n")
    faulthandler.enable(LOG_FILE)
    try:
        os.dup2(LOG_FILE.fileno(), 2)
    except OSError:
        pass
    sys.stdout = sys.stderr = LOG_FILE
    sys.excepthook = lambda kind, value, trace: LOG_FILE.write("".join(traceback.format_exception(kind, value, trace)))
    plugins = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)) / "PySide6" / "plugins"
    os.environ["QT_PLUGIN_PATH"] = str(plugins)
    os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = str(plugins / "platforms")
    os.environ.setdefault("QT_DEBUG_PLUGINS", "1")

from PySide6.QtCore import QStandardPaths
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QApplication, QMainWindow, QMessageBox, QStackedWidget

from cart import Cart
from fiscal import FiscalOptions, FiscalPrinter
from receipts import ReceiptStore
from screens.drop import DropScreen
from screens.payment import PaymentScreen
from screens.receipt import ReceiptScreen
from screens.scan import ScanScreen
from screens.settings import SettingsScreen
from screens.staff import StaffScreen
from screens.terminal import PaymentWaitScreen
from screens.welcome import WelcomeScreen
from settings import Settings, load_settings, save_settings
import styles
from styles import apply_light_theme, px


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Penny samouslužna kasa")
        self.settings_path = data_folder() / "settings.json"
        self.settings = load_settings(self.settings_path)
        if not self.settings.fullscreen:
            self.setFixedSize(px(820), px(1360))
        self.store = ReceiptStore(database_path())
        self.cart = Cart()
        self.guard = None
        self.diagnostics = None
        self.sale_id = ""

        self.screens = QStackedWidget()
        self.setCentralWidget(self.screens)

        self.welcome = WelcomeScreen()
        self.scan = ScanScreen(self.cart)
        self.drop = DropScreen()
        self.payment = PaymentScreen(self.cart)
        self.card = PaymentWaitScreen(self.cart, "card")
        self.qr = PaymentWaitScreen(self.cart, "qr")
        self.receipt = ReceiptScreen(self.cart)
        self.staff = StaffScreen(self.cart)
        self.settings_screen = SettingsScreen(self.settings)
        for screen in (self.welcome, self.scan, self.drop, self.payment, self.card, self.qr,
                       self.receipt, self.staff, self.settings_screen):
            self.screens.addWidget(screen)

        self.welcome.started.connect(self.start_shopping)
        self.scan.pay_requested.connect(self.show_payment)
        self.scan.place_requested.connect(self.show_drop)
        self.drop.accepted.connect(self.item_accepted)
        self.drop.rejected.connect(self.item_rejected)
        self.payment.back_requested.connect(self.back_to_scan)
        self.payment.card_selected.connect(lambda: self.show_waiting(self.card))
        self.payment.qr_selected.connect(lambda: self.show_waiting(self.qr))
        self.card.cancelled.connect(self.show_payment)
        self.qr.cancelled.connect(self.show_payment)
        self.card.paid.connect(lambda payment: self.show_receipt("card", payment))
        self.qr.paid.connect(lambda payment: self.show_receipt("qr", payment))
        self.receipt.done.connect(self.finish_shopping)
        for screen in (self.scan, self.drop, self.payment, self.card, self.qr):
            screen.staff_requested.connect(self.show_staff)
        self.staff.closed.connect(self.back_to_scan)
        self.staff.approve_requested.connect(self.approve_item)
        self.staff.forgive_requested.connect(self.forgive_unscanned)
        self.staff.settings_requested.connect(self.show_settings)
        self.settings_screen.saved.connect(self.apply_settings)
        self.settings_screen.closed.connect(self.close_settings)

        shortcut = QShortcut(QKeySequence("Ctrl+Shift+S"), self)
        shortcut.activated.connect(self.show_settings)
        quit_shortcut = QShortcut(QKeySequence("Ctrl+Shift+Q"), self)
        quit_shortcut.activated.connect(self.close)
        diagnostics_shortcut = QShortcut(QKeySequence("Ctrl+Shift+D"), self)
        diagnostics_shortcut.activated.connect(self.open_diagnostics)
        self.start_cameras()

    def start_cameras(self) -> None:
        if self.guard is not None:
            self.guard.stop()
            self.guard = None
        if self.settings.cameras_enabled:
            try:
                from camera_service import start_guard, start_remote_guard

                if self.settings.vision_server_url:
                    self.guard = start_remote_guard(self.settings)
                else:
                    self.guard = start_guard(self.settings)
                if "--debug" in sys.argv and not self.settings.vision_server_url:
                    from locations import app_folder

                    self.guard.enable_debug(app_folder() / "data" / "debug" / datetime.now().strftime("%Y%m%d-%H%M%S"))
            except Exception as error:
                print(f"Kamere nisu pokrenute: {error}")
        self.scan.guard = self.guard

    def open_diagnostics(self) -> None:
        if getattr(self.guard, "remote", False):
            QMessageBox.information(
                self, "Dijagnostika",
                "Kamere rade na drugom računaru. Dijagnostika se otvara tamo: python vision_server.py --monitor",
            )
            return
        if self.diagnostics is None:
            from screens.diagnostics import DiagnosticsWindow

            self.diagnostics = DiagnosticsWindow(lambda: self.guard)
        self.diagnostics.show()
        self.diagnostics.raise_()

    def start_shopping(self) -> None:
        self.sale_id = f"{self.settings.register_id}-{datetime.now():%Y%m%d-%H%M%S}"
        self.screens.setCurrentWidget(self.scan)
        self.scan.begin()

    def show_drop(self, product, seen_outcome: int) -> None:
        self.screens.setCurrentWidget(self.drop)
        self.drop.begin(product, self.guard, seen_outcome)

    def item_accepted(self, product) -> None:
        self.screens.setCurrentWidget(self.scan)
        self.scan.add_accepted(product)
        self.scan.resume()

    def item_rejected(self, message: str) -> None:
        self.screens.setCurrentWidget(self.scan)
        self.scan.resume()
        self.scan.show_rejected(message)

    def approve_item(self) -> None:
        if self.guard is not None:
            self.guard.approve()

    def forgive_unscanned(self) -> None:
        if self.guard is not None and hasattr(self.guard, "forgive_unscanned"):
            self.guard.forgive_unscanned()

    def show_payment(self) -> None:
        if self.guard is not None and getattr(self.guard, "unscanned", 0) > 0:
            return
        self.screens.setCurrentWidget(self.payment)
        self.payment.begin()

    def back_to_scan(self) -> None:
        if self.card.locked:
            self.screens.setCurrentWidget(self.card)
            return
        if self.drop.waiting:
            self.screens.setCurrentWidget(self.drop)
            self.drop.resume()
            return
        self.screens.setCurrentWidget(self.scan)
        self.scan.resume()

    def show_waiting(self, screen: PaymentWaitScreen) -> None:
        self.screens.setCurrentWidget(screen)
        screen.begin(self.settings, self.sale_id)

    def show_receipt(self, payment_method: str, payment: dict) -> None:
        number = self.store.save(self.cart, payment_method, payment)
        self.screens.setCurrentWidget(self.receipt)
        self.receipt.begin(payment_method, number, self.fiscal_job(number, payment_method), self.settings.receipt_return_seconds)

    def fiscal_job(self, number: str, payment_method: str):
        if not self.settings.fiscal_enabled:
            return None
        settings = self.settings
        options = FiscalOptions(settings.fiscal_unit, settings.fiscal_tax_label, settings.fiscal_card_payment, settings.fiscal_qr_payment)
        printer = FiscalPrinter(settings.fiscal_url, options)
        receipt_id = self.store.receipt_id(number)
        cart_data = self.cart.to_dict()
        store = self.store

        def job():
            result = printer.print_receipt(receipt_id, cart_data, payment_method)
            store.mark_fiscal(number, result.ok, result.message)
            return result

        return job

    def show_staff(self) -> None:
        guard = self.guard
        can_approve = guard is not None and self.drop.waiting and (guard.busy or guard.state in ("mismatch", "timeout", "offline"))
        self.screens.setCurrentWidget(self.staff)
        self.staff.begin(can_approve, getattr(guard, "unscanned", 0) if guard is not None else 0)

    def show_settings(self) -> None:
        self.screens.setCurrentWidget(self.settings_screen)
        self.settings_screen.begin(self.settings)

    def apply_settings(self, settings: Settings) -> None:
        cameras_changed = any(
            getattr(settings, name) != getattr(self.settings, name)
            for name in ("cameras_enabled", "camera_a_host", "camera_a2_host", "camera_b_host", "camera_b2_host", "camera_channel", "camera_model", "match_threshold")
        )
        self.settings = settings
        save_settings(settings, self.settings_path)
        if cameras_changed:
            self.start_cameras()

    def close_settings(self) -> None:
        if self.cart.item_count or self.drop.waiting or self.card.locked:
            self.back_to_scan()
        else:
            self.screens.setCurrentWidget(self.welcome)

    def finish_shopping(self) -> None:
        self.cart.clear()
        self.screens.setCurrentWidget(self.welcome)

    def closeEvent(self, event) -> None:
        if self.diagnostics is not None:
            self.diagnostics.close()
        if self.guard is not None:
            self.guard.stop()
        super().closeEvent(event)


def data_folder() -> Path:
    return Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation))


def database_path() -> Path:
    custom = os.environ.get("KASA_DB")
    if custom:
        return Path(custom)
    return data_folder() / "kasa.db"


def main() -> None:
    print(f"Python {sys.version}, Qt plugini: {os.environ.get('QT_QPA_PLATFORM_PLUGIN_PATH', '-')}")
    application = QApplication(sys.argv)
    application.setOrganizationName("Penny")
    application.setApplicationName("selforderpos")
    apply_light_theme(application)
    if load_settings(data_folder() / "settings.json").fullscreen:
        size = application.primaryScreen().size()
        styles.SCALE = min(size.width() / 820, size.height() / 1360)
        window = MainWindow()
        window.showFullScreen()
    else:
        window = MainWindow()
        window.show()
    if "--monitor" in sys.argv:
        window.open_diagnostics()
    sys.exit(application.exec())


if __name__ == "__main__":
    main()

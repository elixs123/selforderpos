import os
import sys
import threading
import time
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

from PySide6.QtCore import QProcess, QStandardPaths, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QApplication, QInputDialog, QLineEdit, QMainWindow, QMessageBox, QStackedWidget

import catalog
import database
import gate_api
from articles import ArticleStore
from camera_check import cameras_problem
from cart import Cart
from fiscal import FiscalOptions, FiscalPrinter, FiscalResult
from qr_slip import print_gate_slip
from receipts import ReceiptStore
from screens.cameras_down import CamerasDownScreen
from screens.customer_monitor import CustomerMonitor
from screens.drop import DropScreen
from screens.idle import ActivityFilter, IdleOverlay
from screens.payment import PaymentScreen
from screens.receipt import ReceiptScreen
from screens.scan import ScanScreen, payment_allowed
from screens.settings import SettingsScreen
from screens.staff import StaffScreen
from screens.terminal import PaymentWaitScreen
from screens.unpaid import UnpaidScreen
from screens.welcome import WelcomeScreen
from settings import Settings, load_settings, save_settings
from staff_auth import PinError, check_admin_pin
import styles
from styles import apply_light_theme, px


CAMERAS_DOWN_SECONDS = 10
EXIT_WATCH_SECONDS = 120
IDLE_COUNTDOWN_SECONDS = 30


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Penny samouslužna kasa")
        self.settings_path = data_folder() / "settings.json"
        self.settings = load_settings(self.settings_path)
        if not self.settings.fullscreen:
            self.setFixedSize(px(820), px(1360))
        self.configure_database()
        self.store = ReceiptStore(database_path())
        self.articles = ArticleStore(database_path())
        catalog.use_local_store(self.articles)
        self.article_timer = QTimer(self)
        self.article_timer.timeout.connect(self.sync_articles)
        self.gate_server = self.start_gate_api()
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
        self.settings_screen = SettingsScreen(self.settings, self.store)
        self.cameras_down = CamerasDownScreen()
        self.unpaid = UnpaidScreen()
        self.exit_watch: dict | None = None
        for screen in (self.welcome, self.scan, self.drop, self.payment, self.card, self.qr,
                       self.receipt, self.staff, self.settings_screen, self.cameras_down, self.unpaid):
            self.screens.addWidget(screen)

        self.welcome.started.connect(self.start_shopping)
        self.scan.pay_requested.connect(self.show_payment)
        self.scan.quit_requested.connect(self.close)
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
        self.staff.cleared.connect(self.cancel_shopping)
        self.staff.approve_requested.connect(self.approve_item)
        self.staff.learn_requested.connect(self.learn_item)
        self.staff.forgive_requested.connect(self.forgive_unscanned)
        self.staff.settings_requested.connect(self.show_settings)
        self.staff.reprint_requested.connect(self.reprint_fiscal)
        self.settings_screen.saved.connect(self.apply_settings)
        self.settings_screen.restart_requested.connect(self.restart_app)
        self.settings_screen.quit_requested.connect(self.quit_app)
        self.settings_screen.closed.connect(self.close_settings)
        self.settings_screen.sync_requested.connect(self.sync_now)
        self.cameras_down.settings_requested.connect(self.show_settings)
        self.cameras_down_since: float | None = None
        self.camera_timer = QTimer(self)
        self.camera_timer.timeout.connect(self.check_cameras)
        self.camera_timer.timeout.connect(self.check_exit)
        self.camera_timer.timeout.connect(self.check_idle)
        self.last_activity = time.monotonic()
        self.activity_filter = ActivityFilter(self.mark_activity)
        QApplication.instance().installEventFilter(self.activity_filter)
        self.idle_overlay = IdleOverlay(self)
        self.idle_overlay.stay.connect(self.mark_activity)
        self.unpaid.pay_requested.connect(self.pay_for_unpaid)
        self.unpaid.staff_requested.connect(self.show_staff)
        self.camera_timer.start(1000)

        shortcut = QShortcut(QKeySequence("Ctrl+Shift+S"), self)
        shortcut.activated.connect(self.show_settings)
        quit_shortcut = QShortcut(QKeySequence("Ctrl+Shift+Q"), self)
        quit_shortcut.activated.connect(self.request_quit)
        diagnostics_shortcut = QShortcut(QKeySequence("Ctrl+Shift+D"), self)
        diagnostics_shortcut.activated.connect(self.request_diagnostics)
        self.customer_monitor = None
        self.start_cameras()
        self.start_article_sync()
        QTimer.singleShot(2000, self.sync_articles)

    def check_cameras(self) -> None:
        """Kad kamere ne rade duže od CAMERAS_DOWN_SECONDS, kasa se zaključa dok ih administrator ne dozvoli isključiti."""
        self.scan.allow_without_cameras = self.settings.allow_without_cameras
        problem = "" if self.settings.allow_without_cameras else cameras_problem(self.guard, self.settings.cameras_enabled, self.settings.lock_on_moved_camera)
        current = self.screens.currentWidget()
        if not problem:
            self.cameras_down_since = None
            if current is self.cameras_down:
                self.close_settings()
            return
        if self.cameras_down_since is None:
            self.cameras_down_since = time.monotonic()
        self.cameras_down.show_reason(problem)
        if time.monotonic() - self.cameras_down_since < CAMERAS_DOWN_SECONDS:
            return
        if current in (self.welcome, self.scan, self.drop, self.payment):
            print(f"Kasa zaključana, kamere ne rade: {problem}")
            self.screens.setCurrentWidget(self.cameras_down)

    def check_exit(self) -> None:
        """Poslije plaćanja (dok kupac ne prođe vrata): neskeniran artikal blokira QR za vrata i prikaže 'Niste sve platili'."""
        watch, guard = self.exit_watch, self.guard
        if watch is None or guard is None:
            return
        unpaid = getattr(guard, "unscanned", 0) > 0
        guess = getattr(guard, "unscanned_guess", "")
        if not watch["blocked"]:
            if time.monotonic() - watch["since"] > EXIT_WATCH_SECONDS or self.store.gate_used(watch["number"]):
                self.exit_watch = None
                return
            if not unpaid:
                return
            watch["blocked"], watch["guess"] = True, guess
            self.store.block_gate(watch["number"], guess)
            print(f"Račun {watch['number']}: poslije plaćanja uzet neplaćen artikal ({guess or 'nije prepoznat'}), vrata blokirana")
            if hasattr(guard, "record_clip"):
                guard.record_clip("Niste sve platili")
        elif not unpaid and self.cart.item_count:
            # artikal je skeniran u novoj kupovini: stari račun ostaje blokiran, vrata otvara tek novi (plaćeni) račun
            self.exit_watch = None
            return
        elif not unpaid:
            self.store.unblock_gate(watch["number"])
            print(f"Račun {watch['number']}: neplaćen artikal vraćen ili riješen, vrata otključana")
            self.exit_watch = None
            if self.screens.currentWidget() is self.unpaid:
                self.screens.setCurrentWidget(self.welcome)
            return
        elif guess and guess != watch["guess"]:
            watch["guess"] = guess
            self.store.block_gate(watch["number"], guess)
        self.unpaid.show_item(watch["guess"])
        if self.screens.currentWidget() in (self.welcome, self.receipt):
            self.screens.setCurrentWidget(self.unpaid)

    def mark_activity(self) -> None:
        self.last_activity = time.monotonic()

    def check_idle(self) -> None:
        """Kupac ode usred kupovine: poslije idle_seconds pitaj 'Jeste li još tu?', poslije odbrojavanja poništi kupovinu."""
        limit = self.settings.idle_seconds
        current = self.screens.currentWidget()
        if limit <= 0 or current not in (self.scan, self.drop, self.payment):
            self.idle_overlay.hide()
            return
        if getattr(self.guard, "busy", False):
            self.mark_activity()
        idle = time.monotonic() - self.last_activity
        if idle < limit:
            self.idle_overlay.hide()
            return
        if not self.cart.item_count and not self.drop.waiting:
            print("Neaktivnost: prazna korpa, povratak na početak")
            self.cancel_shopping()
            return
        left = round(limit + IDLE_COUNTDOWN_SECONDS - idle)
        if left <= 0:
            self.idle_overlay.hide()
            print(f"Neaktivnost: kupovina poništena ({self.cart.item_count} artikala u korpi)")
            self.cancel_shopping()
            return
        self.idle_overlay.show_countdown(left)

    def pay_for_unpaid(self) -> None:
        """Kupac plaća uzeti artikal u novoj kupovini; stari račun ostaje blokiran, vrata otvara novi račun."""
        self.exit_watch = None
        self.start_shopping()

    def start_article_sync(self) -> None:
        minutes = self.settings.article_sync_minutes
        if minutes > 0:
            self.article_timer.start(minutes * 60 * 1000)
        else:
            self.article_timer.stop()

    def configure_database(self, settings: Settings | None = None) -> None:
        settings = settings or self.settings
        database.configure(settings.db_server, settings.db_port, settings.db_name, settings.db_user, settings.db_password)

    def sync_now(self, settings: Settings) -> None:
        self.configure_database(settings)
        self.sync_articles(report=True)

    def sync_articles(self, report: bool = False) -> None:
        def job() -> None:
            result = self.articles.sync()
            if report:
                text = result.message
                if result.ok:
                    text += f" {result.article_count} artikala, {result.barcode_count} barkodova."
                self.settings_screen.test_finished.emit(text)

        threading.Thread(target=job, daemon=True).start()

    def request_quit(self) -> None:
        if self.settings.demo_payments:
            self.close()
        else:
            self.show_settings()

    def request_diagnostics(self) -> None:
        if self.settings.demo_payments or self.admin_confirmed():
            self.open_diagnostics()

    def admin_confirmed(self) -> bool:
        pin, ok = QInputDialog.getText(self, "Dijagnostika", "Administratorska šifra:", QLineEdit.EchoMode.Password)
        if not ok:
            return False
        try:
            return check_admin_pin(pin)
        except PinError as error:
            QMessageBox.warning(self, "Dijagnostika", str(error))
            return False

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
        self.start_customer_monitor()

    def start_customer_monitor(self) -> None:
        if self.customer_monitor is not None:
            self.customer_monitor.stop()
            self.customer_monitor.deleteLater()
            self.customer_monitor = None
        if self.guard is None or not self.settings.customer_monitor or not hasattr(self.guard, "latest"):
            return
        monitor = CustomerMonitor(self.guard.latest, self.settings.customer_monitor_camera)
        if monitor.start(allow_main_screen=not self.settings.fullscreen):
            self.customer_monitor = monitor
        else:
            print("Ekran 'Snimate se': drugi monitor nije priključen")
            monitor.deleteLater()

    def start_gate_api(self):
        try:
            server = gate_api.start_from_env(self.store)
        except (OSError, ValueError) as error:
            print(f"Servis za vrata nije pokrenut: {error}")
            return None
        if server is None:
            print("Servis za vrata nije pokrenut: GATE_API_TOKEN nije upisan u .env.")
        return server

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
        if self.exit_watch is not None and not self.exit_watch["blocked"]:
            self.exit_watch = None
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

    def learn_item(self) -> None:
        if self.guard is not None:
            self.guard.approve(learn=True)

    def forgive_unscanned(self) -> None:
        if self.guard is not None and hasattr(self.guard, "forgive_unscanned"):
            self.guard.forgive_unscanned()

    def show_payment(self) -> None:
        if not payment_allowed(self.guard, self.settings.allow_without_cameras):
            return
        self.screens.setCurrentWidget(self.payment)
        self.payment.begin(self.settings.demo_payments)

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
        self.exit_watch = {"number": number, "since": time.monotonic(), "blocked": False, "guess": ""}
        self.screens.setCurrentWidget(self.receipt)
        self.receipt.begin(payment_method, number, self.fiscal_job(number, payment_method), self.settings.receipt_return_seconds)

    def fiscal_job(self, number: str, payment_method: str, cart_data: dict | None = None):
        if not self.settings.fiscal_enabled:
            return None
        settings = self.settings
        options = FiscalOptions(settings.fiscal_unit, settings.fiscal_tax_label, settings.fiscal_card_payment, settings.fiscal_qr_payment)
        printer = FiscalPrinter(settings.fiscal_url, options)
        receipt_id = self.store.receipt_id(number)
        cart_data = cart_data or self.cart.to_dict()
        store = self.store

        def job():
            try:
                result = printer.print_receipt(receipt_id, cart_data, payment_method)
            except Exception as error:
                result = FiscalResult(False, f"Greška pri slanju računa: {error!r}")
            print(f"Fiskalni račun {number}: {'OK' if result.ok else 'NIJE ODŠTAMPAN'} {result.message[:300]}")
            try:
                store.mark_fiscal(number, result.ok, result.message, result.fiscal_number)
            except Exception as error:
                print(f"Fiskalni račun {number}: upis u bazu nije uspio: {error!r}")
            if result.ok and settings.qr_slip_enabled:
                try:
                    if not result.fiscal_number:
                        raise ValueError("printer nije vratio broj fiskalnog računa")
                    print_gate_slip(settings.qr_slip_ibfm, result.fiscal_number, cart_data["total"], settings.qr_slip_printer)
                except Exception as error:
                    print(f"QR slip za vrata {number}: nije odštampan: {error!r}")
            return result

        return job

    def show_staff(self) -> None:
        guard = self.guard
        can_approve = guard is not None and self.drop.waiting and (guard.busy or guard.state in ("mismatch", "timeout", "offline"))
        self.screens.setCurrentWidget(self.staff)
        can_learn = can_approve and guard.state == "mismatch"
        unscanned = getattr(guard, "unscanned", 0) + getattr(guard, "zone_a_left", 0) if guard is not None else 0
        self.staff.begin(can_approve, unscanned, can_learn, self.store.unprinted())

    def reprint_fiscal(self, number: str) -> None:
        receipt = next((row for row in self.store.unprinted() if row["number"] == number), None)
        job = self.fiscal_job(number, receipt["payment_method"], self.store.cart_data(number)) if receipt else None
        if job is None:
            self.staff.reprint_done.emit(number, FiscalResult(False, "Fiskalni printer je isključen u postavkama."))
            return
        threading.Thread(target=lambda: self.staff.reprint_done.emit(number, job()), daemon=True).start()

    def show_settings(self) -> None:
        self.screens.setCurrentWidget(self.settings_screen)
        self.settings_screen.begin(self.settings)

    def apply_settings(self, settings: Settings) -> None:
        cameras_changed = any(
            getattr(settings, name) != getattr(self.settings, name)
            for name in ("cameras_enabled", "yolox_enabled", "alarm_clips", "camera_a_host", "camera_a2_host", "camera_a3_host", "camera_b_host", "camera_b2_host", "camera_b3_host", "camera_c_host", "camera_c2_host", "camera_channel", "camera_model", "match_threshold", "reference_min_percent", "label_reading")
        )
        sync_changed = settings.article_sync_minutes != self.settings.article_sync_minutes
        monitor_changed = (settings.customer_monitor, settings.customer_monitor_camera) != (
            self.settings.customer_monitor, self.settings.customer_monitor_camera)
        self.settings = settings
        save_settings(settings, self.settings_path)
        self.configure_database()
        if sync_changed:
            self.start_article_sync()
        if monitor_changed and not cameras_changed:
            self.start_customer_monitor()
        if cameras_changed:
            self.start_cameras()

    def restart_app(self, settings: Settings) -> None:
        save_settings(settings, self.settings_path)
        arguments = sys.argv[1:] if getattr(sys, "frozen", False) else sys.argv
        self.close()
        QProcess.startDetached(sys.executable, arguments)

    def quit_app(self, settings: Settings) -> None:
        save_settings(settings, self.settings_path)
        self.close()

    def close_settings(self) -> None:
        self.configure_database()
        if self.cart.item_count or self.drop.waiting or self.card.locked:
            self.back_to_scan()
        else:
            self.screens.setCurrentWidget(self.welcome)

    def cancel_shopping(self) -> None:
        if self.guard is not None:
            if self.drop.waiting:
                self.guard.cancel()
            self.guard.forgive_unscanned()
        self.drop.cancel()
        self.cart.clear()
        self.screens.setCurrentWidget(self.welcome)

    def finish_shopping(self) -> None:
        self.cart.clear()
        blocked = self.exit_watch is not None and self.exit_watch["blocked"]
        self.screens.setCurrentWidget(self.unpaid if blocked else self.welcome)

    def closeEvent(self, event) -> None:
        if self.customer_monitor is not None:
            self.customer_monitor.stop()
        if self.diagnostics is not None:
            self.diagnostics.close()
        if self.guard is not None:
            self.guard.stop()
        if self.gate_server is not None:
            self.gate_server.shutdown()
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

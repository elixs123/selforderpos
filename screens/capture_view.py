import threading
import time

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QLabel, QLineEdit, QProgressBar, QPushButton, QSizePolicy, QVBoxLayout, QWidget

from catalog import find_by_barcode
from database import DatabaseError
from styles import BACKGROUND, BORDER, MUTED_TEXT, TEXT, px

POLL_MS = 500
PREVIEW_SECONDS = 0.2
PREVIEW_PAINT_MS = 100
INSTRUCTIONS = (
    "Artikli koje kamere teško prepoznaju (izvještaj 'Problematični artikli') snimaju se ovdje. "
    "Ispraznite zonu B, skenirajte artikal i radite šta kasa kaže: kasa sama slika kad je artikal miran i nema ruke, "
    "pa traži da ga okrenete na drugu stranu. Slike odmah koristi za prepoznavanje i čuva ih u arhivi."
)


class CaptureView(QWidget):
    """Postavke > Snimanje artikla: osoblje uz uputstva kase slika artikal sa svih strana u zoni B."""

    closed = Signal()
    updated = Signal(object)

    def __init__(self, guard_provider=None) -> None:
        super().__init__()
        self.guard_provider = guard_provider or (lambda: None)
        self.active = False
        self._polling = False
        self.updated.connect(self._show_status)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._poll)
        self._showing = False
        self._fetched = False
        self._preview: bytes | None = None
        self._painted: bytes | None = None
        self.preview_timer = QTimer(self)
        self.preview_timer.timeout.connect(self._paint_preview)

        column = QVBoxLayout(self)
        column.setContentsMargins(px(40), px(10), px(40), px(30))
        column.setSpacing(px(16))
        title = QLabel("Snimanje artikla")
        title.setStyleSheet(f"font-size: {px(56)}px; font-weight: 800;")
        column.addWidget(title)
        info = QLabel(INSTRUCTIONS)
        info.setWordWrap(True)
        info.setStyleSheet(f"font-size: {px(22)}px; font-weight: 600; color: {MUTED_TEXT};")
        column.addWidget(info)

        # Kamere zone B uživo: zelena zona i krstić pokazuju gdje staviti artikal.
        self.video = QLabel()
        self.video.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.video.setMinimumHeight(px(320))
        # Ignored: slika se prilagodi prostoru, a ne prostor slici (inače bi ekran rastao sa svakom slikom).
        self.video.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.video.setStyleSheet(f"background: #111; color: white; border-radius: {px(24)}px; font-size: {px(24)}px;")
        column.addWidget(self.video, stretch=3)

        self.barcode_input = QLineEdit()
        self.barcode_input.setPlaceholderText("Skenirajte ili upišite barkod artikla")
        self.barcode_input.setFixedHeight(px(76))
        self.barcode_input.setStyleSheet(
            f"QLineEdit {{ background: white; border: {px(2)}px solid {BORDER}; border-radius: {px(24)}px;"
            f" padding: 0 {px(20)}px; font-size: {px(26)}px; }}")
        self.barcode_input.returnPressed.connect(self._barcode_entered)
        column.addWidget(self.barcode_input)

        self.product = QLabel()
        self.product.setWordWrap(True)
        self.product.setStyleSheet(f"font-size: {px(30)}px; font-weight: 800;")
        column.addWidget(self.product)
        self.progress = QProgressBar()
        self.progress.setFixedHeight(px(40))
        self.progress.setTextVisible(True)
        self.progress.setFormat("%v od %m strana")
        self.progress.setStyleSheet(
            f"QProgressBar {{ background: {BACKGROUND}; border: none; border-radius: {px(20)}px; font-size: {px(20)}px;"
            f" font-weight: 800; text-align: center; }} QProgressBar::chunk {{ background: #2e7d32; border-radius: {px(20)}px; }}")
        column.addWidget(self.progress)
        self.message = QLabel()
        self.message.setWordWrap(True)
        self.message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.message.setStyleSheet(
            f"font-size: {px(36)}px; font-weight: 800; background: white; border-radius: {px(30)}px; padding: {px(30)}px;")
        column.addWidget(self.message, stretch=1)

        self.finish_button = self._button("Završi snimanje")
        self.finish_button.clicked.connect(self.finish)
        column.addWidget(self.finish_button)
        close = self._button("Zatvori")
        close.clicked.connect(self.close_view)
        column.addWidget(close)

    def _button(self, text: str) -> QPushButton:
        button = QPushButton(text)
        button.setFixedHeight(px(76))
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setStyleSheet(
            f"QPushButton {{ background: white; color: {TEXT}; border: {px(3)}px solid {BORDER};"
            f" border-radius: {px(38)}px; font-size: {px(24)}px; font-weight: 800; padding: 0 {px(20)}px; }}"
            f"QPushButton:pressed {{ background: {BACKGROUND}; }} QPushButton:disabled {{ color: {BORDER}; }}")
        return button

    def begin(self) -> None:
        self._idle("Skenirajte artikal koji želite snimiti.")
        self.barcode_input.setFocus()
        self._start_preview()

    def _start_preview(self) -> None:
        self._preview = self._painted = None
        self._fetched = False
        self.video.setPixmap(QPixmap())
        self.video.setText("Kamera se spaja…")
        self.preview_timer.start(PREVIEW_PAINT_MS)
        if self._showing:
            return
        self._showing = True
        threading.Thread(target=self._fetch_preview, daemon=True).start()

    def _fetch_preview(self) -> None:
        # Slika se dohvata u posebnoj niti (server kamera može kasniti), ekran samo crta zadnju.
        while self._showing:
            guard = self.guard_provider()
            try:
                self._preview = guard.capture_preview() if hasattr(guard, "capture_preview") else None
            except Exception:
                self._preview = None
            self._fetched = True
            time.sleep(PREVIEW_SECONDS)

    def _paint_preview(self) -> None:
        data = self._preview
        if data is None:
            text = "Kamere zone B nemaju sliku." if self._fetched else "Kamera se spaja…"
            if self._painted is not None or self.video.text() != text:
                self._painted = None
                self.video.setPixmap(QPixmap())
                self.video.setText(text)
            return
        if data is self._painted:
            return
        self._painted = data
        pixmap = QPixmap.fromImage(QImage.fromData(data))
        self.video.setText("")
        self.video.setPixmap(pixmap.scaled(self.video.size(), Qt.AspectRatioMode.KeepAspectRatio,
                                           Qt.TransformationMode.SmoothTransformation))

    def _idle(self, text: str) -> None:
        self.active = False
        self.timer.stop()
        self.product.setText("")
        self.progress.hide()
        self.finish_button.setEnabled(False)
        self.message.setText(text)

    def _barcode_entered(self) -> None:
        barcode = self.barcode_input.text().strip()
        self.barcode_input.clear()
        if not barcode:
            return
        guard = self.guard_provider()
        if guard is None or not hasattr(guard, "start_capture"):
            self.message.setText("Kamere nisu pokrenute.")
            return
        try:
            product = find_by_barcode(barcode)
        except DatabaseError as error:
            self.message.setText(str(error))
            return
        if product is None:
            self.message.setText(f"Artikal sa barkodom {barcode} nije pronađen.")
            return
        if self.active:
            self._run(lambda: guard.stop_capture())
        self.product.setText(product.name)
        self.message.setText("Pokrećem snimanje…")
        self._run(lambda: guard.start_capture(barcode, product.code, product.name))

    def _run(self, job) -> None:
        def work() -> None:
            try:
                self.updated.emit(job())
            except Exception as error:
                self.updated.emit({"active": False, "message": f"Server kamera ne odgovara ({error})."})

        threading.Thread(target=work, daemon=True).start()

    def _poll(self) -> None:
        guard = self.guard_provider()
        if guard is None or self._polling:
            return
        self._polling = True

        def job() -> dict:
            try:
                return guard.capture_status()
            finally:
                self._polling = False

        self._run(job)

    def _show_status(self, status: dict) -> None:
        message = status.get("message") or ""
        if "target" in status:
            self.progress.setMaximum(max(1, int(status["target"])))
            self.progress.setValue(int(status.get("views", 0)))
            self.progress.show()
        if status.get("product_name"):
            self.product.setText(status["product_name"])
        self.active = bool(status.get("active"))
        self.finish_button.setEnabled(self.active)
        if self.active:
            if not self.timer.isActive():
                self.timer.start(POLL_MS)
        else:
            self.timer.stop()
            if status.get("state") == "done":
                message += " Skenirajte sljedeći artikal."
        self.message.setText(message)
        self.barcode_input.setFocus()

    def finish(self) -> None:
        guard = self.guard_provider()
        if guard is not None and hasattr(guard, "stop_capture"):
            self._run(lambda: {**guard.stop_capture(), "message": "Snimanje završeno. Skenirajte sljedeći artikal."})

    def close_view(self) -> None:
        guard = self.guard_provider()
        self.timer.stop()
        self.preview_timer.stop()
        self._showing = False
        if guard is not None and hasattr(guard, "stop_capture"):
            threading.Thread(target=guard.stop_capture, daemon=True).start()
        self.active = False
        self.closed.emit()

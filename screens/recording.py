import threading
import time

import cv2
from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QImage, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from styles import LINE, MUTED_TEXT, RED, px

FRAME_SECONDS = 0.25
# Slika se dohvata samo dok je neka oznaka na ekranu (inače kasa ne opterećuje server kamera).
WANTED_SECONDS = 2.0


class CameraFeed:
    """Jedna nit dohvata sliku kamere za sve oznake 'Snimate se' (skeniranje, odlaganje, kartica)."""

    def __init__(self) -> None:
        self.source = None
        self.camera = "C"
        self.frame = None
        self.wanted_at = 0.0
        self._thread: threading.Thread | None = None

    @property
    def enabled(self) -> bool:
        return self.source is not None

    def configure(self, source, camera: str) -> None:
        """source: funkcija (kamera) -> slika ili None; None gasi oznaku (Postavke > Kamere)."""
        self.source, self.camera, self.frame = source, camera, None
        if source is not None and self._thread is None:
            self._thread = threading.Thread(target=self._loop, daemon=True)
            self._thread.start()

    def _loop(self) -> None:
        while True:
            source = self.source
            if source is not None and time.monotonic() - self.wanted_at < WANTED_SECONDS:
                try:
                    self.frame = source(self.camera)
                except Exception:
                    self.frame = None
            time.sleep(FRAME_SECONDS)


feed = CameraFeed()


def rounded(frame, width: int, height: int, radius: int) -> QPixmap:
    """Slika kamere kao ogledalo, izrezana na veličinu oznake, sa zaobljenim ćoškovima."""
    rgb = cv2.cvtColor(cv2.flip(frame, 1), cv2.COLOR_BGR2RGB)
    rows, columns = rgb.shape[:2]
    image = QImage(rgb.data, columns, rows, 3 * columns, QImage.Format.Format_RGB888).copy()
    scaled = QPixmap.fromImage(image).scaled(
        width, height, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
    result = QPixmap(width, height)
    result.fill(Qt.GlobalColor.transparent)
    painter = QPainter(result)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, width, height), radius, radius)
    painter.setClipPath(path)
    painter.drawPixmap((width - scaled.width()) // 2, (height - scaled.height()) // 2, scaled)
    painter.end()
    return result


class RecordingBadge(QFrame):
    """Mala živa slika kamere u gornjoj traci: kupac vidi da ga kasa snima."""

    def __init__(self, parent: QWidget) -> None:
        # Sa roditeljem odmah: setVisible bez roditelja bi na tren otvorio poseban prozor.
        super().__init__(parent)
        self.setObjectName("recording")
        self.setFixedHeight(px(96))
        self.setStyleSheet(
            f"#recording {{ background: white; border: {px(2)}px solid {LINE}; border-radius: {px(26)}px; }}")
        row = QHBoxLayout(self)
        row.setContentsMargins(px(8), px(8), px(24), px(8))
        row.setSpacing(px(16))
        self.video = QLabel()
        self.video.setFixedSize(px(144), px(80))
        self.video.setStyleSheet(f"background: #1D2620; border-radius: {px(18)}px;")
        row.addWidget(self.video)
        texts = QVBoxLayout()
        texts.setSpacing(0)
        self.title = QLabel()
        texts.addWidget(self.title)
        note = QLabel("Radi vaše sigurnosti")
        note.setStyleSheet(f"color: {MUTED_TEXT}; font-size: {px(20)}px; border: none;")
        texts.addWidget(note)
        row.addLayout(texts)
        self._blink = 0
        self._show_title()
        self.setVisible(feed.enabled)
        self.timer = QTimer(self)
        self.timer.setInterval(int(FRAME_SECONDS * 1000))
        self.timer.timeout.connect(self._paint)
        self.timer.start()

    def _show_title(self) -> None:
        # Crvena tačka trepće kao na kameri koja snima.
        dot = RED if self._blink < 4 else "white"
        self.title.setText(f"<span style='color:{dot}'>●</span>&nbsp;Snimate se")
        self.title.setStyleSheet(f"color: {RED}; font-size: {px(26)}px; font-weight: 800; border: none;")

    def _paint(self) -> None:
        if self.isHidden() == feed.enabled:
            self.setVisible(feed.enabled)
        # isVisible je False i kad je ekran kase sa ovom trakom sakriven (drugi ekran je prikazan).
        if not feed.enabled or not self.isVisible():
            return
        feed.wanted_at = time.monotonic()
        self._blink = (self._blink + 1) % 6
        self._show_title()
        frame = feed.frame
        if frame is not None and frame.size:
            self.video.setPixmap(rounded(frame, self.video.width(), self.video.height(), px(18)))

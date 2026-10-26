import threading
import time

import cv2
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QGuiApplication, QImage, QPixmap
from PySide6.QtWidgets import QLabel, QSizePolicy, QVBoxLayout, QWidget

from styles import FONT, px

FRAME_SECONDS = 0.2


class CustomerMonitor(QWidget):
    """Drugi monitor prema kupcu: uživo slika kamere (kao ogledalo) i natpis 'Snimate se'."""

    def __init__(self, frame_source, camera: str) -> None:
        super().__init__()
        self.frame_source = frame_source
        self.camera = camera
        self._frame = None
        self._running = False
        self.setWindowTitle("Snimate se")
        self.setStyleSheet(f"background: black; font-family: {FONT};")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        banner = QLabel("●  SNIMATE SE")
        banner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        banner.setStyleSheet(f"background: #D5182A; color: white; font-size: {px(64)}px; font-weight: 800; padding: {px(18)}px;")
        layout.addWidget(banner)
        self.video = QLabel()
        self.video.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.video.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        layout.addWidget(self.video, stretch=1)
        note = QLabel("Radi vaše i naše sigurnosti kasa snima. Hvala što skenirate sve artikle.")
        note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        note.setWordWrap(True)
        note.setStyleSheet(f"background: #16211A; color: white; font-size: {px(30)}px; font-weight: 600; padding: {px(16)}px;")
        layout.addWidget(note)

        self.timer = QTimer(self)
        self.timer.setInterval(int(FRAME_SECONDS * 1000))
        self.timer.timeout.connect(self._paint)

    def start(self, allow_main_screen: bool = False) -> bool:
        """Prikaži na drugom monitoru; bez njega samo kad je dozvoljeno (kasa u prozoru, za probu)."""
        screens = QGuiApplication.screens()
        if len(screens) > 1:
            self.setGeometry(screens[1].geometry())
            self.showFullScreen()
        elif allow_main_screen:
            self.resize(px(960), px(720))
            self.show()
        else:
            return False
        self._running = True
        threading.Thread(target=self._fetch_loop, daemon=True).start()
        self.timer.start()
        return True

    def stop(self) -> None:
        self._running = False
        self.timer.stop()
        self.hide()

    def _fetch_loop(self) -> None:
        # Slika se dohvata u posebnoj niti (server kamera može kasniti), ekran samo crta zadnju.
        while self._running:
            try:
                self._frame = self.frame_source(self.camera)
            except Exception:
                self._frame = None
            time.sleep(FRAME_SECONDS)

    def _paint(self) -> None:
        frame = self._frame
        if frame is None:
            self.video.setText("Kamera se spaja…")
            self.video.setStyleSheet(f"color: white; font-size: {px(36)}px;")
            return
        rgb = cv2.cvtColor(cv2.flip(frame, 1), cv2.COLOR_BGR2RGB)
        height, width = rgb.shape[:2]
        image = QImage(rgb.data, width, height, 3 * width, QImage.Format.Format_RGB888).copy()
        self.video.setPixmap(QPixmap.fromImage(image).scaled(
            self.video.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

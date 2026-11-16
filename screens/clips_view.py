import tempfile
import threading
from datetime import date
from pathlib import Path

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QScroller, QVBoxLayout, QWidget

from styles import BACKGROUND, BORDER, GREEN, LIGHT_GREEN, MUTED_TEXT, TEXT, px

try:
    from PySide6.QtMultimedia import QMediaPlayer
    from PySide6.QtMultimediaWidgets import QVideoWidget
except ImportError:
    # Bez Qt videa (npr. paket bez QtMultimedia) snimak se otvara u plejeru Windowsa.
    QMediaPlayer = QVideoWidget = None

KEEP_DAYS = 7


def clip_title(clip: dict) -> str:
    day = clip.get("day", "")
    try:
        shown = "Danas" if date.fromisoformat(day) == date.today() else f"{date.fromisoformat(day):%d.%m.}"
    except ValueError:
        shown = day
    return f"{shown} {clip.get('time', '')}"


def local_copy(name: str, data: bytes) -> Path:
    """Snimak sa servera kamera u privremeni folder (plejer čita fajl)."""
    folder = Path(tempfile.gettempdir()) / "kasa-snimci"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name.replace("/", "_")
    path.write_bytes(data)
    return path


class ClipsView(QWidget):
    """Snimci alarma (sve kamere, par sekundi prije i poslije alarma); čuvaju se 7 dana na serveru kamera."""

    closed = Signal()
    listed = Signal(object)
    downloaded = Signal(str, str)

    def __init__(self, guard_provider=None) -> None:
        super().__init__()
        self.guard_provider = guard_provider or (lambda: None)
        self.rows: dict[str, QPushButton] = {}
        self.titles: dict[str, str] = {}
        self.current = ""
        self.listed.connect(self._show_list)
        self.downloaded.connect(self._play)
        column = QVBoxLayout(self)
        column.setContentsMargins(px(40), px(10), px(40), px(30))
        column.setSpacing(px(14))
        title = QLabel("Snimci alarma")
        title.setStyleSheet(f"font-size: {px(56)}px; font-weight: 800;")
        column.addWidget(title)
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.setStyleSheet(f"font-size: {px(24)}px; color: {MUTED_TEXT};")
        column.addWidget(self.status)

        self.player = None
        if QMediaPlayer is not None:
            self.video = QVideoWidget()
            self.video.setMinimumHeight(px(420))
            self.video.setStyleSheet("background: black;")
            column.addWidget(self.video, stretch=2)
            self.player = QMediaPlayer(self)
            self.player.setVideoOutput(self.video)
            self.player.errorOccurred.connect(lambda *_: self.status.setText(f"Snimak se ne može pustiti: {self.player.errorString()}"))
            controls = QHBoxLayout()
            controls.setSpacing(px(14))
            again = self._button("Pusti ponovo")
            again.clicked.connect(self._replay)
            controls.addWidget(again)
            outside = self._button("Otvori u plejeru")
            outside.clicked.connect(self._open_outside)
            controls.addWidget(outside)
            column.addLayout(controls)

        self.list_widget = QWidget()
        self.list_layout = QVBoxLayout(self.list_widget)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setSpacing(px(10))
        self.list_layout.addStretch()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; } QScrollArea > QWidget > QWidget { background: transparent; }")
        scroll.setWidget(self.list_widget)
        QScroller.grabGesture(scroll.viewport(), QScroller.ScrollerGestureType.LeftMouseButtonGesture)
        column.addWidget(scroll, stretch=3)

        refresh = self._button("Osvježi listu")
        refresh.clicked.connect(self.begin)
        close = self._button("Zatvori")
        close.clicked.connect(self._close)
        bottom = QHBoxLayout()
        bottom.setSpacing(px(14))
        bottom.addWidget(refresh)
        bottom.addWidget(close)
        column.addLayout(bottom)

    def _button(self, text: str) -> QPushButton:
        button = QPushButton(text)
        button.setFixedHeight(px(76))
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setStyleSheet(
            f"QPushButton {{ background: white; color: {TEXT}; border: {px(3)}px solid {BORDER};"
            f" border-radius: {px(30)}px; font-size: {px(24)}px; font-weight: 800; padding: 0 {px(20)}px; }}"
            f"QPushButton:pressed {{ background: {BACKGROUND}; }}"
        )
        return button

    def begin(self) -> None:
        self.status.setText(f"Učitavam snimke… (čuvaju se {KEEP_DAYS} dana)")
        guard = self.guard_provider()
        if guard is None or not hasattr(guard, "clip_list"):
            self.listed.emit((None, "Kamere nisu pokrenute."))
            return

        def work() -> None:
            try:
                self.listed.emit((guard.clip_list(), ""))
            except Exception as error:
                self.listed.emit((None, f"Server kamera ne odgovara ({error})."))

        threading.Thread(target=work, daemon=True).start()

    def _show_list(self, result) -> None:
        clips, error = result
        while self.list_layout.count() > 1:
            widget = self.list_layout.takeAt(0).widget()
            if widget is not None:
                widget.deleteLater()
        self.rows = {}
        if clips is None:
            self.status.setText(error)
            return
        self.status.setText(f"{len(clips)} snimaka (čuvaju se {KEEP_DAYS} dana). Dodirnite snimak da ga pustite."
                            if clips else f"Nema snimaka alarma u zadnjih {KEEP_DAYS} dana.")
        for position, clip in enumerate(clips):
            button = QPushButton(f"{clip_title(clip)}   {clip.get('reason', '')}")
            button.setMinimumHeight(px(72))
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _=False, name=clip["name"]: self._load(name))
            self.rows[clip["name"]] = button
            self.titles[clip["name"]] = f"{clip_title(clip)}  –  {clip.get('reason', '')}"
            self._mark(button, False)
            self.list_layout.insertWidget(position, button)

    def _mark(self, button: QPushButton, selected: bool) -> None:
        background, border = (LIGHT_GREEN, GREEN) if selected else ("white", BORDER)
        button.setStyleSheet(
            f"QPushButton {{ background: {background}; color: {TEXT}; border: {px(2)}px solid {border};"
            f" border-radius: {px(22)}px; font-size: {px(24)}px; font-weight: 700; text-align: left; padding: 0 {px(24)}px; }}"
        )

    def _load(self, name: str) -> None:
        for clip_name, button in self.rows.items():
            self._mark(button, clip_name == name)
        guard = self.guard_provider()
        if guard is None or not hasattr(guard, "clip_file"):
            return
        self.status.setText("Učitavam snimak…")

        def work() -> None:
            data = guard.clip_file(name)
            if data is None:
                self.downloaded.emit(name, "")
                return
            try:
                self.downloaded.emit(name, str(local_copy(name, data)))
            except OSError:
                self.downloaded.emit(name, "")

        threading.Thread(target=work, daemon=True).start()

    def _play(self, name: str, path: str) -> None:
        if not path:
            self.status.setText("Snimak nije dostupan (možda je već obrisan).")
            return
        self.current = path
        self.status.setText(self.titles.get(name, name))
        if self.player is None:
            self._open_outside()
            return
        self.player.setSource(QUrl.fromLocalFile(path))
        self.player.play()

    def _replay(self) -> None:
        if self.player is not None and self.current:
            self.player.setPosition(0)
            self.player.play()

    def _open_outside(self) -> None:
        if self.current:
            QDesktopServices.openUrl(QUrl.fromLocalFile(self.current))

    def _close(self) -> None:
        if self.player is not None:
            self.player.stop()
        self.closed.emit()

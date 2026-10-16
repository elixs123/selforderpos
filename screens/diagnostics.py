import time
from typing import Callable

import cv2
import numpy as np
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QImage, QPixmap
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton, QVBoxLayout, QWidget,
)

from camera_service import CAMERAS_FOLDER
from locations import app_folder
from zones import to_pixels

TILE_WIDTH = 440
THUMB_SIZE = 150
REFRESH_MS = 150
RED = (60, 60, 235)
GREEN = (80, 200, 80)
YELLOW = (0, 210, 255)
STATE_COLORS = {
    "learning": "#E0A800", "empty": "#8A949C", "ready": "#4CAF50", "taken": "#4CAF50",
    "waiting_take": "#E0A800", "waiting_place": "#3D8BFD", "mismatch": "#E5484D",
    "accepted": "#30A46C", "rejected": "#E5484D", "timeout": "#E5484D",
}
STATE_NAMES = {
    "learning": "UČI POZADINU", "empty": "ZONA A PRAZNA", "ready": "SPREMNO", "taken": "ARTIKAL UZET",
    "waiting_take": "ČEKA UZIMANJE IZ A", "waiting_place": "ČEKA ODLAGANJE U B", "mismatch": "NE ODGOVARA",
    "accepted": "PRIHVAĆENO", "rejected": "ODBIJENO", "timeout": "ISTEKLO VRIJEME",
}
EVENT_COLORS = {"scan": "#3D8BFD", "poredjenje": "#E0A800", "mismatch": "#E5484D", "rejected": "#E5484D",
                "timeout": "#E5484D", "accepted": "#30A46C"}
STYLE = """
QWidget#diagnostics { background: #14181C; }
QLabel { color: #E6EAED; font-size: 13px; }
QLabel#state { font-size: 22px; font-weight: 800; padding: 8px 14px; border-radius: 10px; }
QLabel#title { color: #8A949C; font-size: 12px; font-weight: 700; letter-spacing: 1px; }
QFrame#card { background: #1E242A; border-radius: 12px; }
QListWidget { background: #1E242A; color: #E6EAED; border: none; border-radius: 12px; font-family: Menlo, Consolas, monospace; font-size: 12px; }
QPushButton { background: #2A323A; color: #E6EAED; border: none; border-radius: 8px; padding: 8px 14px; }
"""


def to_pixmap(image: np.ndarray, width: int, height: int | None = None) -> QPixmap:
    source_height, source_width = image.shape[:2]
    if height is None:
        height = max(1, source_height * width // source_width)
    else:
        scale = min(width / source_width, height / source_height)
        width, height = max(1, int(source_width * scale)), max(1, int(source_height * scale))
    rgb = np.ascontiguousarray(cv2.cvtColor(cv2.resize(image, (width, height)), cv2.COLOR_BGR2RGB))
    return QPixmap.fromImage(QImage(rgb.data, width, height, 3 * width, QImage.Format.Format_RGB888).copy())


def tint(frame: np.ndarray, box: tuple[int, int, int, int], mask: np.ndarray | None, color: tuple[int, int, int]) -> None:
    x, y, w, h = box
    if mask is None or w <= 0 or h <= 0:
        return
    region = frame[y:y + h, x:x + w]
    resized = cv2.resize(mask, (region.shape[1], region.shape[0]), interpolation=cv2.INTER_NEAREST) > 0
    overlay = region.copy()
    overlay[resized] = color
    frame[y:y + h, x:x + w] = cv2.addWeighted(region, 0.45, overlay, 0.55, 0)


def card(title: str) -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName("card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(14, 12, 14, 12)
    layout.setSpacing(6)
    heading = QLabel(title)
    heading.setObjectName("title")
    layout.addWidget(heading)
    return frame, layout


def zone_b_reason(guard, name: str, now: float) -> tuple[str, str]:
    watcher = guard.watchers[name]
    if not watcher.armed:
        if guard.state == "waiting_take":
            return "#E0A800", "Čeka da zona A javi da je artikal uzet — B još nije aktivirana."
        return "#8A949C", "Neaktivna — aktivira se tek nakon skeniranja i uzimanja iz A."
    if watcher.waiting_for_motion:
        return "#E0A800", "Nakon greške: čekam da se artikal pomjeri ili ukloni."
    if watcher.change_ratio < watcher.change_min:
        return "#E5484D", (f"Promjena {watcher.change_ratio:.1%} < potrebno {watcher.change_min:.1%} — "
                           "kamera ne vidi novi artikal (izvan zone B, zona pogrešno nacrtana ili artikal premali).")
    if watcher.motion_ratio > watcher.motion_max:
        return "#E0A800", (f"Pokret {watcher.motion_ratio:.2%} > dozvoljeno {watcher.motion_max:.2%} — "
                           "nešto se miče u zoni (ruka, ljudi, sjena, sat na slici).")
    still = watcher.still_seconds(now)
    return "#30A46C", f"Vidi artikal, mirno {still:.1f} / {watcher.stable_seconds:.1f} s — uskoro poređenje."


class DiagnosticsWindow(QWidget):
    def __init__(self, guard_source: Callable[[], object]) -> None:
        super().__init__()
        self.guard_source = guard_source
        self.guard = None
        self.seen_event = 0
        self.seen_debug = 0
        self.setObjectName("diagnostics")
        self.setWindowTitle("Dijagnostika kamera")
        self.setStyleSheet(STYLE)
        self.resize(1400, 900)

        root = QHBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(14)

        self.tiles_layout = QGridLayout()
        self.tiles_layout.setSpacing(8)
        self.tiles: dict[str, QLabel] = {}
        left = QVBoxLayout()
        left.addLayout(self.tiles_layout)
        legend = QLabel("Crveno = promjena koju zona B vidi · Zeleno = promjena u zoni A · Žuto = ruke")
        legend.setStyleSheet("color: #8A949C;")
        left.addWidget(legend)
        compare_card, compare_layout = card("ZADNJE POREĐENJE")
        thumbs = QHBoxLayout()
        self.thumbs = []
        for caption in ("Uzeto iz A", "Odloženo u B", "Najsličnija referenca"):
            column = QVBoxLayout()
            image = QLabel()
            image.setFixedSize(THUMB_SIZE, THUMB_SIZE)
            image.setAlignment(Qt.AlignmentFlag.AlignCenter)
            image.setStyleSheet("background: #14181C; border-radius: 8px; color: #5A646C;")
            image.setText("—")
            text = QLabel(caption)
            text.setAlignment(Qt.AlignmentFlag.AlignCenter)
            column.addWidget(image)
            column.addWidget(text)
            thumbs.addLayout(column)
            self.thumbs.append((image, text, caption))
        thumbs.addStretch()
        compare_layout.addLayout(thumbs)
        self.problems = QLabel("Još nema poređenja.")
        self.problems.setWordWrap(True)
        compare_layout.addWidget(self.problems)
        left.addWidget(compare_card)
        left.addStretch()
        root.addLayout(left, 3)

        right = QVBoxLayout()
        right.setSpacing(10)
        self.state = QLabel("Kamere nisu pokrenute")
        self.state.setObjectName("state")
        right.addWidget(self.state)
        self.message = QLabel()
        self.message.setWordWrap(True)
        right.addWidget(self.message)

        flow_card, flow_layout = card("TOK ARTIKLA")
        self.flow = QLabel()
        self.flow.setWordWrap(True)
        self.flow.setTextFormat(Qt.TextFormat.RichText)
        flow_layout.addWidget(self.flow)
        right.addWidget(flow_card)

        why_card, why_layout = card("ZAŠTO ZONA B JOŠ NIJE PREPOZNALA")
        self.why = QLabel()
        self.why.setWordWrap(True)
        self.why.setTextFormat(Qt.TextFormat.RichText)
        why_layout.addWidget(self.why)
        right.addWidget(why_card)

        log_title = QLabel("DOGAĐAJI")
        log_title.setObjectName("title")
        right.addWidget(log_title)
        self.events = QListWidget()
        right.addWidget(self.events, 1)
        bottom = QHBoxLayout()
        self.folder = QLabel()
        self.folder.setStyleSheet("color: #8A949C;")
        self.folder.setWordWrap(True)
        clear = QPushButton("Očisti događaje")
        clear.clicked.connect(self.events.clear)
        bottom.addWidget(self.folder, 1)
        bottom.addWidget(clear)
        right.addLayout(bottom)
        root.addLayout(right, 2)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(REFRESH_MS)

    def attach(self, guard) -> None:
        self.guard = guard
        self.seen_event = 0
        self.seen_debug = 0
        for label in self.tiles.values():
            label.deleteLater()
        self.tiles.clear()
        if guard is None:
            return
        for row, names in enumerate((guard.cameras_a, guard.cameras_b)):
            for column, name in enumerate(names):
                label = QLabel(name)
                label.setFixedSize(TILE_WIDTH, TILE_WIDTH * 9 // 16)
                label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                label.setStyleSheet("background: #000; border-radius: 8px;")
                self.tiles_layout.addWidget(label, row, column)
                self.tiles[name] = label
        if guard.debug_folder is None:
            guard.enable_debug(app_folder() / "data" / "debug" / time.strftime("%Y%m%d-%H%M%S"))
        self.folder.setText(f"Slike i log: {guard.debug_folder}")
        self.add_event("--:--:--", "info", "Dijagnostika spojena na kasu.")

    def add_event(self, clock: str, kind: str, text: str) -> None:
        item = QListWidgetItem(f"{clock}  {kind:<12} {text}")
        item.setForeground(QColor(EVENT_COLORS.get(kind, "#C9D1D9")))
        self.events.insertItem(0, item)
        while self.events.count() > 400:
            self.events.takeItem(self.events.count() - 1)

    def draw_tile(self, name: str) -> None:
        guard = self.guard
        frame = guard.latest(name)
        label = self.tiles[name]
        if frame is None:
            reader = guard.readers.get(name)
            label.setText(f"{name}: {reader.status if reader else 'nema kamere'}")
            label.setStyleSheet("background: #000; color: #E5484D; border-radius: 8px;")
            return
        height, width = frame.shape[:2]
        box = to_pixels(guard.zones.get(name), width, height)
        if name[0] == "B":
            watcher = guard.watchers[name]
            if watcher.armed:
                tint(frame, box, watcher.last_mask, RED)
            color = RED if watcher.armed else (140, 140, 140)
        else:
            tint(frame, box, guard.trackers[name].last_mask, GREEN)
            color = GREEN
        x, y, w, h = box
        cv2.rectangle(frame, (x, y), (x + w, y + h), color, 3)
        if guard.hand_shapes.get(name):
            cv2.polylines(frame, guard.hand_shapes[name], True, YELLOW, 3)
        reader = guard.readers.get(name)
        cv2.putText(frame, f"{name}  {reader.fps:.1f} FPS", (12, 34), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)
        label.setPixmap(to_pixmap(frame, label.width(), label.height()))

    def refresh(self) -> None:
        guard = self.guard_source()
        if guard is not self.guard:
            self.attach(guard)
        if guard is None:
            self.state.setText("Kamere nisu pokrenute")
            self.state.setStyleSheet("background: #2A323A;")
            self.message.setText("Uključite kamere u postavkama kase.")
            return
        now = time.monotonic()
        for name in self.tiles:
            self.draw_tile(name)
        color = STATE_COLORS.get(guard.state, "#2A323A")
        self.state.setText(STATE_NAMES.get(guard.state, guard.state.upper()))
        self.state.setStyleSheet(f"background: {color}; color: white;")
        self.message.setText(guard.message)
        self.flow.setText(self.flow_text(guard, now))
        self.why.setText(self.why_text(guard, now))
        for number, clock, kind, text in list(guard.events):
            if number > self.seen_event:
                self.add_event(clock, kind, text)
                self.seen_event = number
        if guard.debug is not None and guard.debug_number != self.seen_debug:
            self.seen_debug = guard.debug_number
            self.show_comparison(guard)

    def flow_text(self, guard, now: float) -> str:
        def step(done: bool, text: str) -> str:
            mark = "<span style='color:#30A46C'>●</span>" if done else "<span style='color:#5A646C'>○</span>"
            return f"{mark} {text}"

        scanned = bool(guard.barcode)
        taken = bool(guard._taken_items) or guard.state in ("taken", "waiting_place", "mismatch", "accepted")
        armed = guard.zone_b_armed
        lines = [
            step(guard.zone_a_ready, f"Zona A: {guard.basket_status}"),
            step(taken, f"Uzimanje iz A: {guard.last_event_a}"),
            step(scanned, f"Skenirano: {guard.barcode or '-'} {guard.product_name or ''}"),
            step(armed or guard.state in ("mismatch", "accepted"),
                 f"Zona B aktivna: {'da, ' + format(now - guard._armed_at, '.0f') + ' s' if armed else 'ne'}"),
            step(guard.state == "accepted", f"Ishod: {guard.outcome.verdict if guard.outcome else '-'}"),
        ]
        if guard._pending_until is not None:
            lines.append(f"<span style='color:#E0A800'>Čekam uzimanje iz A još {guard._pending_until - now:.0f} s</span>")
        return "<br>".join(lines)

    def why_text(self, guard, now: float) -> str:
        if guard.state == "accepted":
            return "<span style='color:#30A46C'>Artikal prihvaćen.</span>"
        lines = []
        for name in guard.cameras_b:
            color, text = zone_b_reason(guard, name, now)
            watcher = guard.watchers[name]
            lines.append(f"<b>{name}</b> <span style='color:{color}'>{text}</span><br>"
                         f"<span style='color:#8A949C'>promjena {watcher.change_ratio:.1%} · pokret {watcher.motion_ratio:.2%}</span>")
        if guard.state == "mismatch" and guard.last_problems:
            lines.append("<span style='color:#E5484D'><b>Poređenje palo:</b> " + ", ".join(guard.last_problems) + "</span>")
        if guard.state == "rejected" and guard.outcome:
            lines.append(f"<span style='color:#E5484D'><b>Odbijeno ({guard.outcome.verdict}):</b> {guard.outcome.message}</span>")
        return "<br><br>".join(lines)

    def show_comparison(self, guard) -> None:
        debug = guard.debug
        threshold = debug["threshold"]
        values = [(debug["taken"], None), (debug["placed"], debug["score_taken"]), (debug["reference"], debug["score_product"])]
        for (label, text, caption), (image, score) in zip(self.thumbs, values):
            if image is None or not getattr(image, "size", 0):
                label.clear()
                label.setText("nema slike")
            else:
                label.setPixmap(to_pixmap(image, THUMB_SIZE, THUMB_SIZE))
            if score is None:
                text.setText(caption)
                text.setStyleSheet("")
            else:
                ok = score >= threshold
                text.setText(f"{caption}<br><b>{score:.2f}</b> (prag {threshold})")
                text.setStyleSheet(f"color: {'#30A46C' if ok else '#E5484D'};")
        problems = guard.last_problems
        self.problems.setText(("Problem: " + ", ".join(problems)) if problems else "Poređenje prošlo.")
        self.problems.setStyleSheet(f"color: {'#E5484D' if problems else '#30A46C'};")

import re
import shutil
import threading
import time
from collections import deque
from datetime import datetime, timedelta
from pathlib import Path

import cv2
import numpy as np

FPS = 2.0
BEFORE_SECONDS = 8.0
AFTER_SECONDS = 5.0
TILE = (480, 270)
KEEP_DAYS = 30
REPEAT_SECONDS = 60.0


def mosaic(frames: dict[str, np.ndarray | None], when: datetime | None = None) -> np.ndarray:
    """Sve kamere u jednoj slici (mreža 2 ili 3 kolone) s imenom kamere i vremenom."""
    names = sorted(frames)
    columns = 2 if len(names) <= 4 else 3
    rows = max(1, -(-len(names) // columns))
    canvas = np.zeros((rows * TILE[1], columns * TILE[0], 3), np.uint8)
    for index, name in enumerate(names):
        frame = frames[name]
        row, column = divmod(index, columns)
        top, left = row * TILE[1], column * TILE[0]
        if frame is not None and frame.size:
            canvas[top:top + TILE[1], left:left + TILE[0]] = cv2.resize(frame, TILE, interpolation=cv2.INTER_AREA)
        cv2.putText(canvas, name, (left + 10, top + 30), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 255), 2)
    stamp = (when or datetime.now()).strftime("%d.%m.%Y %H:%M:%S")
    cv2.putText(canvas, stamp, (10, canvas.shape[0] - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
    return canvas


def safe_name(text: str) -> str:
    return re.sub(r"[^0-9A-Za-z]+", "-", text.translate(str.maketrans("čćžšđČĆŽŠĐ", "cczsdCCZSD"))).strip("-")[:40] or "alarm"


class ClipRecorder:
    """Kratak snimak kod alarma: BEFORE_SECONDS prije i AFTER_SECONDS poslije, sve kamere u jednom videu."""

    def __init__(self, folder: Path) -> None:
        self.folder = folder
        self._buffer: deque[tuple[float, bytes]] = deque(maxlen=int((BEFORE_SECONDS + AFTER_SECONDS) * FPS) + 4)
        self._pending: list[tuple[float, float, str]] = []
        self._lock = threading.Lock()
        self._last_add = 0.0
        self._recorded: dict[str, float] = {}
        self.saved: list[Path] = []

    def add(self, frames: dict[str, np.ndarray | None], now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        if now - self._last_add < 1 / FPS:
            return
        self._last_add = now
        ok, encoded = cv2.imencode(".jpg", mosaic(frames), [cv2.IMWRITE_JPEG_QUALITY, 70])
        if not ok:
            return
        with self._lock:
            self._buffer.append((now, encoded.tobytes()))
            ready = [item for item in self._pending if now >= item[1]]
            self._pending = [item for item in self._pending if now < item[1]]
        for started, _, reason in ready:
            threading.Thread(target=self._write, args=(started, reason), daemon=True).start()

    def record(self, reason: str, now: float | None = None) -> None:
        """Zapamti alarm; video se zapiše kad prođe AFTER_SECONDS. Novi alarm unutar postojećeg snimka se ne duplira,
        a isti alarm (npr. ista pomjerena kamera) snima se najviše jednom u REPEAT_SECONDS."""
        now = time.monotonic() if now is None else now
        with self._lock:
            if any(started <= now <= until for started, until, _ in self._pending):
                return
            if now - self._recorded.get(reason, -REPEAT_SECONDS) < REPEAT_SECONDS:
                return
            self._recorded[reason] = now
            self._pending.append((now, now + AFTER_SECONDS, reason))

    def _write(self, started: float, reason: str) -> None:
        with self._lock:
            images = [data for at, data in self._buffer if started - BEFORE_SECONDS <= at <= started + AFTER_SECONDS]
        if not images:
            return
        frames = [cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR) for data in images]
        now = datetime.now()
        folder = self.folder / f"{now:%Y-%m-%d}"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{now:%H%M%S}-{safe_name(reason)}.mp4"
        height, width = frames[0].shape[:2]
        writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), FPS, (width, height))
        for frame in frames:
            writer.write(frame)
        writer.release()
        self.saved.append(path)
        print(f"Snimak alarma: {path}")
        self.cleanup(now)

    def cleanup(self, now: datetime | None = None) -> None:
        limit = ((now or datetime.now()) - timedelta(days=KEEP_DAYS)).strftime("%Y-%m-%d")
        for folder in self.folder.glob("????-??-??"):
            if folder.is_dir() and folder.name < limit:
                shutil.rmtree(folder, ignore_errors=True)

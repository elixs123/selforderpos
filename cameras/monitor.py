import os
import sys
import time

os.environ.setdefault("GLOG_minloglevel", "2")
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import CameraConfigError, load_cameras
from guard import CheckoutGuard
from reader import CameraReader
from zones import to_pixels

TILE_WIDTH = 720
PANEL_HEIGHT = 280
LINE_HEIGHT = 26
FONT_SCALE = 0.6
TITLE = "Monitor kamera - barkod+ENTER, ESC izlaz"
GREEN = (0, 200, 0)
RED = (0, 0, 230)
WHITE = (255, 255, 255)
YELLOW = (0, 220, 255)


def find_product(barcode: str) -> tuple[str | None, str | None]:
    try:
        from catalog import find_by_barcode

        product = find_by_barcode(barcode)
    except Exception as error:
        print(f"Baza: {error}")
        return None, None
    if product is None:
        return None, None
    return product.code, product.name


def ascii_text(text: str) -> str:
    table = str.maketrans("čćžšđČĆŽŠĐ", "cczsdCCZSD")
    return text.translate(table)


STATE_COLORS = {
    "accepted": GREEN,
    "mismatch": RED,
    "rejected": RED,
    "waiting_place": RED,
    "waiting_take": YELLOW,
    "timeout": YELLOW,
    "learning": YELLOW,
}


class Monitor:
    def __init__(self, readers: dict[str, CameraReader]) -> None:
        self.guard = CheckoutGuard(readers)
        self.typed = ""

    def on_key(self, key: int) -> bool:
        if key == 27:
            return False
        if key in (10, 13):
            if self.typed:
                code, name = find_product(self.typed)
                self.guard.scan(self.typed, code, name)
            self.typed = ""
        elif key in (8, 127):
            self.typed = self.typed[:-1]
        elif 32 <= key < 127:
            self.typed += chr(key)
        return True

    def tile(self, name: str) -> np.ndarray:
        guard = self.guard
        reader = guard.readers.get(name)
        frame = reader.latest() if reader else None
        if frame is None:
            tile = np.zeros((TILE_WIDTH * 9 // 16, TILE_WIDTH, 3), dtype=np.uint8)
            status = reader.status if reader else "nije podesena"
            cv2.putText(tile, ascii_text(f"{name}: {status}"), (12, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.8, RED, 2)
            return tile
        height, width = frame.shape[:2]
        x, y, w, h = to_pixels(guard.zones.get(name), width, height)
        color = RED if name == "B" and guard.watcher.armed else GREEN
        cv2.rectangle(frame, (x, y), (x + w, y + h), color, 3)
        if guard.hand_shapes.get(name):
            cv2.polylines(frame, guard.hand_shapes[name], True, YELLOW, 3)
        tile = cv2.resize(frame, (TILE_WIDTH, height * TILE_WIDTH // width))
        label = ascii_text(f"{name}  {reader.status}  {reader.fps:.1f} FPS")
        cv2.putText(tile, label, (12, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.8, GREEN, 2)
        return tile

    def frame(self) -> np.ndarray:
        guard = self.guard
        tiles = np.vstack([self.tile(name) for name in ("A", "B")])
        panel = np.zeros((PANEL_HEIGHT, tiles.shape[1], 3), dtype=np.uint8)
        lines = [
            (ascii_text(guard.message), STATE_COLORS.get(guard.state, WHITE)),
            (ascii_text(f"Zona A: {guard.basket_status}   pokret A: {guard.tracker.motion_ratio:.2%}   ruke: {'da' if guard.hands else 'ISKLJUCENO'}"), WHITE),
            *[(f"Slicnost  {part.strip()}", WHITE) for part in guard.scores.split("velicina")[:1]],
            (f"velicina {guard.scores.split('velicina', 1)[1]}" if "velicina" in guard.scores else "", WHITE),
            (f"Zadnji dogadjaj A: {guard.last_event_a}", WHITE),
            (f"Unos: {self.typed}_", WHITE),
            (f"Zadnji barkod: {guard.barcode or '-'}  {ascii_text(guard.product_name or '')}", WHITE),
            (f"Promjena zone B: {guard.watcher.change_ratio:.1%}  pokret: {guard.watcher.motion_ratio:.2%}  uzoraka: {guard.store.count()}", WHITE),
        ]
        for index, (text, color) in enumerate(lines):
            cv2.putText(panel, text, (10, 24 + index * LINE_HEIGHT), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
        return np.vstack([tiles, panel])


def main() -> None:
    try:
        cameras = load_cameras()
    except CameraConfigError as error:
        print(error)
        return
    readers = {settings.name: CameraReader(settings) for settings in cameras}
    for reader in readers.values():
        reader.start()

    monitor = Monitor(readers)
    cv2.namedWindow(TITLE, cv2.WINDOW_NORMAL)
    try:
        while True:
            monitor.guard.step()
            cv2.imshow(TITLE, monitor.frame())
            key = cv2.waitKey(30)
            if key != -1 and not monitor.on_key(key & 0xFF):
                break
    finally:
        for reader in readers.values():
            reader.stop()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()

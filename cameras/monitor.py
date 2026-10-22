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
from guard import CheckoutGuard, zone_of
from reader import CameraReader
from zones import outline

TILE_WIDTH = 720
GRID_TILE_WIDTH = 480
PANEL_HEIGHT = 306
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


COMPARE_TITLE = "Poredjenje"
THUMB_HEIGHT = 240


def thumbnail(image: np.ndarray | None, title: str, score: float | None, threshold: float) -> np.ndarray:
    width = THUMB_HEIGHT
    if image is None or image.size == 0:
        thumb = np.zeros((THUMB_HEIGHT, width, 3), dtype=np.uint8)
        cv2.putText(thumb, "nema slike", (40, THUMB_HEIGHT // 2), cv2.FONT_HERSHEY_SIMPLEX, 0.7, WHITE, 1)
    else:
        height, original_width = image.shape[:2]
        width = max(1, original_width * THUMB_HEIGHT // height)
        thumb = cv2.resize(image, (width, THUMB_HEIGHT))
    label = np.zeros((60, max(width, 240), 3), dtype=np.uint8)
    cv2.putText(label, title, (8, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.6, WHITE, 1)
    if score is not None:
        color = GREEN if score >= threshold else RED
        cv2.putText(label, f"{score:.2f} (prag {threshold})", (8, 48), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
    canvas = np.zeros((THUMB_HEIGHT, label.shape[1], 3), dtype=np.uint8)
    canvas[:, :thumb.shape[1]] = thumb[:, :label.shape[1]]
    return np.vstack([canvas, label])


class Monitor:
    def __init__(self, readers: dict[str, CameraReader]) -> None:
        self.guard = CheckoutGuard(readers)
        self.typed = ""
        self.shown_debug = 0

    def comparison(self) -> np.ndarray | None:
        guard = self.guard
        if guard.debug is None or guard.debug_number == self.shown_debug:
            return None
        self.shown_debug = guard.debug_number
        debug = guard.debug
        threshold = debug["threshold"]
        parts = [
            thumbnail(debug["taken"], "Uzeto iz A", None, threshold),
            thumbnail(debug["placed"], "Odlozeno u B", debug["score_taken"], threshold),
            thumbnail(debug["reference"], "Najslicnija referenca", debug["score_product"], threshold),
        ]
        height = max(part.shape[0] for part in parts)
        parts = [cv2.copyMakeBorder(part, 0, height - part.shape[0], 0, 8, cv2.BORDER_CONSTANT) for part in parts]
        return np.hstack(parts)

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

    def tile(self, name: str, width: int = TILE_WIDTH) -> np.ndarray:
        guard = self.guard
        reader = guard.readers.get(name)
        frame = reader.latest() if reader else None
        if frame is not None:
            frame_height, frame_width = frame.shape[:2]
        if frame is None:
            tile = np.zeros((width * 9 // 16, width, 3), dtype=np.uint8)
            status = reader.status if reader else "nije podesena"
            cv2.putText(tile, ascii_text(f"{name}: {status}"), (12, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.8, RED, 2)
            return tile
        color = RED if zone_of(name) == "B" and guard.zone_b_armed else YELLOW if zone_of(name) == "C" else GREEN
        cv2.polylines(frame, [outline(guard.zones.get(name), frame_width, frame_height)], True, color, 3, cv2.LINE_AA)
        if guard.hand_shapes.get(name):
            cv2.polylines(frame, guard.hand_shapes[name], True, YELLOW, 3)
        result = guard.hold_results.get(name) if zone_of(name) == "C" else None
        if result is not None:
            for item in result.items:
                held = any(item is other for other in result.held_items)
                cv2.rectangle(frame, (int(item[0]), int(item[1])), (int(item[2]), int(item[3])), RED if held else (255, 170, 60), 3)
            if result.hands:
                cv2.polylines(frame, result.hands, True, YELLOW, 3)
        tile = cv2.resize(frame, (width, width * 9 // 16))
        label = ascii_text(f"{name}  {reader.status}  {reader.fps:.1f} FPS")
        cv2.putText(tile, label, (12, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.8, GREEN, 2)
        return tile

    def frame(self) -> np.ndarray:
        guard = self.guard
        rows = []
        columns = max(len(guard.cameras_a), len(guard.cameras_b), len(guard.cameras_c))
        width = TILE_WIDTH if columns == 1 else GRID_TILE_WIDTH
        for names in (guard.cameras_a, guard.cameras_b, guard.cameras_c):
            if not names:
                continue
            row = [self.tile(name, width) for name in names]
            while len(row) < columns:
                row.append(np.zeros((width * 9 // 16, width, 3), dtype=np.uint8))
            rows.append(np.hstack(row))
        tiles = np.vstack(rows)
        panel = np.zeros((PANEL_HEIGHT, tiles.shape[1], 3), dtype=np.uint8)
        lines = [
            (ascii_text(guard.message), STATE_COLORS.get(guard.state, WHITE)),
            (ascii_text(f"Zona A: {guard.basket_status}   pokret A: {guard.zone_a_motion:.2%}   ruke: {'da' if guard.hands else 'ISKLJUCENO'}"), WHITE),
            *[(f"Slicnost  {part.strip()}", WHITE) for part in guard.scores.split("velicina")[:1]],
            (f"velicina {guard.scores.split('velicina', 1)[1]}" if "velicina" in guard.scores else "", WHITE),
            (f"Zadnji dogadjaj A: {guard.last_event_a}", WHITE),
            (f"Unos: {self.typed}_", WHITE),
            (ascii_text(f"Artikal u ruci (C): {guard.held_message or 'ne'}"), RED if guard.held_message else WHITE),
            (f"Zadnji barkod: {guard.barcode or '-'}  {ascii_text(guard.product_name or '')}", WHITE),
            ("Zona B: " + "  ".join(f"{name} promjena {w.change_ratio:.1%} pokret {w.motion_ratio:.2%}" for name, w in guard.watchers.items()) + f"  uzoraka: {guard.store.count()}", WHITE),
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
    if "--debug" in sys.argv:
        from locations import app_folder

        monitor.guard.enable_debug(app_folder() / "data" / "debug" / time.strftime("%Y%m%d-%H%M%S"))
    cv2.namedWindow(TITLE, cv2.WINDOW_NORMAL)
    try:
        while True:
            monitor.guard.step()
            cv2.imshow(TITLE, monitor.frame())
            comparison = monitor.comparison()
            if comparison is not None:
                cv2.imshow(COMPARE_TITLE, comparison)
            key = cv2.waitKey(30)
            if key != -1 and not monitor.on_key(key & 0xFF):
                break
    finally:
        for reader in readers.values():
            reader.stop()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()

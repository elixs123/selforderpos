import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2
import numpy as np

from config import CameraConfigError, load_cameras
from reader import CameraReader
from zones import Zone, load_zones, save_zone, to_pixels

GREEN = (0, 200, 0)
YELLOW = (0, 220, 255)
RED = (0, 0, 230)
WHITE = (255, 255, 255)


class ZoneDrawer:
    """Olovka: drži lijevi taster i crtaj slobodnom rukom, oblik se sam zatvori. Način 'kocka' crta pravougaonik."""

    MIN_STEP = 4

    def __init__(self) -> None:
        self.freehand = True
        self.points: list[tuple[int, int]] = []
        self.start: tuple[int, int] | None = None
        self.end: tuple[int, int] | None = None
        self.dragging = False

    def toggle_mode(self) -> None:
        self.freehand = not self.freehand
        self.reset()

    def reset(self) -> None:
        self.points = []
        self.start = self.end = None
        self.dragging = False

    def on_mouse(self, event: int, x: int, y: int, flags: int, param) -> None:
        if event == cv2.EVENT_LBUTTONDOWN:
            self.reset()
            self.start, self.end, self.dragging = (x, y), (x, y), True
            self.points = [(x, y)]
        elif event == cv2.EVENT_MOUSEMOVE and self.dragging:
            self.end = (x, y)
            last = self.points[-1]
            if abs(x - last[0]) + abs(y - last[1]) >= self.MIN_STEP:
                self.points.append((x, y))
        elif event == cv2.EVENT_LBUTTONUP and self.dragging:
            self.end, self.dragging = (x, y), False

    def polygon(self) -> list[tuple[int, int]] | None:
        if self.freehand:
            points = np.array(self.points, np.int32).reshape(-1, 1, 2)
            if len(points) < 3:
                return None
            smooth = cv2.approxPolyDP(points, 2.0, True).reshape(-1, 2)
            if len(smooth) < 3 or cv2.contourArea(smooth) < 100:
                return None
            return [(int(x), int(y)) for x, y in smooth]
        rectangle = self.rectangle()
        if rectangle is None:
            return None
        x, y, w, h = rectangle
        return [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]

    def rectangle(self) -> tuple[int, int, int, int] | None:
        if self.start is None or self.end is None:
            return None
        left, right = sorted((self.start[0], self.end[0]))
        top, bottom = sorted((self.start[1], self.end[1]))
        if right - left < 10 or bottom - top < 10:
            return None
        return left, top, right - left, bottom - top


def draw_shape(frame: np.ndarray, points: list[tuple[int, int]], color: tuple[int, int, int], thickness: int) -> None:
    cv2.polylines(frame, [np.array(points, np.int32).reshape(-1, 1, 2)], True, color, thickness, cv2.LINE_AA)


def main() -> None:
    wanted = sys.argv[1].upper() if len(sys.argv) > 1 else "A"
    try:
        cameras = {camera.name: camera for camera in load_cameras()}
    except CameraConfigError as error:
        print(error)
        return
    if wanted not in cameras:
        print(f"Kamera {wanted} nije podešena u .env.")
        return

    reader = CameraReader(cameras[wanted])
    reader.start()
    drawer = ZoneDrawer()
    title = f"Zona {wanted} - crtaj misem, ENTER spremi zonu, I ignorisi nacrtano, C obrisi ignorisano, R ponovo, M olovka/kocka, ESC izlaz"
    cv2.namedWindow(title, cv2.WINDOW_NORMAL)
    cv2.setMouseCallback(title, drawer.on_mouse)
    saved_zone = load_zones().get(wanted)
    try:
        while True:
            frame = reader.latest()
            if frame is None:
                time.sleep(0.05)
                if cv2.waitKey(30) & 0xFF == 27:
                    break
                continue
            height, width = frame.shape[:2]
            if saved_zone is not None:
                if saved_zone.polygon:
                    draw_shape(frame, [(round(px * width), round(py * height)) for px, py in saved_zone.polygon], YELLOW, 2)
                else:
                    x, y, w, h = to_pixels(saved_zone, width, height)
                    cv2.rectangle(frame, (x, y), (x + w, y + h), YELLOW, 2)
            if saved_zone is not None:
                for area in saved_zone.exclude:
                    points = np.array([(round(px * width), round(py * height)) for px, py in area], np.int32)
                    overlay = frame.copy()
                    cv2.fillPoly(overlay, [points], RED)
                    cv2.addWeighted(overlay, 0.35, frame, 0.65, 0, frame)
                    cv2.polylines(frame, [points], True, RED, 2)
            shape = drawer.polygon()
            if drawer.dragging and drawer.freehand and len(drawer.points) > 1:
                cv2.polylines(frame, [np.array(drawer.points, np.int32).reshape(-1, 1, 2)], False, GREEN, 3, cv2.LINE_AA)
            elif shape is not None:
                draw_shape(frame, shape, GREEN, 3)
            mode = "olovka" if drawer.freehand else "kocka"
            cv2.putText(frame, f"{wanted}  {reader.status}  {reader.fps:.0f} FPS  nacin: {mode}", (10, 28),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, WHITE, 2)
            cv2.putText(frame, "zuto = spremljena zona, zeleno = nova", (10, height - 14),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, WHITE, 2)
            cv2.imshow(title, frame)
            key = cv2.waitKey(30) & 0xFF
            if key == 27:
                print("Izlaz bez spremanja.")
                break
            if key in (ord("r"), ord("R")):
                drawer.reset()
            if key in (ord("m"), ord("M")):
                drawer.toggle_mode()
            if key in (ord("i"), ord("I")):
                if saved_zone is None:
                    print("Prvo nacrtaj i spremi zonu (ENTER), pa onda dijelove koje treba ignorisati.")
                elif shape is None or drawer.dragging:
                    print("Prvo mišem nacrtaj dio zone koji treba ignorisati.")
                else:
                    area = tuple((px / width, py / height) for px, py in shape)
                    save_zone(wanted, Zone(saved_zone, saved_zone.polygon, saved_zone.exclude + (area,)))
                    saved_zone = load_zones().get(wanted)
                    drawer.reset()
                    print(f"Zona {wanted}: dio zone se ignoriše ({len(saved_zone.exclude)} ukupno).")
            if key in (ord("c"), ord("C")) and saved_zone is not None and saved_zone.exclude:
                save_zone(wanted, Zone(saved_zone, saved_zone.polygon))
                saved_zone = load_zones().get(wanted)
                print(f"Zona {wanted}: ignorisani dijelovi obrisani.")
            if key in (10, 13):
                if shape is None or drawer.dragging:
                    print("Prvo mišem nacrtaj zonu.")
                    continue
                x, y, w, h = cv2.boundingRect(np.array(shape, np.int32))
                polygon = [] if not drawer.freehand else [(px / width, py / height) for px, py in shape]
                exclude = saved_zone.exclude if saved_zone is not None else ()
                save_zone(wanted, Zone((x / width, y / height, w / width, h / height), polygon, exclude))
                saved_zone = load_zones().get(wanted)
                print(f"Zona {wanted} spremljena u zones.json.")
                break
    finally:
        reader.stop()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2

from config import CameraConfigError, load_cameras
from reader import CameraReader
from zones import load_zones, save_zone, to_pixels

GREEN = (0, 200, 0)
YELLOW = (0, 220, 255)
WHITE = (255, 255, 255)


class ZoneDrawer:
    def __init__(self) -> None:
        self.start: tuple[int, int] | None = None
        self.end: tuple[int, int] | None = None
        self.dragging = False

    def on_mouse(self, event: int, x: int, y: int, flags: int, param) -> None:
        if event == cv2.EVENT_LBUTTONDOWN:
            self.start, self.end, self.dragging = (x, y), (x, y), True
        elif event == cv2.EVENT_MOUSEMOVE and self.dragging:
            self.end = (x, y)
        elif event == cv2.EVENT_LBUTTONUP and self.dragging:
            self.end, self.dragging = (x, y), False

    def rectangle(self) -> tuple[int, int, int, int] | None:
        if self.start is None or self.end is None:
            return None
        left, right = sorted((self.start[0], self.end[0]))
        top, bottom = sorted((self.start[1], self.end[1]))
        if right - left < 10 or bottom - top < 10:
            return None
        return left, top, right - left, bottom - top


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
    title = f"Zona {wanted} - misem nacrtaj zonu, ENTER spremi, R ponovo, ESC izlaz"
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
                x, y, w, h = to_pixels(saved_zone, width, height)
                cv2.rectangle(frame, (x, y), (x + w, y + h), YELLOW, 2)
            rectangle = drawer.rectangle()
            if rectangle is not None:
                x, y, w, h = rectangle
                cv2.rectangle(frame, (x, y), (x + w, y + h), GREEN, 3)
            cv2.putText(frame, f"{wanted}  {reader.status}  {reader.fps:.0f} FPS", (10, 28),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, WHITE, 2)
            cv2.putText(frame, "zuto = spremljena zona, zeleno = nova", (10, height - 14),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, WHITE, 2)
            cv2.imshow(title, frame)
            key = cv2.waitKey(30) & 0xFF
            if key == 27:
                print("Izlaz bez spremanja.")
                break
            if key in (ord("r"), ord("R")):
                drawer.start = drawer.end = None
            if key in (10, 13):
                if rectangle is None:
                    print("Prvo mišem nacrtaj zonu.")
                    continue
                x, y, w, h = rectangle
                save_zone(wanted, (x / width, y / height, w / width, h / height))
                saved_zone = load_zones().get(wanted)
                print(f"Zona {wanted} spremljena u zones.json.")
                break
    finally:
        reader.stop()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()

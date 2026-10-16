import os

os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp")

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2

from config import CameraConfigError, load_cameras
from zones import save_zone


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

    camera = cv2.VideoCapture(cameras[wanted].rtsp_url, cv2.CAP_FFMPEG)
    frame = None
    for _ in range(10):
        ok, image = camera.read()
        if ok:
            frame = image
    camera.release()
    if frame is None:
        print("Nema slike sa kamere.")
        return

    title = f"Zona {wanted}: oznaci misem pa ENTER (c = odustani)"
    x, y, w, h = cv2.selectROI(title, frame, showCrosshair=False)
    cv2.destroyAllWindows()
    if w == 0 or h == 0:
        print("Zona nije označena.")
        return
    height, width = frame.shape[:2]
    save_zone(wanted, (x / width, y / height, w / width, h / height))
    print(f"Zona {wanted} spremljena u zones.json.")


if __name__ == "__main__":
    main()

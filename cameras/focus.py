import argparse
import getpass
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import cv2

from disable_osd import opener
from config import CAMERA_NAMES, build_rtsp_url

WAIT_SECONDS = 5
# Hikvision ima "foucs" s greškom u nazivu; različite verzije softvera kamere koriste različite adrese.
FOCUS_CALLS = (
    ("/ISAPI/PTZCtrl/channels/1/onepushfoucs/start", ""),
    ("/ISAPI/PTZCtrl/channels/1/onepushfocus/start", ""),
)
LENS_INIT_CALLS = (
    ("/ISAPI/Image/channels/1/lensInitialization", "<LensInitialization><enabled>true</enabled></LensInitialization>"),
    ("/ISAPI/PTZCtrl/channels/1/lensInitialization", "<LensInitialization><enabled>true</enabled></LensInitialization>"),
)


def sharpness(host: str, user: str, password: str, channel: str) -> float | None:
    """Oštrina slike (veće = oštrije), da se vidi je li fokus pomogao."""
    capture = cv2.VideoCapture(build_rtsp_url(host, user, password, channel), cv2.CAP_FFMPEG)
    try:
        frame = None
        for _ in range(5):
            ok, image = capture.read()
            if ok:
                frame = image
        if frame is None:
            return None
        gray = cv2.cvtColor(cv2.resize(frame, (640, int(640 * frame.shape[0] / frame.shape[1]))), cv2.COLOR_BGR2GRAY)
        return float(cv2.Laplacian(gray, cv2.CV_64F).var())
    finally:
        capture.release()


def send(client, host: str, calls: tuple[tuple[str, str], ...]) -> str:
    """Pošalji prvu komandu koju kamera prihvati; vrati adresu koja je uspjela ili opis greške."""
    errors = []
    for path, body in calls:
        request = urllib.request.Request(f"http://{host}{path}", data=body.encode(), method="PUT")
        request.add_header("Content-Type", "application/xml")
        try:
            client.open(request, timeout=10).read()
            return path
        except urllib.error.HTTPError as error:
            errors.append(f"{path}: {error.code}")
            if error.code == 401:
                break
        except OSError as error:
            return f"kamera nije dostupna ({error})"
    raise RuntimeError("kamera je odbila: " + ", ".join(errors))


def process(name: str, host: str, user: str, password: str, channel: str, lens_init: bool) -> None:
    print(f"\n{name}  {host}")
    client = opener(host, user, password)
    before = sharpness(host, user, password, channel)
    print(f"  Oštrina prije: {before:.0f}" if before is not None else "  Slika se ne može pročitati (RTSP).")
    try:
        if lens_init:
            print(f"  Inicijalizacija objektiva: {send(client, host, LENS_INIT_CALLS)}")
            time.sleep(WAIT_SECONDS * 2)
        print(f"  One-push focus: {send(client, host, FOCUS_CALLS)}")
    except RuntimeError as error:
        print(f"  {error}")
        return
    time.sleep(WAIT_SECONDS)
    after = sharpness(host, user, password, channel)
    if after is None:
        return
    change = f" ({(after / before - 1) * 100:+.0f} %)" if before else ""
    print(f"  Oštrina poslije: {after:.0f}{change}")


def main() -> None:
    parser = argparse.ArgumentParser(description="One-push focus na Hikvision kamerama s motornim objektivom.")
    parser.add_argument("cameras", nargs="*", help=f"kamere ({', '.join(CAMERA_NAMES)}); bez navođenja sve iz .env")
    parser.add_argument("--init", action="store_true", help="prvo inicijalizacija objektiva (kad fokus 'luta')")
    arguments = parser.parse_args()

    names = [name.upper() for name in arguments.cameras] or list(CAMERA_NAMES)
    cameras = [(name, os.environ.get(f"CAM_{name}_HOST", "")) for name in names]
    cameras = [(name, host) for name, host in cameras if host]
    if not cameras:
        print("Nema kamera: upiši CAM_<ime>_HOST u .env.")
        return
    user = os.environ.get("CAM_USER") or input("Admin korisnik kamere [admin]: ").strip() or "admin"
    password = os.environ.get("CAM_PASSWORD") or getpass.getpass("Lozinka (ne prikazuje se): ")
    channel = os.environ.get("CAM_CHANNEL", "102")
    for name, host in cameras:
        process(name, host, user, password, channel, arguments.init)
    print("\nGotovo. Ako se slika promijenila, ponovo nacrtaj zone u zone_setup.")


if __name__ == "__main__":
    main()

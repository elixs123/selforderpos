"""Testni prikaz: kako YOLOX vidi i broji artikle u zonama kamera.

Pokretanje (iz foldera projekta):
    ./.venv/bin/python cameras/yolo_view.py            # kamere koje broje (CAM_COUNT_CAMERAS, npr. A2,B2)
    ./.venv/bin/python cameras/yolo_view.py A3 B3 C    # izabrane kamere
    ./.venv/bin/python cameras/yolo_view.py --file slika.jpg   # slika ili video sa diska
    ./.venv/bin/python cameras/yolo_view.py A2 --cijela        # cijela slika kamere, ne samo zona
    ./.venv/bin/python cameras/yolo_view.py --model yolox_s    # uporedi sa manjim modelom

Boje:
    zeleno  = artikal koji se BROJI (kao na kasi: pouzdanost >= prag, klasa nije zanemarena)
    plavo   = zanemarena klasa (osoba, stolica, laptop...) - kasa je ne broji
    žuto    = YOLOX nešto vidi, ali ispod praga (kasa to ne broji; ako je artikal žut, broj će falit)

Tipke:
    TAB / 1-8   sljedeća / izabrana kamera
    M           prikaz "očima modela": slika smanjena na 640x640 (sivo = dopuna)
    [  ]        spusti / podigni prag pouzdanosti (samo za ovaj prikaz, kasa se ne mijenja)
    Z           žuti okviri (ispod praga) uključi/isključi
    RAZMAK      pauza
    S           spremi trenutnu sliku u data/yolo_view/
    Q / ESC     izlaz
"""
import argparse
import os
import sys
import time
from collections import deque
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(1, str(Path(__file__).resolve().parent.parent))

import cv2
import numpy as np

from config import CameraConfigError, load_cameras
from counter import IGNORED_CLASSES, INPUT_SIZE, MIN_CONFIDENCE, counting_cameras, get_counter, model_name
from reader import CameraReader
from zones import crop, load_zones

COCO = (
    "osoba", "bicikl", "auto", "motor", "avion", "autobus", "voz", "kamion", "brod", "semafor",
    "hidrant", "znak stop", "parking", "klupa", "ptica", "macka", "pas", "konj", "ovca", "krava",
    "slon", "medvjed", "zebra", "zirafa", "ranac", "kisobran", "torba", "kravata", "kofer", "frizbi",
    "skije", "snowboard", "lopta", "zmaj", "palica", "rukavica", "skejt", "daska", "reket", "boca",
    "casa vina", "solja", "viljuska", "noz", "kasika", "zdjela", "banana", "jabuka", "sendvic", "narandza",
    "brokula", "mrkva", "hot dog", "pizza", "krofna", "torta", "stolica", "kauc", "biljka", "krevet",
    "sto", "wc", "tv", "laptop", "mis", "daljinski", "tastatura", "mobitel", "mikrotalasna", "rerna",
    "toster", "sudoper", "frizider", "knjiga", "sat", "vaza", "makaze", "meda", "fen", "cetkica",
)
LOW_CONFIDENCE = 0.15
WINDOW_WIDTH, WINDOW_HEIGHT = 1400, 820
PANEL_WIDTH = 460
# Koliko zadnjih brojanja se pamti da se vidi skače li broj (kasa broji svakih ~0.5 s).
HISTORY = 20
GREY = (170, 170, 170)
GREEN, BLUE, YELLOW, WHITE, BLACK = (60, 200, 60), (230, 150, 40), (0, 220, 255), (255, 255, 255), (0, 0, 0)
SAVE_FOLDER = Path(__file__).resolve().parent.parent / "data" / "yolo_view"


def letterbox(image: np.ndarray) -> tuple[np.ndarray, float]:
    """Isto što counter.detections radi prije modela: smanji na 640 po dužoj strani, ostatak sivo (114)."""
    height, width = image.shape[:2]
    ratio = min(INPUT_SIZE / height, INPUT_SIZE / width)
    canvas = np.full((INPUT_SIZE, INPUT_SIZE, 3), 114, np.uint8)
    canvas[:int(height * ratio), :int(width * ratio)] = cv2.resize(image, (int(width * ratio), int(height * ratio)))
    return canvas, ratio


def label(image: np.ndarray, text: str, x: int, y: int, color, scale: float = 0.6) -> None:
    (width, height), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, scale, 2)
    y = max(height + 4, y)
    cv2.rectangle(image, (x, y - height - 6), (x + width + 6, y + 2), color, -1)
    cv2.putText(image, text, (x + 3, y - 3), cv2.FONT_HERSHEY_SIMPLEX, scale, BLACK, 2, cv2.LINE_AA)


def draw(image: np.ndarray, found: list, threshold: float, scale: float, show_low: bool) -> tuple[np.ndarray, int]:
    """Okviri preko slike; vraća sliku i broj artikala koje bi kasa izbrojala."""
    counted = 0
    for kind, score, box in sorted(found, key=lambda item: item[1]):
        if kind in IGNORED_CLASSES:
            color = BLUE if score >= threshold else None
        elif score >= threshold:
            color, counted = GREEN, counted + 1
        else:
            color = YELLOW if show_low else None
        if color is None:
            continue
        x1, y1, x2, y2 = (int(value * scale) for value in box)
        cv2.rectangle(image, (x1, y1), (x2, y2), color, 3 if color is GREEN else 2)
        name = COCO[kind] if 0 <= kind < len(COCO) else str(kind)
        label(image, f"{name} {score:.0%}", x1, y1 - 2, color, 0.55)
    return image, counted


def fit(image: np.ndarray) -> tuple[np.ndarray, float]:
    height, width = image.shape[:2]
    scale = min((WINDOW_WIDTH - PANEL_WIDTH) / width, WINDOW_HEIGHT / height, 3.0)
    return cv2.resize(image, (max(1, int(width * scale)), max(1, int(height * scale)))), scale


def compose(image: np.ndarray, count: str, lines: list[tuple[str, tuple]]) -> np.ndarray:
    """Slika lijevo, desno panel sa velikim brojem artikala (zona je često uska, pa tekst iznad slike ne stane)."""
    height = max(image.shape[0], WINDOW_HEIGHT)
    canvas = np.full((height, image.shape[1] + PANEL_WIDTH, 3), 30, np.uint8)
    canvas[:image.shape[0], :image.shape[1]] = image
    left = image.shape[1] + 20
    cv2.putText(canvas, "BROJ ARTIKALA", (left, 45), cv2.FONT_HERSHEY_SIMPLEX, 0.9, WHITE, 2, cv2.LINE_AA)
    cv2.putText(canvas, count, (left, 170), cv2.FONT_HERSHEY_SIMPLEX, 4.0, GREEN, 8, cv2.LINE_AA)
    for index, (text, color) in enumerate(lines):
        cv2.putText(canvas, text, (left, 230 + index * 32), cv2.FONT_HERSHEY_SIMPLEX, 0.62, color, 1 if color == GREY else 2, cv2.LINE_AA)
    return canvas


def file_source(path: Path):
    if path.suffix.lower() in (".jpg", ".jpeg", ".png", ".bmp", ".webp"):
        image = cv2.imread(str(path))
        if image is None:
            sys.exit(f"Ne mogu otvoriti sliku {path}")
        return lambda: image
    video = cv2.VideoCapture(str(path))
    if not video.isOpened():
        sys.exit(f"Ne mogu otvoriti video {path}")

    def next_frame():
        ok, frame = video.read()
        if not ok:
            video.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ok, frame = video.read()
        return frame if ok else None

    return next_frame


def main() -> None:
    parser = argparse.ArgumentParser(description="Kako YOLOX vidi i broji artikle u zonama kamera.")
    parser.add_argument("cameras", nargs="*", help="imena kamera (A, A2, A3, B, B2, B3, C, C2)")
    parser.add_argument("--file", type=Path, help="slika ili video sa diska umjesto kamere")
    parser.add_argument("--cijela", action="store_true", help="cijela slika kamere umjesto zone")
    parser.add_argument("--model", help="yolox_s, yolox_m ili yolox_l (zadano: CAM_YOLOX_MODEL iz .env)")
    args = parser.parse_args()
    if args.model:
        os.environ["CAM_YOLOX_MODEL"] = args.model

    print("Učitavam YOLOX...")
    counter = get_counter()
    if counter is None:
        sys.exit("YOLOX se nije mogao učitati (vidi grešku iznad).")
    print(f"Model {model_name()}, izvršava se na:", ", ".join(counter.session.get_providers()))

    sources: dict[str, object] = {}
    readers: list[CameraReader] = []
    if args.file:
        sources[args.file.name] = file_source(args.file)
    else:
        try:
            cameras = {camera.name: camera for camera in load_cameras()}
        except CameraConfigError as error:
            sys.exit(str(error))
        wanted = args.cameras or sorted(counting_cameras())
        missing = [name for name in wanted if name not in cameras]
        if missing:
            print(f"Nema adrese u .env za: {', '.join(missing)}")
        for name in wanted:
            if name in cameras:
                reader = CameraReader(cameras[name])
                reader.start()
                readers.append(reader)
                sources[name] = reader
        if not sources:
            sys.exit("Nijedna kamera nije izabrana.")
    zones = {} if args.cijela or args.file else load_zones()
    names = list(sources)
    current, threshold, model_view, show_low, paused = 0, MIN_CONFIDENCE, False, True, False
    frame, shown, ms = None, None, 0.0
    history: dict[str, deque] = {}
    window = "YOLOX - kako broji"
    cv2.namedWindow(window, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window, WINDOW_WIDTH, WINDOW_HEIGHT)
    print(__doc__.split("Boje:")[1])

    while True:
        name = names[current]
        source = sources[name]
        if not paused or shown is None:
            frame = source.latest() if isinstance(source, CameraReader) else source()
        if frame is None:
            status = source.status if isinstance(source, CameraReader) else "nema slike"
            blank = np.zeros((WINDOW_HEIGHT, WINDOW_WIDTH - PANEL_WIDTH, 3), np.uint8)
            shown = compose(blank, "-", [(f"Kamera {name}: {status}", WHITE), ("TAB sljedeca kamera, Q izlaz", GREY)])
        else:
            zone = zones.get(name)
            region = crop(frame, zone)[0] if zone is not None else frame
            if not paused or shown is None:
                started = time.perf_counter()
                found = counter.detections(region, LOW_CONFIDENCE)
                ms = (time.perf_counter() - started) * 1000
            if model_view:
                picture, ratio = letterbox(region)
                picture, scale = fit(picture)
                scale *= ratio
            else:
                picture, scale = fit(region)
            picture, counted = draw(picture, found, threshold, scale, show_low)
            low = sum(1 for kind, score, _ in found if kind not in IGNORED_CLASSES and score < threshold)
            if not paused:
                history.setdefault(name, deque(maxlen=HISTORY)).append(counted)
            seen = history.get(name) or [counted]
            height, width = region.shape[:2]
            jumps = min(seen) != max(seen)
            lines = [
                (f"Kamera {name}", WHITE),
                (f"{'cijela slika' if zone is None else 'zona'} {width}x{height} px", GREY),
                (f"ispod praga (zuto): {low}", YELLOW if low else GREY),
                (f"zadnjih {len(seen)} brojanja: {min(seen)}-{max(seen)}", YELLOW if jumps else GREEN),
                ("BROJ SKACE - YOLO gubi artikal" if jumps else "broj stabilan", YELLOW if jumps else GREEN),
                (f"prag {threshold:.0%} (kasa {MIN_CONFIDENCE:.0%})", WHITE),
                (f"{model_name()} {ms:.0f} ms", GREY),
                ("model 640x640" if model_view else "originalna slika", GREY),
                ("PAUZA" if paused else "", YELLOW),
                ("TAB / 1-8  kamera", GREY), ("M  pogled modela", GREY), ("[ ]  prag", GREY),
                ("Z  zuti okviri", GREY), ("RAZMAK  pauza   S  spremi", GREY), ("Q  izlaz", GREY),
            ]
            shown = compose(picture, str(counted), lines)
        cv2.imshow(window, shown)
        key = cv2.waitKey(1 if not paused else 30) & 0xFF
        if key in (ord("q"), 27):
            break
        if key == 9:
            current = (current + 1) % len(names)
            shown = None
        elif ord("1") <= key <= ord("8") and key - ord("1") < len(names):
            current = key - ord("1")
            shown = None
        elif key == ord("m"):
            model_view = not model_view
        elif key == ord("["):
            threshold = max(LOW_CONFIDENCE, round(threshold - 0.05, 2))
        elif key == ord("]"):
            threshold = min(0.95, round(threshold + 0.05, 2))
        elif key == ord("z"):
            show_low = not show_low
        elif key == ord(" "):
            paused = not paused
        elif key == ord("s") and shown is not None:
            SAVE_FOLDER.mkdir(parents=True, exist_ok=True)
            path = SAVE_FOLDER / f"{name}-{datetime.now():%Y%m%d-%H%M%S}.jpg"
            cv2.imwrite(str(path), shown)
            print(f"Spremljeno: {path}")

    for reader in readers:
        reader.stop()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()

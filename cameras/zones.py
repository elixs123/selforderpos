import json
from datetime import datetime
from pathlib import Path

import numpy as np

from locations import zones_file

ZONES_PATH = zones_file()

Zone = tuple[float, float, float, float]


def load_zones() -> dict[str, Zone]:
    if not ZONES_PATH.exists():
        return {}
    data = json.loads(ZONES_PATH.read_text(encoding="utf-8"))
    return {name: tuple(values) for name, values in data.items()}


def zones_changed_at() -> str:
    if not ZONES_PATH.exists():
        return ""
    return datetime.fromtimestamp(ZONES_PATH.stat().st_mtime).isoformat(timespec="seconds")


def save_zone(name: str, zone: Zone) -> None:
    zones = load_zones()
    zones[name] = zone
    ZONES_PATH.write_text(json.dumps(zones, indent=2), encoding="utf-8")


def to_pixels(zone: Zone | None, width: int, height: int) -> tuple[int, int, int, int]:
    if zone is None:
        return 0, 0, width, height
    left, top, zone_width, zone_height = zone
    return round(left * width), round(top * height), round(zone_width * width), round(zone_height * height)


def crop(frame: np.ndarray, zone: Zone | None) -> tuple[np.ndarray, tuple[int, int]]:
    height, width = frame.shape[:2]
    x, y, w, h = to_pixels(zone, width, height)
    return frame[y:y + h, x:x + w], (x, y)

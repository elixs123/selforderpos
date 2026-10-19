import json
from datetime import datetime
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np

from locations import zones_file

ZONES_PATH = zones_file()

OUTSIDE_VALUE = 127


class Zone(tuple):
    """Okvir zone (lijevo, gore, širina, visina) u razmjeru 0-1; polygon je neobavezan slobodno nacrtan oblik unutar okvira."""

    polygon: tuple[tuple[float, float], ...] = ()

    def __new__(cls, box, polygon=()):
        zone = super().__new__(cls, (float(value) for value in box))
        zone.polygon = tuple((float(x), float(y)) for x, y in polygon)
        return zone


def _decode(value) -> Zone:
    if isinstance(value, dict):
        return Zone(value["box"], value.get("polygon", ()))
    return Zone(value)


def _encode(zone: Zone):
    polygon = getattr(zone, "polygon", ())
    if not polygon:
        return list(zone)
    return {"box": list(zone), "polygon": [list(point) for point in polygon]}


def load_zones() -> dict[str, Zone]:
    if not ZONES_PATH.exists():
        return {}
    data = json.loads(ZONES_PATH.read_text(encoding="utf-8"))
    return {name: _decode(value) for name, value in data.items()}


def zones_changed_at() -> str:
    if not ZONES_PATH.exists():
        return ""
    return datetime.fromtimestamp(ZONES_PATH.stat().st_mtime).isoformat(timespec="seconds")


def save_zone(name: str, zone: Zone) -> None:
    zones = load_zones()
    zones[name] = zone
    ZONES_PATH.write_text(json.dumps({key: _encode(value) for key, value in zones.items()}, indent=2), encoding="utf-8")


def to_pixels(zone: Zone | None, width: int, height: int) -> tuple[int, int, int, int]:
    if zone is None:
        return 0, 0, width, height
    left, top, zone_width, zone_height = zone
    return round(left * width), round(top * height), round(zone_width * width), round(zone_height * height)


def outline(zone: Zone | None, width: int, height: int) -> np.ndarray:
    polygon = getattr(zone, "polygon", ())
    if polygon:
        points = [(round(px * width), round(py * height)) for px, py in polygon]
    else:
        x, y, w, h = to_pixels(zone, width, height)
        points = [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
    return np.array(points, np.int32).reshape(-1, 1, 2)


@lru_cache(maxsize=32)
def _inside_mask(polygon: tuple, width: int, height: int, x: int, y: int, w: int, h: int) -> np.ndarray:
    points = np.array([[round(px * width) - x, round(py * height) - y] for px, py in polygon], np.int32)
    mask = np.zeros((h, w), np.uint8)
    cv2.fillPoly(mask, [points], 255)
    return mask == 0


def crop(frame: np.ndarray, zone: Zone | None) -> tuple[np.ndarray, tuple[int, int]]:
    height, width = frame.shape[:2]
    x, y, w, h = to_pixels(zone, width, height)
    region = frame[y:y + h, x:x + w]
    polygon = getattr(zone, "polygon", ())
    if polygon and region.size:
        outside = _inside_mask(polygon, width, height, x, y, region.shape[1], region.shape[0])
        region = region.copy()
        region[outside] = OUTSIDE_VALUE
    return region, (x, y)

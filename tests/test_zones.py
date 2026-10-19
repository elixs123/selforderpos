import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "cameras"))

import zones
from zones import OUTSIDE_VALUE, Zone, crop, load_zones, save_zone, to_pixels


def test_polygon_zone_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(zones, "ZONES_PATH", tmp_path / "zones.json")
    save_zone("A", Zone((0.1, 0.2, 0.5, 0.4), [(0.1, 0.2), (0.6, 0.2), (0.35, 0.6)]))
    save_zone("B", Zone((0.0, 0.0, 1.0, 1.0)))
    loaded = load_zones()
    assert tuple(loaded["A"]) == (0.1, 0.2, 0.5, 0.4)
    assert loaded["A"].polygon == ((0.1, 0.2), (0.6, 0.2), (0.35, 0.6))
    assert loaded["B"].polygon == ()


def test_old_rectangle_file_still_loads(tmp_path, monkeypatch):
    path = tmp_path / "zones.json"
    path.write_text('{"A": [0.5, 0.5, 0.25, 0.5]}', encoding="utf-8")
    monkeypatch.setattr(zones, "ZONES_PATH", path)
    assert to_pixels(load_zones()["A"], 200, 100) == (100, 50, 50, 50)


def test_crop_hides_pixels_outside_polygon():
    frame = np.full((100, 100, 3), 200, np.uint8)
    zone = Zone((0.0, 0.0, 1.0, 1.0), [(0.0, 0.0), (1.0, 0.0), (0.0, 1.0)])
    region, offset = crop(frame, zone)
    assert offset == (0, 0)
    assert region[5, 5, 0] == 200
    assert region[95, 95, 0] == OUTSIDE_VALUE
    assert frame[95, 95, 0] == 200


def test_crop_without_polygon_is_plain_rectangle():
    frame = np.arange(100 * 100 * 3, dtype=np.uint8).reshape(100, 100, 3)
    region, _ = crop(frame, Zone((0.5, 0.5, 0.25, 0.5)))
    assert region.shape == (50, 25, 3)
    assert np.array_equal(region, frame[50:100, 50:75])

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "cameras"))

from zones import OUTSIDE_VALUE, Zone, _decode, _encode, crop


def test_excluded_area_is_grey_and_survives_saving():
    zone = Zone((0.0, 0.0, 1.0, 1.0), (), [[(0.5, 0.0), (1.0, 0.0), (1.0, 1.0), (0.5, 1.0)]])
    zone = _decode(_encode(zone))
    frame = np.full((100, 200, 3), 30, np.uint8)
    region, offset = crop(frame, zone)
    assert offset == (0, 0)
    assert (region[:, :90] == 30).all()
    assert (region[:, 110:] == OUTSIDE_VALUE).all()
    assert (frame == 30).all()


def test_zone_without_exclude_is_saved_as_before():
    assert _encode(Zone((0.1, 0.2, 0.3, 0.4))) == [0.1, 0.2, 0.3, 0.4]

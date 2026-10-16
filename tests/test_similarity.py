import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "cameras"))

from similarity import color_similarity


def bottle(color: tuple[int, int, int]) -> np.ndarray:
    image = np.full((120, 80, 3), 235, dtype=np.uint8)
    image[5:115, 5:75] = color
    return image


def test_same_colour_in_different_light_is_similar():
    assert color_similarity(bottle((40, 160, 60)), bottle((55, 175, 75))) > 0.8


def test_neighbour_in_corner_does_not_ruin_colour():
    crowded = bottle((40, 160, 60))
    crowded[0:30, 50:80] = (30, 200, 230)
    assert color_similarity(bottle((40, 160, 60)), crowded) > 0.7


def test_different_colour_is_not_similar():
    assert color_similarity(bottle((40, 160, 60)), bottle((30, 200, 230))) < 0.5


def test_references_before_zones_changed_are_ignored(tmp_path):
    from samples import SampleStore

    store = SampleStore(tmp_path)
    image = np.full((40, 40, 3), 120, dtype=np.uint8)
    store.save("placed", "1001", "A1", "Mlijeko", "B", crop_image=image, verdict="learned")
    assert len(store.reference_paths("A1")) == 1
    assert len(store.reference_paths("A1", since="2000-01-01T00:00:00")) == 1
    assert store.reference_paths("A1", since="2999-01-01T00:00:00") == []
    assert store.old_reference_count("A1", "2999-01-01T00:00:00") == 1
    assert store.old_reference_count("A1", "") == 0

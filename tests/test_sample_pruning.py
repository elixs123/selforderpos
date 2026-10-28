import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "cameras"))

from samples import SampleStore

IMAGE = np.full((20, 20, 3), 128, np.uint8)


def saved(store, camera, verdict, quality, event="placed", code="090822"):
    return store.save(event, "1", code, "Kiseljak", camera, crop_image=IMAGE, full_image=IMAGE, verdict=verdict, quality=quality)


def paths(store):
    return sorted(path.name for path in store.folder.rglob("*.jpg"))


def test_keeps_best_images_per_camera_and_deletes_files(tmp_path):
    store = SampleStore(tmp_path)
    low = saved(store, "B", "ok", 0.76)
    best = saved(store, "B", "learned", 0.95)
    staff = saved(store, "B", "verified", None)
    other_camera = saved(store, "B3", "ok", 0.5)
    rejected = saved(store, "B", "bad_reference", 0.3)
    assert store.prune("090822", keep=2) == 1
    remaining = {row[0] for row in __import__("sqlite3").connect(store.database).execute("SELECT id FROM samples")}
    assert remaining == {best, staff, other_camera, rejected}
    assert len(paths(store)) == 8


def test_old_unused_images_are_cleaned_but_references_stay(tmp_path):
    store = SampleStore(tmp_path)
    saved(store, "B", "mismatch", None)
    saved(store, "B", "ok", 0.9)
    later = datetime.now() + timedelta(days=31)
    assert store.cleanup(later) == 1
    assert store.count() == 1
    assert len(paths(store)) == 1

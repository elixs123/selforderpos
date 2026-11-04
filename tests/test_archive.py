import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "cameras"))

from archive import ImageArchive

# Tri "strane" artikla; slike iste strane imaju skoro isti otisak.
SIDES = {"front": [1.0, 0.0, 0.0], "back": [0.0, 1.0, 0.0], "side": [0.0, 0.0, 1.0]}


def crop_file(folder: Path, name: str, side: str) -> Path:
    image = np.zeros((40, 30, 3), dtype=np.uint8)
    image[0, 0] = [list(SIDES).index(side), 0, 0]
    path = folder / f"{name}.png"
    cv2.imwrite(str(path), image)
    return path


def fake_embed(image):
    side = list(SIDES)[int(image[0, 0, 0])]
    return np.array(SIDES[side]) + np.random.default_rng(int(image.sum())).normal(0, 0.01, 3)


def make_archive(tmp_path, monkeypatch, keep=3):
    monkeypatch.setenv("CAM_ARCHIVE_PER_ARTICLE", str(keep))
    return ImageArchive(tmp_path / "archive", fake_embed, lambda: "clip", background=False)


def add(archive, source, quality=0.5, verdict="ok", code="079643"):
    return archive.add(source, code, "3850102", "MLIJEKO", "B", "placed", verdict, quality)


def test_keeps_different_sides_instead_of_many_fronts(tmp_path, monkeypatch):
    archive = make_archive(tmp_path, monkeypatch, keep=3)
    for index in range(4):
        add(archive, crop_file(tmp_path, f"front{index}", "front"), quality=0.5 + index / 100)
    add(archive, crop_file(tmp_path, "back", "back"))
    add(archive, crop_file(tmp_path, "side", "side"))
    archive.process_pending()

    summary = archive.summary()
    assert summary["images"] == 3
    files = list((tmp_path / "archive" / "079643").glob("*.jpg"))
    assert len(files) == 3
    kept = sorted(list(SIDES)[int(cv2.imread(str(path))[0, 0, 0])] for path in files)
    assert kept == ["back", "front", "side"]


def test_among_similar_images_better_quality_stays(tmp_path, monkeypatch):
    archive = make_archive(tmp_path, monkeypatch, keep=1)
    add(archive, crop_file(tmp_path, "good", "front"), quality=0.9)
    add(archive, crop_file(tmp_path, "bad", "front"), quality=0.2)
    archive.process_pending()
    with archive._connect() as connection:
        assert [row["quality"] for row in connection.execute("SELECT quality FROM images")] == [0.9]


def test_staff_verified_image_is_kept(tmp_path, monkeypatch):
    archive = make_archive(tmp_path, monkeypatch, keep=1)
    add(archive, crop_file(tmp_path, "verified", "front"), quality=0.1, verdict="verified")
    add(archive, crop_file(tmp_path, "ok", "front"), quality=0.9)
    archive.process_pending()
    with archive._connect() as connection:
        assert [row["verdict"] for row in connection.execute("SELECT verdict FROM images")] == ["verified"]


def test_without_model_keeps_best_quality(tmp_path, monkeypatch):
    monkeypatch.setenv("CAM_ARCHIVE_PER_ARTICLE", "2")
    archive = ImageArchive(tmp_path / "archive", None, background=False)
    for quality in (0.3, 0.8, 0.5):
        add(archive, crop_file(tmp_path, f"q{quality}", "front"), quality=quality)
    archive.process_pending()
    with archive._connect() as connection:
        assert sorted(row["quality"] for row in connection.execute("SELECT quality FROM images")) == [0.5, 0.8]


def test_full_archive_stops_saving(tmp_path, monkeypatch):
    monkeypatch.setenv("CAM_ARCHIVE_GB", str(1 / 1024 ** 3))  # 1 bajt
    archive = make_archive(tmp_path, monkeypatch)
    assert add(archive, crop_file(tmp_path, "front", "front")) is None
    assert archive.summary()["images"] == 0


def test_articles_are_separate_and_unknown_is_skipped(tmp_path, monkeypatch):
    archive = make_archive(tmp_path, monkeypatch, keep=1)
    add(archive, crop_file(tmp_path, "a", "front"), code="079643")
    add(archive, crop_file(tmp_path, "b", "front"), code="012345")
    assert add(archive, crop_file(tmp_path, "c", "front"), code=None) is None
    archive.process_pending()
    assert archive.summary() == {"images": 2, "products": 2, "bytes": archive.total_bytes()}

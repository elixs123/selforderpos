import os
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

from locations import app_folder

DEFAULT_FOLDER = app_folder() / "data" / "samples"

SCHEMA = """
CREATE TABLE IF NOT EXISTS samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    event TEXT NOT NULL,
    barcode TEXT NOT NULL,
    product_code TEXT,
    product_name TEXT,
    camera TEXT NOT NULL,
    crop_path TEXT,
    full_path TEXT,
    change_ratio REAL
)
"""

EXTRA_COLUMNS = {"verdict": "TEXT", "score_taken": "REAL", "score_product": "REAL"}

INSERT = """
INSERT INTO samples (created_at, event, barcode, product_code, product_name, camera, crop_path, full_path,
                     change_ratio, verdict, score_taken, score_product)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

REFERENCES = """
SELECT {column} FROM samples
WHERE product_code = ? AND event = 'placed' AND verdict IN ('learned', 'ok', 'verified') AND {column} IS NOT NULL
AND created_at >= ?
ORDER BY verdict = 'verified' DESC, id DESC LIMIT ?
"""

TAKEN_REFERENCES = """
SELECT crop_path FROM samples
WHERE product_code = ? AND event = 'taken' AND verdict IN ('ok', 'verified') AND crop_path IS NOT NULL AND created_at >= ?
ORDER BY verdict = 'verified' DESC, id DESC LIMIT ?
"""

OTHER_REFERENCES = """
SELECT product_code, product_name, crop_path FROM samples
WHERE product_code IS NOT NULL AND product_code != ? AND event = 'placed' AND verdict IN ('learned', 'ok', 'verified')
AND crop_path IS NOT NULL AND created_at >= ?
ORDER BY verdict = 'verified' DESC, id DESC LIMIT ?
"""

OLD_REFERENCES = """
SELECT COUNT(*) FROM samples
WHERE product_code = ? AND event = 'placed' AND verdict IN ('learned', 'ok', 'verified') AND crop_path IS NOT NULL
AND created_at < ?
"""


class SampleStore:
    def __init__(self, folder: Path | None = None) -> None:
        self.folder = folder or Path(os.environ.get("SAMPLES_DIR", DEFAULT_FOLDER))
        self.folder.mkdir(parents=True, exist_ok=True)
        self.database = self.folder / "samples.db"
        with closing(sqlite3.connect(self.database)) as connection, connection:
            connection.execute(SCHEMA)
            existing = {row[1] for row in connection.execute("PRAGMA table_info(samples)")}
            for name, kind in EXTRA_COLUMNS.items():
                if name not in existing:
                    connection.execute(f"ALTER TABLE samples ADD COLUMN {name} {kind}")

    def _write_image(self, subfolder: str, name: str, image: np.ndarray | None) -> str | None:
        if image is None or image.size == 0:
            return None
        target = self.folder / subfolder
        target.mkdir(parents=True, exist_ok=True)
        path = target / name
        cv2.imwrite(str(path), image)
        return str(path.relative_to(self.folder))

    def save(
        self,
        event: str,
        barcode: str,
        product_code: str | None,
        product_name: str | None,
        camera: str,
        crop_image: np.ndarray | None = None,
        full_image: np.ndarray | None = None,
        change_ratio: float | None = None,
        verdict: str | None = None,
        score_taken: float | None = None,
        score_product: float | None = None,
    ) -> int:
        now = datetime.now()
        stamp = now.strftime("%Y%m%d-%H%M%S-%f")
        subfolder = product_code or barcode
        crop_path = self._write_image(subfolder, f"{stamp}-{camera}-{event}-crop.jpg", crop_image)
        full_path = self._write_image(subfolder, f"{stamp}-{camera}-{event}-full.jpg", full_image)
        with closing(sqlite3.connect(self.database)) as connection, connection:
            cursor = connection.execute(
                INSERT,
                (now.isoformat(timespec="seconds"), event, barcode, product_code, product_name, camera, crop_path,
                 full_path, change_ratio, verdict, score_taken, score_product),
            )
            return cursor.lastrowid

    def reference_paths(self, product_code: str | None, limit: int = 10, since: str = "") -> list[str]:
        if not product_code:
            return []
        query = REFERENCES.format(column="crop_path")
        with closing(sqlite3.connect(self.database)) as connection:
            return [row[0] for row in connection.execute(query, (product_code, since, limit)).fetchall()]

    def other_reference_paths(self, product_code: str | None, limit: int = 60, since: str = "") -> list[tuple[str, str, str]]:
        with closing(sqlite3.connect(self.database)) as connection:
            return [(row[0], row[1] or row[0], row[2])
                    for row in connection.execute(OTHER_REFERENCES, (product_code or "", since, limit)).fetchall()]

    def taken_reference_paths(self, product_code: str | None, limit: int = 20, since: str = "") -> list[str]:
        if not product_code:
            return []
        with closing(sqlite3.connect(self.database)) as connection:
            return [row[0] for row in connection.execute(TAKEN_REFERENCES, (product_code, since, limit)).fetchall()]

    def mark_taken_reference(self, sample_id: int | None) -> None:
        if sample_id is None:
            return
        with closing(sqlite3.connect(self.database)) as connection, connection:
            connection.execute("UPDATE samples SET verdict = 'ok' WHERE id = ? AND event = 'taken' AND verdict IS NULL", (sample_id,))

    def mark_verified(self, sample_ids: list[int | None]) -> None:
        ids = [sample_id for sample_id in sample_ids if sample_id is not None]
        if not ids:
            return
        with closing(sqlite3.connect(self.database)) as connection, connection:
            connection.executemany("UPDATE samples SET verdict = 'verified' WHERE id = ?", [(sample_id,) for sample_id in ids])

    def old_reference_count(self, product_code: str | None, since: str) -> int:
        if not product_code or not since:
            return 0
        with closing(sqlite3.connect(self.database)) as connection:
            return connection.execute(OLD_REFERENCES, (product_code, since)).fetchone()[0]

    def load_image(self, relative_path: str) -> np.ndarray | None:
        path = self.folder / relative_path
        if not path.is_file():
            return None
        return cv2.imread(str(path))

    def references(self, product_code: str | None, limit: int = 10) -> list[np.ndarray]:
        images = [self.load_image(path) for path in self.reference_paths(product_code, limit)]
        return [image for image in images if image is not None]

    def reference_sizes(self, product_code: str | None, limit: int = 10, since: str = "") -> list[float]:
        if not product_code:
            return []
        query = REFERENCES.format(column="change_ratio")
        with closing(sqlite3.connect(self.database)) as connection:
            return [row[0] for row in connection.execute(query, (product_code, since, limit)).fetchall()]

    def count(self) -> int:
        with closing(sqlite3.connect(self.database)) as connection:
            return connection.execute("SELECT COUNT(*) FROM samples").fetchone()[0]

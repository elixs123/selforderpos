import os
import queue
import shutil
import sqlite3
import threading
from contextlib import closing
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

SCHEMA = """
CREATE TABLE IF NOT EXISTS images (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    product_code TEXT NOT NULL,
    barcode TEXT,
    product_name TEXT,
    camera TEXT NOT NULL,
    event TEXT NOT NULL,
    verdict TEXT,
    quality REAL,
    path TEXT NOT NULL,
    size INTEGER NOT NULL DEFAULT 0,
    model TEXT,
    embedding BLOB
)
"""

EXTRA_COLUMNS = {"score": "REAL"}

# Izmjereno na prvim arhiviranim slikama: izrezi kamere izdaleka su ~80 px (premalo detalja), a prazna
# podloga bez artikla ima oštrinu 4-25; najmekša prava slika (glatka zelena flaša) ima 79.
MIN_SIDE = 120
MIN_SHARPNESS = 30.0
# Slika ove veličine/oštrine i više dobija punu ocjenu; manja i mekša ispada prva kad artikal ima previše slika.
GOOD_SIDE = 250
GOOD_SHARPNESS = 150.0
# Izrez iz zone A nema ocjenu kase (quality); tada se uzima ova.
DEFAULT_QUALITY = 0.85


def sharpness(image: np.ndarray) -> float:
    return float(cv2.Laplacian(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY), cv2.CV_64F).var())


def image_problem(image: np.ndarray | None) -> str:
    """Zašto slika ne ide u arhivu (prazno = dobra)."""
    if image is None or not image.size:
        return "nema slike"
    if min(image.shape[:2]) < MIN_SIDE:
        return f"premala ({image.shape[1]}x{image.shape[0]} px)"
    if sharpness(image) < MIN_SHARPNESS:
        return "nema detalja (prazna podloga ili mutno)"
    return ""


def image_score(image: np.ndarray, quality: float | None) -> float:
    size = min(1.0, min(image.shape[:2]) / GOOD_SIDE)
    sharp = min(1.0, sharpness(image) / GOOD_SHARPNESS)
    return round((DEFAULT_QUALITY if quality is None else quality) * size * sharp, 4)


def enabled() -> bool:
    """Arhiva izgleda artikla (CAM_ARCHIVE, zadano uključena)."""
    return os.environ.get("CAM_ARCHIVE", "da").lower() not in ("", "off", "0", "ne")


def per_article() -> int:
    return int(os.environ.get("CAM_ARCHIVE_PER_ARTICLE", "50") or 50)


def max_bytes() -> int:
    return int(float(os.environ.get("CAM_ARCHIVE_GB", "50") or 50) * 1024 ** 3)


class ImageArchive:
    """Za svaki artikal do per_article() najboljih i najrazličitijih izreza (sve strane artikla, sve kamere).

    Slike iz prodaje dolaze stalno; kad artikal ima previše slika, briše se ona koja najviše liči na neku drugu
    (ista strana, isti ugao), i to slabija od te dvije. Tako ostaju različiti uglovi, a ne 50 slika prednje etikete.
    Služi za kasnije dotreniranje modela prepoznavanja; na samo prepoznavanje u kasi ne utiče.
    """

    def __init__(self, folder: Path, embed=None, model_name=lambda: "", background: bool = True) -> None:
        self.folder = folder
        self.folder.mkdir(parents=True, exist_ok=True)
        self.database = folder / "archive.db"
        self._embed = embed
        self._model_name = model_name
        self._background = background
        self._queue: queue.Queue[int] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._full_reported = False
        with closing(sqlite3.connect(self.database)) as connection, connection:
            connection.execute(SCHEMA)
            existing = {row[1] for row in connection.execute("PRAGMA table_info(images)")}
            for name, kind in EXTRA_COLUMNS.items():
                if name not in existing:
                    connection.execute(f"ALTER TABLE images ADD COLUMN {name} {kind}")
            connection.execute("CREATE INDEX IF NOT EXISTS images_product ON images (product_code)")
            # Slike koje nisu obrađene prije gašenja servera idu ponovo u red.
            for (image_id,) in connection.execute("SELECT id FROM images WHERE model IS NULL ORDER BY id"):
                self._queue.put(image_id)
        if background and not self._queue.empty():
            self._start()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def add(self, source: Path, product_code: str | None, barcode: str | None, product_name: str | None,
            camera: str, event: str, verdict: str | None, quality: float | None, created_at: str | None = None) -> int | None:
        """Kopira izrez u arhivu (odmah, jer kasa original uskoro briše); otisak i izbor slika idu u pozadini."""
        if not product_code or not source.is_file():
            return None
        size = source.stat().st_size
        if self.total_bytes() + size > max_bytes():
            if not self._full_reported:
                print(f"Arhiva izgleda artikla je puna ({max_bytes() / 1024 ** 3:.0f} GB, CAM_ARCHIVE_GB); nove slike se ne spremaju.")
                self._full_reported = True
            return None
        target = self.folder / product_code / f"{datetime.now():%Y%m%d-%H%M%S-%f}-{camera}-{event}.jpg"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        with closing(self._connect()) as connection, connection:
            image_id = connection.execute(
                "INSERT INTO images (created_at, product_code, barcode, product_name, camera, event, verdict, quality, path, size)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (created_at or datetime.now().isoformat(timespec="seconds"), product_code, barcode, product_name, camera, event,
                 verdict, quality, str(target.relative_to(self.folder)), size),
            ).lastrowid
        self._queue.put(image_id)
        if self._background:
            self._start()
        return image_id

    def _start(self) -> None:
        with self._lock:
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(target=self._work, daemon=True)
                self._thread.start()

    def _work(self) -> None:
        while True:
            image_id = self._queue.get()
            try:
                self._process(image_id)
            except Exception as error:
                print(f"Arhiva izgleda artikla: {error!r}")

    def process_pending(self) -> None:
        """Obradi sve što čeka (za testove i kad nema pozadinske niti)."""
        while not self._queue.empty():
            self._process(self._queue.get())

    def _process(self, image_id: int) -> None:
        with closing(self._connect()) as connection:
            row = connection.execute("SELECT product_code, path, quality FROM images WHERE id = ?", (image_id,)).fetchone()
        if row is None:
            return
        image = cv2.imread(str(self.folder / row["path"]))
        problem = image_problem(image)
        if problem:
            self.delete(image_id)
            return
        embedding = None
        if self._embed is not None:
            vector = self._embed(image)
            if vector is not None:
                vector = np.asarray(vector, dtype=np.float32).reshape(-1)
                vector /= max(float(np.linalg.norm(vector)), 1e-6)
                embedding = vector.tobytes()
        # model != NULL znači da je slika obrađena (i kad otisak nije uspio); tek tad smije u izbor za brisanje.
        with closing(self._connect()) as connection, connection:
            connection.execute("UPDATE images SET model = ?, embedding = ?, score = ? WHERE id = ?",
                               (self._model_name() if embedding is not None else "", embedding,
                                image_score(image, row["quality"]), image_id))
        self.trim(row["product_code"])

    def trim(self, product_code: str, keep: int | None = None) -> int:
        keep = per_article() if keep is None else keep
        removed = 0
        with closing(self._connect()) as connection, connection:
            rows = [dict(row) for row in connection.execute(
                "SELECT id, verdict, score, path, model, embedding FROM images WHERE product_code = ? ORDER BY id",
                (product_code,))]
            # Dok neka slika artikla čeka otisak, ne bira se šta brisati (ne zna se još s koje je strane artikla).
            if any(row["model"] is None for row in rows):
                return 0
            while len(rows) > keep:
                victim = self._victim(rows)
                (self.folder / victim["path"]).unlink(missing_ok=True)
                connection.execute("DELETE FROM images WHERE id = ?", (victim["id"],))
                rows.remove(victim)
                removed += 1
        return removed

    @staticmethod
    def _rank(row: dict) -> tuple:
        # Osoblje potvrđene slike su najsigurnije; zatim ocjena (kasa x veličina x oštrina); kod iste, novija ostaje.
        return (row["verdict"] == "verified", row["score"] or 0.0, row["id"])

    def _victim(self, rows: list[dict]) -> dict:
        model = self._model_name()
        embedded = [row for row in rows if row["embedding"] is not None and row["model"] == model]
        if len(embedded) >= 2:
            vectors = np.stack([np.frombuffer(row["embedding"], dtype=np.float32) for row in embedded])
            similar = vectors @ vectors.T
            np.fill_diagonal(similar, -1.0)
            first, second = np.unravel_index(int(np.argmax(similar)), similar.shape)
            return min(embedded[first], embedded[second], key=self._rank)
        return min(rows, key=self._rank)

    def delete(self, image_id: int) -> bool:
        with closing(self._connect()) as connection, connection:
            row = connection.execute("SELECT path FROM images WHERE id = ?", (image_id,)).fetchone()
            if row is None:
                return False
            (self.folder / row["path"]).unlink(missing_ok=True)
            connection.execute("DELETE FROM images WHERE id = ?", (image_id,))
        return True

    def recheck(self) -> int:
        """Ponovo ocijeni sve slike (npr. poslije promjene pravila); loše briše. Vraća broj obrisanih."""
        with closing(self._connect()) as connection:
            ids = [row[0] for row in connection.execute("SELECT id FROM images ORDER BY id")]
        before = self.summary()["images"]
        for image_id in ids:
            self._process(image_id)
        return before - self.summary()["images"]

    def products(self) -> list[dict]:
        """Artikli u arhivi: šifra, naziv, broj slika (kao reference_products za ekran Slike artikala)."""
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT product_code, MAX(product_name), COUNT(*) FROM images GROUP BY product_code ORDER BY MAX(product_name)"
            ).fetchall()
        return [{"code": code, "name": name or code, "count": count} for code, name, count in rows]

    def images(self, product_code: str) -> list[dict]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT id, created_at, camera, event, verdict, score FROM images WHERE product_code = ?"
                " ORDER BY event DESC, camera, id DESC", (product_code,)).fetchall()
        # Izrez iz zone A nosi redni broj uzimanja (A1, A2...) umjesto kamere, pa se prikazuje samo zona.
        return [{"id": row["id"], "created_at": row["created_at"],
                 "camera": row["camera"] if row["event"] == "placed" else "zona A",
                 "verdict": row["verdict"], "quality": row["score"]} for row in rows]

    def crop_bytes(self, image_id: int) -> bytes | None:
        with closing(self._connect()) as connection:
            row = connection.execute("SELECT path FROM images WHERE id = ?", (image_id,)).fetchone()
        if row is None:
            return None
        try:
            return (self.folder / row["path"]).read_bytes()
        except OSError:
            return None

    def total_bytes(self) -> int:
        with closing(self._connect()) as connection:
            return int(connection.execute("SELECT COALESCE(SUM(size), 0) FROM images").fetchone()[0])

    def summary(self) -> dict:
        with closing(self._connect()) as connection:
            images, products = connection.execute("SELECT COUNT(*), COUNT(DISTINCT product_code) FROM images").fetchone()
        return {"images": images, "products": products, "bytes": self.total_bytes()}

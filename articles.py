import sqlite3
import threading
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from database import DatabaseError, connect

SCHEMA = """
CREATE TABLE IF NOT EXISTS articles (
    code TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    price REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS barcodes (
    barcode TEXT PRIMARY KEY,
    code TEXT NOT NULL REFERENCES articles(code)
);
CREATE TABLE IF NOT EXISTS article_sync (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    synced_at TEXT,
    article_count INTEGER NOT NULL DEFAULT 0,
    barcode_count INTEGER NOT NULL DEFAULT 0,
    message TEXT
);
"""

SERVER_QUERY = """
SELECT i.acIdent, b.acCode, i.acName, i.anSalePrice
FROM tHE_SetItem i
LEFT JOIN tHE_SetItemExtItemSubj b ON b.acIdent = i.acIdent
"""


@dataclass(frozen=True)
class SyncResult:
    ok: bool
    message: str
    article_count: int = 0
    barcode_count: int = 0


class ArticleStore:
    """Lokalna kopija artikala i barkodova sa centralnog servera (tabele u kasa.db)."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._sync_lock = threading.Lock()
        path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as connection, connection:
            connection.executescript(SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def find(self, barcode: str):
        from catalog import Product

        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT a.code, b.barcode, a.name, a.price FROM barcodes b JOIN articles a ON a.code = b.code WHERE b.barcode = ?",
                (barcode,),
            ).fetchone()
            if row is None:
                row = connection.execute(
                    "SELECT code, code AS barcode, name, price FROM articles WHERE code = ?", (barcode,)
                ).fetchone()
        if row is None:
            return None
        return Product(row["code"], row["barcode"], row["name"], row["price"])

    def names(self) -> list[tuple[str, str]]:
        """(šifra, naziv) svih artikala; kamere njima provjeravaju šta piše na etiketi."""
        with closing(self._connect()) as connection:
            return [(row["code"], row["name"]) for row in connection.execute("SELECT code, name FROM articles")]

    def article_count(self) -> int:
        with closing(self._connect()) as connection:
            return connection.execute("SELECT COUNT(*) FROM articles").fetchone()[0]

    def last_sync(self) -> dict | None:
        with closing(self._connect()) as connection:
            row = connection.execute("SELECT * FROM article_sync WHERE id = 1").fetchone()
        return dict(row) if row else None

    def replace_all(self, rows) -> tuple[int, int]:
        """rows: (code, barcode ili None, name, price). Zamijeni sve artikle u jednoj transakciji."""
        articles: dict[str, tuple[str, float]] = {}
        barcodes: dict[str, str] = {}
        for code, barcode, name, price in rows:
            if code is None or price is None:
                continue
            code = str(code).strip()
            articles[code] = ((name or "").strip(), float(price))
            if barcode is not None and str(barcode).strip():
                barcodes[str(barcode).strip()] = code
        if not articles:
            raise ValueError("server nije vratio nijedan artikal")
        with closing(self._connect()) as connection, connection:
            connection.execute("DELETE FROM barcodes")
            connection.execute("DELETE FROM articles")
            connection.executemany(
                "INSERT INTO articles (code, name, price) VALUES (?, ?, ?)",
                [(code, name, price) for code, (name, price) in articles.items()],
            )
            connection.executemany("INSERT INTO barcodes (barcode, code) VALUES (?, ?)", list(barcodes.items()))
        return len(articles), len(barcodes)

    def _remember(self, result: SyncResult) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        with closing(self._connect()) as connection, connection:
            if result.ok:
                connection.execute(
                    "INSERT OR REPLACE INTO article_sync (id, synced_at, article_count, barcode_count, message) VALUES (1, ?, ?, ?, ?)",
                    (now, result.article_count, result.barcode_count, result.message),
                )
            else:
                connection.execute("INSERT OR IGNORE INTO article_sync (id) VALUES (1)")
                connection.execute("UPDATE article_sync SET message = ? WHERE id = 1", (f"{now}: {result.message}",))

    def sync(self, fetch=None) -> SyncResult:
        """Povuci sve artikle i barkodove sa servera. Ako ne uspije, lokalni artikli ostaju kakvi su bili."""
        if not self._sync_lock.acquire(blocking=False):
            return SyncResult(False, "Sinhronizacija je već u toku.")
        try:
            try:
                rows = (fetch or fetch_from_server)()
                article_count, barcode_count = self.replace_all(rows)
                result = SyncResult(True, "Artikli su sinhronizovani.", article_count, barcode_count)
            except (DatabaseError, ValueError) as error:
                result = SyncResult(False, f"Sinhronizacija nije uspjela: {error}")
            except Exception as error:
                result = SyncResult(False, f"Sinhronizacija nije uspjela: {error!r}")
            self._remember(result)
            print(f"Artikli: {result.message} ({result.article_count} artikala, {result.barcode_count} barkodova)")
            return result
        finally:
            self._sync_lock.release()


def fetch_from_server() -> list[tuple]:
    with closing(connect()) as connection:
        return [tuple(row) for row in connection.execute(SERVER_QUERY).fetchall()]

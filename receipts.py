import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path

from cart import Cart

SCHEMA = """
CREATE TABLE IF NOT EXISTS receipts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    number TEXT UNIQUE,
    created_at TEXT NOT NULL,
    payment_method TEXT NOT NULL,
    item_count INTEGER NOT NULL,
    total REAL NOT NULL,
    synced INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS receipt_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    receipt_id INTEGER NOT NULL REFERENCES receipts(id),
    code TEXT NOT NULL,
    barcode TEXT NOT NULL,
    name TEXT NOT NULL,
    price REAL NOT NULL,
    quantity INTEGER NOT NULL,
    amount REAL NOT NULL
);
"""

EXTRA_COLUMNS = {
    "payment_reference": "TEXT",
    "approval_code": "TEXT",
    "rrn": "TEXT",
    "bank_id": "TEXT",
    "card_number": "TEXT",
    "fiscal_printed": "INTEGER NOT NULL DEFAULT 0",
    "fiscal_message": "TEXT",
}

INSERT_RECEIPT = """
INSERT INTO receipts (created_at, payment_method, item_count, total, payment_reference, approval_code, rrn, bank_id, card_number)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

INSERT_ITEM = """
INSERT INTO receipt_items (receipt_id, code, barcode, name, price, quantity, amount)
VALUES (?, ?, ?, ?, ?, ?, ?)
"""


class ReceiptStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as connection, connection:
            connection.executescript(SCHEMA)
            existing = {row[1] for row in connection.execute("PRAGMA table_info(receipts)")}
            for name, kind in EXTRA_COLUMNS.items():
                if name not in existing:
                    connection.execute(f"ALTER TABLE receipts ADD COLUMN {name} {kind}")

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def save(self, cart: Cart, payment_method: str, payment: dict | None = None) -> str:
        data = cart.to_dict()
        payment = payment or {}
        now = datetime.now()
        with closing(self._connect()) as connection, connection:
            cursor = connection.execute(
                INSERT_RECEIPT,
                (
                    now.isoformat(timespec="seconds"), payment_method, data["item_count"], data["total"],
                    payment.get("invoice_id"), payment.get("approval_code"), payment.get("rrn"),
                    payment.get("bank_id"), payment.get("card_number"),
                ),
            )
            receipt_id = cursor.lastrowid
            number = f"{now:%Y}-{receipt_id:06d}"
            connection.execute("UPDATE receipts SET number = ? WHERE id = ?", (number, receipt_id))
            connection.executemany(
                INSERT_ITEM,
                [
                    (receipt_id, item["code"], item["barcode"], item["name"], item["price"], item["quantity"], item["amount"])
                    for item in data["items"]
                ],
            )
        return number

    def receipt_id(self, number: str) -> int:
        with closing(self._connect()) as connection:
            row = connection.execute("SELECT id FROM receipts WHERE number = ?", (number,)).fetchone()
        return row[0] if row else 0

    def mark_fiscal(self, number: str, printed: bool, message: str) -> None:
        with closing(self._connect()) as connection, connection:
            connection.execute(
                "UPDATE receipts SET fiscal_printed = ?, fiscal_message = ? WHERE number = ?",
                (1 if printed else 0, message, number),
            )

    def unsynced(self) -> list[dict]:
        with closing(self._connect()) as connection:
            rows = connection.execute("SELECT * FROM receipts WHERE synced = 0 ORDER BY id").fetchall()
        return [dict(row) for row in rows]

    def items(self, number: str) -> list[dict]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT ri.* FROM receipt_items ri JOIN receipts r ON r.id = ri.receipt_id WHERE r.number = ? ORDER BY ri.id",
                (number,),
            ).fetchall()
        return [dict(row) for row in rows]

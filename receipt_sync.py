import threading
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime

from database import DatabaseError, connect
from receipts import ReceiptStore

# Način plaćanja na kasi -> acPayMethod u Pantheonu (tHE_SetPayMet)
PAY_METHODS = {"card": "K", "qr": "Q"}

DOC_TYPE_QUERY = "SELECT acIssuer, acReceiver, acDept, acAcctCR FROM tPA_SetDocType WHERE acDocType = ?"

ITEMS_QUERY = """
SELECT i.acIdent, i.acUM, i.acVATCode, t.anVAT
FROM tHE_SetItem i
LEFT JOIN tHE_SetTax t ON t.acVATCode = i.acVATCode
WHERE i.acIdent IN ({})
"""

INSERT_MOVE = """
INSERT INTO tHE_Move (acKey, acDocType, adDate, adDateInv, adDateDue, adDateVAT,
    acReceiver, acIssuer, acDept, acReceiverStock, acIssuerStock, acWayOfSale, acPriceRate, acPayMethod,
    acCurrency, anFXRate, anValue, anVAT, anForPay, anCurrValue, acAcctClaimLiab, acFiskPrintNo, adTimeIns)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'N', 'Y', 'K', '1', ?, 'KM', 1, ?, ?, ?, ?, ?, ?, ?)
"""

INSERT_MOVE_ITEM = """
INSERT INTO tHE_MoveItem (acKey, anNo, acIdent, acName, anQty, acUM, anPrice, acVATCode, anVAT,
    anRTPrice, anSalePrice, anRetailPrice, acDept, acVATCodeTR, anVATIn,
    anPVValue, anPVVATBase, anPVVAT, anPVForPay, anPVOCValue, anPVOCVATBase, anPVOCVAT, anPVOCForPay,
    anUMToUM3, anQtyConverted, acUMConverted, adTimeIns)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?)
"""

INSERT_MOVE_CASH = """
INSERT INTO tHE_MoveCash (acKey, anNo, acPayMethod, anAmount, acCurrency, anAmountCurr, acIsRefund, adTimeIns)
VALUES (?, 1, ?, ?, 'KM', ?, 'F', ?)
"""


def pantheon_key(number: str) -> str:
    """26-3257-000001 -> 2632570000001 (acKey u Pantheonu ima brojač na 7 cifara)."""
    year, doc_type, counter = number.split("-")
    return f"{year}{doc_type}{int(counter):07d}"


@dataclass(frozen=True)
class SyncResult:
    sent: int
    failed: int
    message: str


class ReceiptSync:
    """Šalje račune iz kasa.db u Pantheon (tHE_Move, tHE_MoveItem, tHE_MoveCash).

    Račun se uvijek prvo sprema lokalno; ako server nije dostupan, ostaje neposlan i šalje se kasnije.
    """

    def __init__(self, store: ReceiptStore, connect=connect) -> None:
        self.store = store
        self._connect = connect
        self._lock = threading.Lock()

    def send_pending(self, fiscal_required: bool = True) -> SyncResult:
        if not self._lock.acquire(blocking=False):
            return SyncResult(0, 0, "Slanje računa je već u toku.")
        try:
            receipts = self.store.unsent(fiscal_required)
            if not receipts:
                return SyncResult(0, 0, "Nema računa za slanje.")
            try:
                connection = self._connect()
            except Exception as error:
                message = f"Server nije dostupan: {error}"
                for receipt in receipts:
                    self.store.mark_synced(receipt["number"], False, message)
                print(f"Računi: {len(receipts)} čeka slanje. {message[:200]}")
                return SyncResult(0, len(receipts), message)
            sent = failed = 0
            with closing(connection):
                for receipt in receipts:
                    try:
                        message = self._send(connection, receipt)
                        self.store.mark_synced(receipt["number"], True, message)
                        sent += 1
                    except Exception as error:
                        try:
                            connection.rollback()
                        except Exception:
                            pass
                        message = str(error) if isinstance(error, (DatabaseError, ValueError)) else repr(error)
                        self.store.mark_synced(receipt["number"], False, message[:500])
                        failed += 1
                    print(f"Račun {receipt['number']}: {message[:200]}")
            return SyncResult(sent, failed, f"Poslano {sent}, nije poslano {failed}.")
        finally:
            self._lock.release()

    def _send(self, connection, receipt: dict) -> str:
        number = receipt["number"]
        key = pantheon_key(number)
        cursor = connection.cursor()
        if cursor.execute("SELECT 1 FROM tHE_Move WHERE acKey = ?", key).fetchone():
            return f"Račun je već na serveru ({key})."
        doc_type = number.split("-")[1]
        setup = cursor.execute(DOC_TYPE_QUERY, doc_type).fetchone()
        if setup is None:
            raise ValueError(f"Vrsta dokumenta {doc_type} ne postoji u Pantheonu.")
        issuer, receiver, dept, account = setup
        pay_method = PAY_METHODS.get(receipt["payment_method"])
        if pay_method is None:
            raise ValueError(f"Nepoznat način plaćanja: {receipt['payment_method']}")

        items = self.store.items(number)
        codes = sorted({item["code"] for item in items})
        rows = cursor.execute(ITEMS_QUERY.format(", ".join("?" * len(codes))), *codes).fetchall()
        articles = {row[0].strip(): row for row in rows}
        missing = [code for code in codes if code not in articles]
        if missing:
            raise ValueError("Artikal ne postoji u Pantheonu: " + ", ".join(missing))

        created = datetime.fromisoformat(receipt["created_at"])
        day = created.replace(hour=0, minute=0, second=0, microsecond=0)
        lines = []
        for no, item in enumerate(items, start=1):
            _, unit, vat_code, rate = articles[item["code"]]
            if rate is None:
                raise ValueError(f"Artikal {item['code']} nema poresku stopu ({vat_code}).")
            rate = float(rate)
            gross = round(item["amount"], 2)
            net = round(gross / (1 + rate / 100), 4)
            vat = round(gross - net, 4)
            price = round(item["price"], 2)
            unit_net = round(price / (1 + rate / 100), 4)
            lines.append((
                key, no, item["code"], item["name"], item["quantity"], unit, unit_net, vat_code, rate,
                price, price, price, dept, vat_code, rate,
                net, net, vat, gross, net, net, vat, gross,
                item["quantity"], unit, created,
            ))
        total = round(receipt["total"], 2)
        total_net = round(sum(line[15] for line in lines), 4)
        total_vat = round(total - total_net, 4)
        fiscal = f"BF:{receipt['fiscal_number']}" if receipt.get("fiscal_number") else None

        cursor.execute(
            INSERT_MOVE,
            key, doc_type, day, day, day, day, receiver, issuer, dept, pay_method,
            total_net, total_vat, total, total, account, fiscal, created,
        )
        cursor.executemany(INSERT_MOVE_ITEM, lines)
        cursor.execute(INSERT_MOVE_CASH, key, pay_method, total, total, created)
        connection.commit()
        return f"Poslano na server ({key})."

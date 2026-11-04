from datetime import datetime

import pytest
from pytest import approx

from cart import Cart
from catalog import Product
from database import DatabaseError
from receipt_sync import ReceiptSync, pantheon_key
from receipts import ReceiptStore

MILK = Product("079643", "3850102", "MLIJEKO 0.9% 1L MEGGLE", 2.35)
JUICE = Product("012345", "3850103", "SOK 1L", 1.80)


class FakeServer:
    """Glumi Pantheon: pamti upisane redove, a commit tek onda ih 'potvrđuje'."""

    def __init__(self, articles=None, existing=()):
        self.articles = articles if articles is not None else {
            "079643": ("079643", "KOM", "P1", 17.0),
            "012345": ("012345", "KOM", "P1", 17.0),
        }
        self.existing = set(existing)
        self.pending: list[tuple[str, tuple]] = []
        self.committed: list[tuple[str, tuple]] = []
        self.online = True

    def connect(self):
        if not self.online:
            raise DatabaseError("Nije moguće spojiti se na bazu.")
        return FakeConnection(self)

    def rows(self, table: str) -> list[tuple]:
        return [params for name, params in self.committed if name == table]


class FakeConnection:
    def __init__(self, server: FakeServer):
        self.server = server
        self._result = []

    def cursor(self):
        return self

    def execute(self, sql, *params):
        sql = " ".join(sql.split())
        if sql.startswith("SELECT 1 FROM tHE_Move"):
            self._result = [(1,)] if params[0] in self.server.existing else []
        elif "FROM tPA_SetDocType" in sql:
            self._result = [("MARKET VELEŠIĆI", "POS kupac", "MARKET VELEŠIĆI", "2058")] if params[0] == "3257" else []
        elif "FROM tHE_SetItem" in sql:
            self._result = [self.server.articles[code] for code in params if code in self.server.articles]
        elif sql.startswith("INSERT INTO"):
            self.server.pending.append((sql.split()[2], params))
        return self

    def executemany(self, sql, rows):
        for row in rows:
            self.execute(sql, *row)

    def fetchone(self):
        return self._result[0] if self._result else None

    def fetchall(self):
        return self._result

    def commit(self):
        self.server.committed += self.server.pending
        for table, params in self.server.pending:
            if table == "tHE_Move":
                self.server.existing.add(params[0])
        self.server.pending = []

    def rollback(self):
        self.server.pending = []

    def close(self):
        self.server.pending = []


@pytest.fixture
def store(tmp_path):
    return ReceiptStore(tmp_path / "kasa.db", doc_type="3257")


def paid(store, *products, fiscal_number="23445", method="card"):
    cart = Cart()
    for product in products:
        cart.add(product)
    number = store.save(cart, method)
    if fiscal_number is not None:
        store.mark_fiscal(number, True, "<RacunOdgovor/>", fiscal_number)
    return number


def test_pantheon_key_has_seven_digit_counter():
    assert pantheon_key("26-3257-000001") == "2632570000001"
    assert pantheon_key("27-3000-012345") == "2730000012345"


def test_fiscalized_receipt_is_sent_with_items_and_payment(store):
    server = FakeServer()
    number = paid(store, MILK, MILK, JUICE)
    result = ReceiptSync(store, server.connect).send_pending()

    assert (result.sent, result.failed) == (1, 0)
    key = pantheon_key(number)
    move = server.rows("tHE_Move")[0]
    assert move[0] == key and move[1] == "3257"
    assert move[6:10] == ("POS kupac", "MARKET VELEŠIĆI", "MARKET VELEŠIĆI", "K")
    total_net, total_vat, total = move[10:13]
    assert total == approx(6.50)
    assert total_net + total_vat == approx(6.50)
    assert move[14] == "2058"
    assert move[15] == "BF:23445"

    items = server.rows("tHE_MoveItem")
    assert [(item[1], item[2], item[4]) for item in items] == [(1, "079643", 2), (2, "012345", 1)]
    milk = items[0]
    assert milk[5] == "KOM" and milk[7] == "P1" and milk[8] == 17.0
    assert milk[6] == approx(2.0085)  # neto cijena
    assert milk[9] == approx(2.35)  # cijena sa PDV-om
    assert milk[18] == approx(4.70)  # za platiti

    cash = server.rows("tHE_MoveCash")
    assert cash == [(key, "K", approx(6.50), approx(6.50), cash[0][4])]

    row = store.unsynced()
    assert row == []
    assert store.receipts_on(datetime.now().date())[0]["sync_message"].startswith("Poslano")


def test_qr_payment_uses_q(store):
    server = FakeServer()
    paid(store, MILK, method="qr")
    ReceiptSync(store, server.connect).send_pending()
    assert server.rows("tHE_Move")[0][9] == "Q"
    assert server.rows("tHE_MoveCash")[0][1] == "Q"


def test_receipt_waits_for_fiscal_number(store):
    server = FakeServer()
    paid(store, MILK, fiscal_number=None)
    result = ReceiptSync(store, server.connect).send_pending()
    assert result.sent == 0
    assert server.committed == []


def test_without_fiscal_printer_receipt_is_sent_without_bf(store):
    server = FakeServer()
    paid(store, MILK, fiscal_number=None)
    ReceiptSync(store, server.connect).send_pending(fiscal_required=False)
    assert server.rows("tHE_Move")[0][15] is None


def test_offline_keeps_receipt_and_sends_it_later(store):
    server = FakeServer()
    server.online = False
    number = paid(store, MILK)
    sync = ReceiptSync(store, server.connect)

    result = sync.send_pending()
    assert (result.sent, result.failed) == (0, 1)
    row = store.unsynced()[0]
    assert row["number"] == number and row["synced"] == 0
    assert "Server nije dostupan" in row["sync_message"]

    server.online = True
    assert sync.send_pending().sent == 1
    assert store.unsynced() == []
    assert len(server.rows("tHE_Move")) == 1


def test_receipt_already_on_server_is_not_sent_twice(store):
    number = paid(store, MILK)
    server = FakeServer(existing={pantheon_key(number)})
    result = ReceiptSync(store, server.connect).send_pending()
    assert result.sent == 1
    assert server.committed == []
    assert store.unsynced() == []


def test_unknown_article_rolls_back_and_stays_local(store):
    server = FakeServer(articles={"079643": ("079643", "KOM", "P1", 17.0)})
    paid(store, MILK, JUICE)
    good = paid(store, MILK)
    result = ReceiptSync(store, server.connect).send_pending()

    assert (result.sent, result.failed) == (1, 1)
    assert [row[0] for row in server.rows("tHE_Move")] == [pantheon_key(good)]
    left = store.unsynced()
    assert len(left) == 1 and "012345" in left[0]["sync_message"]

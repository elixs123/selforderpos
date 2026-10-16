from decimal import Decimal

import catalog
from catalog import Product


class FakeCursor:
    def __init__(self, row):
        self.row = row

    def execute(self, query, barcode):
        self.barcode = barcode
        return self

    def fetchone(self):
        return self.row


class FakeConnection:
    def __init__(self, row):
        self.row = row
        self.closed = False

    def execute(self, query, parameters):
        return FakeCursor(self.row).execute(query, parameters)

    def close(self):
        self.closed = True


def test_find_by_barcode_returns_product(monkeypatch):
    connection = FakeConnection(("A1", "1001", "Mlijeko 1 l", Decimal("1.79")))
    monkeypatch.setattr(catalog, "connect", lambda: connection)
    product = catalog.find_by_barcode("1001")
    assert product == Product("A1", "1001", "Mlijeko 1 l", 1.79)
    assert type(product.price) is float
    assert connection.closed


def test_find_by_barcode_unknown_returns_none(monkeypatch):
    connection = FakeConnection(None)
    monkeypatch.setattr(catalog, "connect", lambda: connection)
    assert catalog.find_by_barcode("0000") is None
    assert connection.closed

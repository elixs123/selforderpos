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


class FakeStore:
    def __init__(self, products):
        self.products = products

    def find(self, barcode):
        return self.products.get(barcode)

    def article_count(self):
        return len(self.products)


def test_weighed_parts_reads_barcode_and_grams():
    assert catalog.weighed_parts("2890619002483") == ("2890619", 248)


def test_weighed_parts_rejects_other_barcodes():
    assert catalog.weighed_parts("2890619002484") is None  # pogrešna kontrolna cifra
    assert catalog.weighed_parts("3870000000001") is None  # ne počinje sa 2
    assert catalog.weighed_parts("2890619") is None
    assert catalog.weighed_parts("2890619000008") is None  # masa 0


def test_find_by_barcode_weighed_label(monkeypatch):
    store = FakeStore({"2890619": Product("097992", "2890619", "DINJA", 5.95)})
    monkeypatch.setattr(catalog, "local_store", store)
    product = catalog.find_by_barcode("2890619002483")
    assert product == Product("097992", "2890619002483", "DINJA", 5.95, 248)


def test_find_by_barcode_full_barcode_wins_over_weighed(monkeypatch):
    whole = Product("A1", "2890619002483", "Artikal sa punim barkodom", 1.0)
    store = FakeStore({"2890619002483": whole, "2890619": Product("097992", "2890619", "DINJA", 5.95)})
    monkeypatch.setattr(catalog, "local_store", store)
    assert catalog.find_by_barcode("2890619002483") == whole


def test_weighed_parts_only_confirmed_prefix():
    for prefix in ("2190619", "2445770", "2701741"):
        digits = [int(digit) for digit in prefix + "00248"]
        check = (10 - (sum(digits[0::2]) + 3 * sum(digits[1::2])) % 10) % 10
        assert catalog.weighed_parts(f"{prefix}00248{check}") is None

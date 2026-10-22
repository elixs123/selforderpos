from pytest import approx

from cart import Cart
from catalog import Product
from receipts import ReceiptStore

MILK = Product("A1", "1001", "Mlijeko 1 l", 1.79)
BISCUITS = Product("A2", "1002", "Keks petit beurre 200 g", 2.49)


def filled_cart() -> Cart:
    cart = Cart()
    cart.add(MILK, 2)
    cart.add(BISCUITS)
    return cart


def test_save_creates_receipt_with_number(tmp_path):
    store = ReceiptStore(tmp_path / "kasa.db")
    number = store.save(filled_cart(), "card")
    receipts = store.unsynced()
    assert len(receipts) == 1
    assert receipts[0]["number"] == number
    assert receipts[0]["payment_method"] == "card"
    assert receipts[0]["item_count"] == 3
    assert receipts[0]["total"] == approx(6.07)


def test_save_stores_items(tmp_path):
    store = ReceiptStore(tmp_path / "kasa.db")
    number = store.save(filled_cart(), "qr")
    items = store.items(number)
    assert [item["name"] for item in items] == ["Mlijeko 1 l", "Keks petit beurre 200 g"]
    assert items[0]["quantity"] == 2
    assert items[0]["amount"] == approx(3.58)


def test_numbers_increase(tmp_path):
    store = ReceiptStore(tmp_path / "kasa.db")
    first = store.save(filled_cart(), "card")
    second = store.save(filled_cart(), "card")
    assert first.endswith("000001")
    assert second.endswith("000002")


def test_data_survives_new_store(tmp_path):
    path = tmp_path / "kasa.db"
    ReceiptStore(path).save(filled_cart(), "card")
    assert len(ReceiptStore(path).unsynced()) == 1


def test_card_payment_details_and_fiscal_flag(tmp_path):
    import sqlite3

    store = ReceiptStore(tmp_path / "kasa.db")
    payment = {"invoice_id": "K1-20261015-120000", "approval_code": "A1B2", "rrn": "999", "bank_id": "51", "card_number": "****1234"}
    number = store.save(filled_cart(), "card", payment)
    store.mark_fiscal(number, False, "printer nije dostupan")
    row = store.unsynced()[0]
    assert row["payment_reference"] == "K1-20261015-120000"
    assert row["approval_code"] == "A1B2"
    assert row["bank_id"] == "51"
    assert row["fiscal_printed"] == 0
    assert row["fiscal_message"] == "printer nije dostupan"


def test_fiscal_number_is_stored(tmp_path):
    store = ReceiptStore(tmp_path / "kasa.db")
    number = store.save(filled_cart(), "card")
    store.mark_fiscal(number, True, "<RacunOdgovor/>", "84366")
    assert store.unsynced()[0]["fiscal_number"] == "84366"


def test_receipt_opens_gate_only_once(tmp_path):
    from datetime import datetime, timedelta

    store = ReceiptStore(tmp_path / "kasa.db")
    number = store.save(filled_cart(), "card")
    store.mark_fiscal(number, True, "", "84366")
    now = datetime(2026, 10, 21, 10, 10)
    assert store.claim_for_gate("084366", now) == (True, "račun pronađen")
    assert store.claim_for_gate("084366", now + timedelta(seconds=60)) == (True, "ponovljeno skeniranje")
    allowed, reason = store.claim_for_gate("084366", now + timedelta(minutes=5))
    assert not allowed
    assert "već iskorišten" in reason


def test_unknown_receipt_does_not_open_gate(tmp_path):
    store = ReceiptStore(tmp_path / "kasa.db")
    number = store.save(filled_cart(), "card")
    store.mark_fiscal(number, True, "", "84366")
    assert store.claim_for_gate("084367") == (False, "račun nije pronađen")
    assert store.claim_for_gate("") == (False, "nema broja računa")


def test_old_database_gets_new_columns(tmp_path):
    import sqlite3

    path = tmp_path / "kasa.db"
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE receipts (id INTEGER PRIMARY KEY AUTOINCREMENT, number TEXT UNIQUE, created_at TEXT NOT NULL, payment_method TEXT NOT NULL, item_count INTEGER NOT NULL, total REAL NOT NULL, synced INTEGER NOT NULL DEFAULT 0)")
    connection.commit()
    connection.close()
    store = ReceiptStore(path)
    store.save(filled_cart(), "qr")
    assert store.unsynced()[0]["fiscal_printed"] == 0

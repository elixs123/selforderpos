import pytest

import catalog
from articles import ArticleStore
from catalog import Product
from database import DatabaseError

SERVER_ROWS = [
    ("A1", "1001", "Mlijeko 1 l", 1.79),
    ("A1", "1002", "Mlijeko 1 l", 1.79),
    ("A2", None, "Keks petit beurre 200 g", 2.49),
    ("A3", "1003", "Bez cijene", None),
]


@pytest.fixture
def store(tmp_path):
    return ArticleStore(tmp_path / "kasa.db")


def test_sync_stores_articles_and_barcodes(store):
    result = store.sync(lambda: SERVER_ROWS)
    assert result.ok
    assert (result.article_count, result.barcode_count) == (2, 2)
    assert store.find("1002") == Product("A1", "1002", "Mlijeko 1 l", 1.79)
    assert store.find("A2") == Product("A2", "A2", "Keks petit beurre 200 g", 2.49)
    assert store.find("1003") is None
    assert store.last_sync()["article_count"] == 2


def test_sync_replaces_old_articles(store):
    store.sync(lambda: SERVER_ROWS)
    store.sync(lambda: [("A9", "9009", "Sok 1 l", 2.10)])
    assert store.find("1001") is None
    assert store.find("9009").price == 2.10


def test_failed_sync_keeps_local_articles(store):
    store.sync(lambda: SERVER_ROWS)

    def offline():
        raise DatabaseError("server nije dostupan")

    result = store.sync(offline)
    assert not result.ok
    assert store.find("1001") is not None
    assert "server nije dostupan" in store.last_sync()["message"]
    assert not store.sync(lambda: []).ok
    assert store.find("1001") is not None


def test_catalog_uses_local_store_then_server(store, monkeypatch):
    store.sync(lambda: SERVER_ROWS)
    monkeypatch.setattr(catalog, "local_store", store)
    asked = []

    def server(barcode):
        asked.append(barcode)
        raise DatabaseError("server nije dostupan")

    monkeypatch.setattr(catalog, "find_on_server", server)
    assert catalog.find_by_barcode("1001").code == "A1"
    assert asked == []
    assert catalog.find_by_barcode("5555") is None
    assert asked == ["5555"]


def test_catalog_reports_server_error_when_nothing_synced(store, monkeypatch):
    monkeypatch.setattr(catalog, "local_store", store)

    def server(barcode):
        raise DatabaseError("server nije dostupan")

    monkeypatch.setattr(catalog, "find_on_server", server)
    with pytest.raises(DatabaseError):
        catalog.find_by_barcode("1001")

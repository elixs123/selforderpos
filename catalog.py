from contextlib import closing
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from database import DatabaseError, connect


@dataclass(frozen=True)
class Product:
    code: str
    barcode: str
    name: str
    price: float

    @property
    def price_minor(self) -> int:
        """Cijena u feninzima, zaokružena kao na fiskalnom računu (1,785 -> 179)."""
        return int((Decimal(str(self.price)) * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))


QUERY = """
SELECT i.acIdent, b.acCode, i.acName, i.anSalePrice
FROM tHE_SetItem i
JOIN tHE_SetItemExtItemSubj b ON b.acIdent = i.acIdent
WHERE b.acCode = ? or i.acIdent = ?
"""


local_store = None


def use_local_store(store) -> None:
    global local_store
    local_store = store


def find_by_barcode(barcode: str) -> Product | None:
    """Prvo lokalna kopija artikala; server samo ako artikla nema lokalno (npr. novi od zadnje sinhronizacije)."""
    if local_store is None:
        return find_on_server(barcode)
    product = local_store.find(barcode)
    if product is not None:
        return product
    try:
        return find_on_server(barcode)
    except DatabaseError:
        if local_store.article_count() == 0:
            raise
        return None


def find_on_server(barcode: str) -> Product | None:
    with closing(connect()) as connection:
        row = connection.execute(QUERY, (barcode, barcode)).fetchone()
    if row is None:
        return None
    code, barcode, name, price = row
    if price is None:
        return None
    return Product(code, barcode, name, float(price))

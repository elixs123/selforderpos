from contextlib import closing
from dataclasses import dataclass

from database import connect


@dataclass(frozen=True)
class Product:
    code: str
    barcode: str
    name: str
    price: float


QUERY = """
SELECT i.acIdent, b.acCode, i.acName, i.anSalePrice
FROM tHE_SetItem i
JOIN tHE_SetItemExtItemSubj b ON b.acIdent = i.acIdent
WHERE b.acCode = ? or i.acIdent = ?
"""


def find_by_barcode(barcode: str) -> Product | None:
    with closing(connect()) as connection:
        row = connection.execute(QUERY, (barcode, barcode)).fetchone()
    if row is None:
        return None
    code, barcode, name, price = row
    return Product(code, barcode, name, float(price))

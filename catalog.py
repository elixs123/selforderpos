from contextlib import closing
from dataclasses import dataclass, replace
from decimal import ROUND_HALF_UP, Decimal

from database import DatabaseError, connect


# Podgrupe (acClassif2) za koje kasa prikazuje upozorenje 18+: vina crna, vina bijela, žestoka pića, pivo.
AGE_RESTRICTED_CATEGORIES = frozenset({"PEN.25.121.", "PEN.25.47.", "PEN.25.46.", "PEN.25.34."})


def clean_category(value) -> str:
    """U bazi ima kodova pisanih i kao 'Pen.25.11.'."""
    return str(value or "").strip().upper()


@dataclass(frozen=True)
class Product:
    code: str
    barcode: str
    name: str
    price: float
    weight_grams: int = 0
    category: str = ""

    @property
    def age_restricted(self) -> bool:
        return self.category in AGE_RESTRICTED_CATEGORIES

    @property
    def price_minor(self) -> int:
        """Cijena u feninzima, zaokružena kao na fiskalnom računu (1,785 -> 179)."""
        return int((Decimal(str(self.price)) * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))

    @property
    def weight(self) -> float:
        return self.weight_grams / 1000

    def amount_minor(self, quantity: float) -> int:
        """Iznos stavke u feninzima; masa se množi sa cijenom po kg i zaokružuje kao na fiskalnom računu."""
        return int((self.price_minor * Decimal(str(quantity))).quantize(Decimal(1), rounding=ROUND_HALF_UP))


QUERY = """
SELECT i.acIdent, b.acCode, i.acName, i.anSalePrice, i.acClassif2
FROM tHE_SetItem i
JOIN tHE_SetItemExtItemSubj b ON b.acIdent = i.acIdent
WHERE b.acCode = ? or i.acIdent = ?
"""


# Samo 28 je potvrđeno skenerom; 24 i 27 su obični artikli sa 7 cifara, a format 21 nije provjeren.
WEIGHED_PREFIX = "28"

local_store = None


def use_local_store(store) -> None:
    global local_store
    local_store = store


def weighed_parts(barcode: str) -> tuple[str, int] | None:
    """Deklaracija sa vage: EAN-13 sa prefiksom 28, 7 cifara barkoda artikla + masa u gramima (5 cifara) + kontrolna."""
    if len(barcode) != 13 or not barcode.isdecimal() or not barcode.startswith(WEIGHED_PREFIX):
        return None
    digits = [int(digit) for digit in barcode]
    if (sum(digits[0::2]) + 3 * sum(digits[1::2])) % 10 != 0:
        return None
    grams = int(barcode[7:12])
    return (barcode[:7], grams) if grams else None


def find_by_barcode(barcode: str) -> Product | None:
    """Prvo lokalna kopija artikala; server samo ako artikla nema lokalno (npr. novi od zadnje sinhronizacije)."""
    weighed = weighed_parts(barcode)
    if local_store is not None:
        product = _find_with(local_store.find, barcode, weighed)
        if product is not None:
            return product
    try:
        return _find_with(find_on_server, barcode, weighed)
    except DatabaseError:
        if local_store is None or local_store.article_count() == 0:
            raise
        return None


def _find_with(find, barcode: str, weighed: tuple[str, int] | None) -> Product | None:
    """Cijeli barkod ima prednost; tek ako ga nema, traži se artikal po prvih 7 cifara deklaracije."""
    product = find(barcode)
    if product is not None or weighed is None:
        return product
    product = find(weighed[0])
    return None if product is None else replace(product, barcode=barcode, weight_grams=weighed[1])


def find_on_server(barcode: str) -> Product | None:
    with closing(connect()) as connection:
        row = connection.execute(QUERY, (barcode, barcode)).fetchone()
    if row is None:
        return None
    code, barcode, name, price, category = row
    if price is None:
        return None
    return Product(code, barcode, name, float(price), category=clean_category(category))

from dataclasses import dataclass

from catalog import Product


@dataclass
class CartItem:
    product: Product
    quantity: int

    @property
    def amount_minor(self) -> int:
        return self.product.price_minor * self.quantity

    @property
    def amount(self) -> float:
        return self.amount_minor / 100


class Cart:
    def __init__(self) -> None:
        self._items: dict[str, CartItem] = {}

    def add(self, product: Product, quantity: int = 1) -> None:
        if product.code in self._items:
            self._items[product.code].quantity += quantity
        else:
            self._items[product.code] = CartItem(product, quantity)

    def change_quantity(self, code: str, delta: int) -> None:
        if code not in self._items:
            return
        item = self._items[code]
        item.quantity += delta
        if item.quantity <= 0:
            del self._items[code]

    def remove(self, code: str) -> None:
        self._items.pop(code, None)

    @property
    def total_minor(self) -> int:
        """Ukupno u feninzima; iz ovoga se računaju i iznos za terminal i iznos na fiskalnom računu."""
        return sum(item.amount_minor for item in self._items.values())

    @property
    def total(self) -> float:
        return self.total_minor / 100

    @property
    def item_count(self) -> int:
        return sum(item.quantity for item in self._items.values())

    def clear(self) -> None:
        self._items.clear()

    def to_dict(self) -> dict:
        return {
            "items": [
                {
                    "code": item.product.code,
                    "barcode": item.product.barcode,
                    "name": item.product.name,
                    "price": item.product.price_minor / 100,
                    "quantity": item.quantity,
                    "amount": item.amount,
                }
                for item in self._items.values()
            ],
            "item_count": self.item_count,
            "total": self.total,
        }

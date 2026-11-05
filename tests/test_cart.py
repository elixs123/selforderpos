from pytest import approx

from cart import Cart
from catalog import Product

MILK = Product("A1", "1001", "Mlijeko 1 l", 1.79)
BISCUITS = Product("A2", "1002", "Keks petit beurre 200 g", 2.49)
SILICONE = Product("A3", "1003", "Silikon sanitarni bijeli 280 ml", 6.90)
LED_BULB = Product("A4", "1004", "LED žarulja E27 9 W", 3.20)
GLOVES = Product("A5", "1005", "Radne rukavice PU", 2.80)


def test_empty_cart_total_is_zero():
    assert Cart().total == 0


def test_adding_same_product_twice_increases_quantity():
    cart = Cart()
    cart.add(MILK)
    cart.add(MILK)
    assert cart.item_count == 2
    assert cart.total == approx(3.58)


def test_total_for_design_example():
    cart = Cart()
    cart.add(MILK, 2)
    cart.add(BISCUITS)
    cart.add(SILICONE)
    cart.add(LED_BULB, 3)
    cart.add(GLOVES)
    assert cart.item_count == 8
    assert cart.total == approx(25.37)


def test_decreasing_quantity():
    cart = Cart()
    cart.add(LED_BULB, 3)
    cart.change_quantity("A4", -1)
    assert cart.item_count == 2


def test_decreasing_to_zero_removes_item():
    cart = Cart()
    cart.add(BISCUITS)
    cart.change_quantity("A2", -1)
    assert cart.item_count == 0
    assert cart.to_dict()["items"] == []


def test_changing_unknown_code_does_not_fail():
    cart = Cart()
    cart.change_quantity("NONE", 1)
    assert cart.total == 0


def test_remove_deletes_whole_item():
    cart = Cart()
    cart.add(LED_BULB, 3)
    cart.add(MILK)
    cart.remove("A4")
    assert cart.item_count == 1


def test_remove_unknown_code_does_not_fail():
    cart = Cart()
    cart.remove("NONE")
    assert cart.item_count == 0


def test_total_is_exact_in_fenings():
    cart = Cart()
    for code, price in (("P1", 0.1), ("P2", 0.2), ("P3", 12.0)):
        cart.add(Product(code, code, code, price))
    assert cart.total_minor == 1230
    assert cart.total == 12.3


def test_price_with_more_decimals_is_rounded_like_fiscal_receipt():
    from fiscal import FiscalOptions, build_request

    cart = Cart()
    cart.add(Product("P1", "1", "Sir", 1.785), 3)
    assert cart.total_minor == 537
    data = cart.to_dict()
    assert data["items"][0]["price"] == 1.79
    xml = build_request(1, data, "card", FiscalOptions()).decode()
    assert "<Cijena>1.79</Cijena>" in xml and "<Iznos>5.37</Iznos>" in xml


MELON = Product("097992", "2890619002483", "DINJA", 5.95, 248)


def test_weighed_item_is_mass_times_price():
    cart = Cart()
    cart.add(MELON)
    item = cart.to_dict()["items"][0]
    assert item["quantity"] == 0.248
    assert item["price"] == approx(5.95)
    assert item["amount"] == approx(1.48)  # 0,248 x 5,95 = 1,4756
    assert cart.item_count == 1


def test_two_labels_of_same_article_add_up_mass():
    cart = Cart()
    cart.add(MELON)
    cart.add(Product("097992", "2890619003006", "DINJA", 5.95, 300))
    assert cart.to_dict()["items"][0]["quantity"] == 0.548
    assert cart.total == approx(3.26)  # 0,548 x 5,95 = 3,2606
    assert cart.item_count == 1


def test_changing_weighed_item_removes_or_ignores():
    cart = Cart()
    cart.add(MELON)
    cart.change_quantity("097992", 1)
    assert cart.to_dict()["items"][0]["quantity"] == 0.248
    cart.change_quantity("097992", -1)
    assert cart.item_count == 0

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

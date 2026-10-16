from formatting import format_amount, item_count_text


def test_format_amount():
    assert format_amount(0) == "0,00"
    assert format_amount(0.05) == "0,05"
    assert format_amount(1.79) == "1,79"
    assert format_amount(0.9119) == "0,91"
    assert format_amount(25.37) == "25,37"


def test_item_count_text():
    assert item_count_text(0) == "0 artikala"
    assert item_count_text(1) == "1 artikal"
    assert item_count_text(2) == "2 artikla"
    assert item_count_text(5) == "5 artikala"
    assert item_count_text(11) == "11 artikala"
    assert item_count_text(12) == "12 artikala"
    assert item_count_text(21) == "21 artikal"
    assert item_count_text(24) == "24 artikla"

def format_amount(price: float) -> str:
    return f"{price:.2f}".replace(".", ",")


def item_count_text(count: int) -> str:
    last_digit = count % 10
    last_two_digits = count % 100
    if last_digit == 1 and last_two_digits != 11:
        word = "artikal"
    elif 2 <= last_digit <= 4 and not 12 <= last_two_digits <= 14:
        word = "artikla"
    else:
        word = "artikala"
    return f"{count} {word}"

def format_amount(price: float) -> str:
    return f"{price:.2f}".replace(".", ",")


def count_text(count: int, one: str, few: str, many: str) -> str:
    last_digit = count % 10
    last_two_digits = count % 100
    if last_digit == 1 and last_two_digits != 11:
        word = one
    elif 2 <= last_digit <= 4 and not 12 <= last_two_digits <= 14:
        word = few
    else:
        word = many
    return f"{count} {word}"


def item_count_text(count: int) -> str:
    return count_text(count, "artikal", "artikla", "artikala")


def receipt_count_text(count: int) -> str:
    return count_text(count, "račun", "računa", "računa")

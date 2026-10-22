from datetime import datetime

from qr_slip import build_payload


def test_payload_matches_original_receipt_qr():
    payload = build_payload("AM040250", "84366", datetime(2026, 10, 21, 10, 10), 9.0)
    assert payload == "IBFM:AM040250\nBF:084366\nDatum:21.10.2026 10:10\nTotal:9,00"


def test_payload_keeps_non_numeric_number():
    assert "BF:A-12\n" in build_payload("AM040250", " A-12 ", datetime(2026, 1, 2, 3, 4), 1.5)

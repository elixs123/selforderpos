import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "cameras"))

from counter import ZoneALedger, ZoneBLedger


def seen(ledger, count, now=None):
    if now is None:
        ledger.observe(count)
        ledger.observe(count)
    else:
        ledger.observe(count, now)
        ledger.observe(count, now)


def test_zone_a_normal_sale():
    ledger = ZoneALedger()
    seen(ledger, 3)
    seen(ledger, 2)
    assert ledger.missing == 1 and not ledger.extra_after_accept
    ledger.accepted()
    assert ledger.missing == 0
    seen(ledger, 2)
    assert ledger.missing == 0 and not ledger.extra_after_accept


def test_zone_a_two_taken_one_scanned():
    ledger = ZoneALedger()
    seen(ledger, 3, now=0.0)
    seen(ledger, 1, now=1.0)
    seen(ledger, 1, now=5.0)
    ledger.accepted()
    seen(ledger, 1, now=6.0)
    assert ledger.missing == 1 and ledger.extra_after_accept


def test_zone_a_item_returned_clears():
    ledger = ZoneALedger()
    seen(ledger, 3, now=0.0)
    seen(ledger, 1, now=1.0)
    seen(ledger, 1, now=5.0)
    ledger.accepted()
    seen(ledger, 1)
    seen(ledger, 2)
    assert ledger.missing == 0 and not ledger.extra_after_accept


def test_zone_a_count_flicker_is_not_taking_several_items():
    ledger = ZoneALedger()
    seen(ledger, 3, now=0.0)
    for second in range(1, 20, 2):
        seen(ledger, 0, now=float(second))
        assert ledger.missing == 0
        seen(ledger, 3, now=second + 1.0)
    seen(ledger, 2, now=30.0)
    assert ledger.missing == 1
    seen(ledger, 0, now=31.0)
    assert ledger.missing == 1
    seen(ledger, 0, now=34.5)
    assert ledger.missing == 3


def test_zone_a_single_flicker_is_ignored():
    ledger = ZoneALedger()
    seen(ledger, 3)
    ledger.observe(2)
    ledger.observe(3)
    assert ledger.missing == 0


def test_zone_a_basket_added_resyncs():
    ledger = ZoneALedger()
    seen(ledger, 0)
    seen(ledger, 4)
    assert ledger.expected == 4 and ledger.missing == 0


def test_zone_b_item_put_without_scan_and_packing():
    ledger = ZoneBLedger()
    seen(ledger, 0)
    ledger.accepted(1)
    seen(ledger, 1)
    assert ledger.extra == 0
    seen(ledger, 2)
    assert ledger.extra == 1
    seen(ledger, 1)
    assert ledger.extra == 0
    seen(ledger, 0, now=100.0)
    assert ledger.known == 1
    seen(ledger, 0, now=110.0)
    assert ledger.known == 0


def test_accepted_item_counts_even_when_yolox_missed_it():
    ledger = ZoneBLedger()
    seen(ledger, 3)
    ledger.accepted(3)
    assert ledger.known == 4
    seen(ledger, 4)
    assert ledger.extra == 0


def test_zone_b_count_flicker_is_not_an_unscanned_item():
    ledger = ZoneBLedger()
    seen(ledger, 0)
    ledger.accepted(2)
    for second in range(0, 30, 3):
        seen(ledger, 1, now=float(second))
        assert ledger.known == 2 and ledger.extra == 0
        seen(ledger, 2, now=second + 1.5)
        assert ledger.extra == 0
    seen(ledger, 3, now=40.0)
    assert ledger.extra == 1

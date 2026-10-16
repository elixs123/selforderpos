import pytest

from staff_auth import StaffPinMissing, check_pin


def test_correct_pin(monkeypatch):
    monkeypatch.setenv("STAFF_PIN", "4321")
    assert check_pin("4321")


def test_wrong_pin(monkeypatch):
    monkeypatch.setenv("STAFF_PIN", "4321")
    assert not check_pin("1234")


def test_missing_pin(monkeypatch):
    monkeypatch.delenv("STAFF_PIN", raising=False)
    with pytest.raises(StaffPinMissing):
        check_pin("4321")


def test_admin_pin(monkeypatch):
    from staff_auth import check_admin_pin

    monkeypatch.setenv("ADMIN_PIN", "0000")
    assert check_admin_pin("0000")
    assert not check_admin_pin("1111")

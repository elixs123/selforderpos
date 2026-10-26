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


def test_pin_locks_after_too_many_wrong_attempts(monkeypatch):
    import staff_auth

    staff_auth.reset_attempts()
    clock = [1000.0]
    monkeypatch.setattr(staff_auth.time, "monotonic", lambda: clock[0])
    monkeypatch.setenv("STAFF_PIN", "4321")
    for _ in range(staff_auth.MAX_ATTEMPTS):
        assert not check_pin("0000")
    with pytest.raises(staff_auth.PinLocked):
        check_pin("4321")
    clock[0] += staff_auth.LOCK_SECONDS
    assert check_pin("4321")
    for _ in range(staff_auth.MAX_ATTEMPTS):
        check_pin("0000")
    clock[0] += staff_auth.LOCK_SECONDS
    assert check_pin("4321")
    staff_auth.reset_attempts()


def test_second_lock_is_longer(monkeypatch):
    import staff_auth

    staff_auth.reset_attempts()
    clock = [1000.0]
    monkeypatch.setattr(staff_auth.time, "monotonic", lambda: clock[0])
    monkeypatch.setenv("ADMIN_PIN", "9876")
    for _ in range(staff_auth.MAX_ATTEMPTS):
        check_pin("0000", "ADMIN_PIN")
    clock[0] += staff_auth.LOCK_SECONDS
    for _ in range(staff_auth.MAX_ATTEMPTS):
        check_pin("0000", "ADMIN_PIN")
    clock[0] += staff_auth.LOCK_SECONDS
    with pytest.raises(staff_auth.PinLocked):
        check_pin("9876", "ADMIN_PIN")
    clock[0] += staff_auth.LOCK_SECONDS
    assert check_pin("9876", "ADMIN_PIN")
    staff_auth.reset_attempts()

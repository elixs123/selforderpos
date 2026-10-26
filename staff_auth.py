import hmac
import os
import threading
import time

from dotenv import load_dotenv

from locations import env_file

load_dotenv(env_file())


MAX_ATTEMPTS = 5
LOCK_SECONDS = 60
MAX_LOCK_SECONDS = 15 * 60


class PinError(Exception):
    pass


class StaffPinMissing(PinError):
    pass


class PinLocked(PinError):
    pass


_failures: dict[str, int] = {}
_locked_until: dict[str, float] = {}
_lock = threading.Lock()


def check_pin(entered: str, variable: str = "STAFF_PIN") -> bool:
    """Nakon MAX_ATTEMPTS pogrešnih pokušaja PIN se zaključa na LOCK_SECONDS, svako sljedeće zaključavanje duplo duže."""
    expected = os.environ.get(variable, "")
    if not expected:
        raise StaffPinMissing(f"PIN nije podešen ({variable} u .env).")
    with _lock:
        remaining = _locked_until.get(variable, 0.0) - time.monotonic()
        if remaining > 0:
            raise PinLocked(f"Previše pogrešnih pokušaja. Pokušajte ponovo za {int(remaining) + 1} s.")
        if hmac.compare_digest(entered.encode(), expected.encode()):
            _failures[variable] = 0
            return True
        _failures[variable] = _failures.get(variable, 0) + 1
        failures = _failures[variable]
        if failures >= MAX_ATTEMPTS and failures % MAX_ATTEMPTS == 0:
            seconds = min(MAX_LOCK_SECONDS, LOCK_SECONDS * 2 ** (failures // MAX_ATTEMPTS - 1))
            _locked_until[variable] = time.monotonic() + seconds
            print(f"PIN {variable}: {failures} pogrešnih pokušaja, zaključano {seconds} s")
        return False


def reset_attempts() -> None:
    with _lock:
        _failures.clear()
        _locked_until.clear()


def check_admin_pin(entered: str) -> bool:
    return check_pin(entered, "ADMIN_PIN")

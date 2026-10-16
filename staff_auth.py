import hmac
import os

from dotenv import load_dotenv

from locations import env_file

load_dotenv(env_file())


class StaffPinMissing(Exception):
    pass


def check_pin(entered: str, variable: str = "STAFF_PIN") -> bool:
    expected = os.environ.get(variable, "")
    if not expected:
        raise StaffPinMissing(f"PIN nije podešen ({variable} u .env).")
    return hmac.compare_digest(entered, expected)


def check_admin_pin(entered: str) -> bool:
    return check_pin(entered, "ADMIN_PIN")

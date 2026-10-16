import sys
from pathlib import Path

FROZEN = getattr(sys, "frozen", False)


def app_folder() -> Path:
    if FROZEN:
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def env_file() -> Path:
    return app_folder() / ".env"


def zones_file() -> Path:
    if FROZEN:
        return app_folder() / "zones.json"
    return app_folder() / "cameras" / "zones.json"

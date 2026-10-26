import os

from dotenv import load_dotenv

from locations import env_file

load_dotenv(env_file())

REQUIRED_SETTINGS = ("DB_SERVER", "DB_NAME", "DB_USER", "DB_PASSWORD")


class DatabaseError(Exception):
    pass


_overrides: dict[str, str] = {}


def configure(server: str = "", port: str = "", name: str = "", user: str = "", password: str = "") -> None:
    """Postavke baze iz ekrana Postavke; prazno polje = vrijednost iz .env."""
    values = {"DB_SERVER": server, "DB_PORT": port, "DB_NAME": name, "DB_USER": user, "DB_PASSWORD": password}
    _overrides.clear()
    _overrides.update({key: value.strip() for key, value in values.items() if value and value.strip()})


def _value(name: str) -> str:
    return _overrides.get(name) or os.environ.get(name, "")


def build_connection_string() -> str:
    missing = [name for name in REQUIRED_SETTINGS if not _value(name)]
    if missing:
        raise DatabaseError("Nedostaju postavke baze (Postavke ili .env): " + ", ".join(missing))
    driver = os.environ.get("DB_DRIVER", "ODBC Driver 18 for SQL Server")
    trust_certificate = os.environ.get("DB_TRUST_CERT", "yes")
    server = _value("DB_SERVER")
    port = _value("DB_PORT")
    if port and "," not in server:
        server = f"{server},{port}"
    return (
        f"DRIVER={{{driver}}};"
        f"SERVER={server};"
        f"DATABASE={_value('DB_NAME')};"
        f"UID={_value('DB_USER')};"
        f"PWD={_value('DB_PASSWORD')};"
        f"TrustServerCertificate={trust_certificate}"
    )


def connect():
    import pyodbc

    connection_string = build_connection_string()
    try:
        return pyodbc.connect(connection_string, timeout=5)
    except pyodbc.Error as error:
        detail = str(error.args[-1] if error.args else error).replace(_value("DB_PASSWORD") or "\0", "***")
        raise DatabaseError(
            "Nije moguće spojiti se na bazu. Provjeri adresu servera, korisnika, lozinku i ODBC drajver."
            f" ({detail[:300]})"
        ) from error

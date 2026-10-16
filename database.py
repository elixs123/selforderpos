import os

from dotenv import load_dotenv

from locations import env_file

load_dotenv(env_file())

REQUIRED_SETTINGS = ("DB_SERVER", "DB_NAME", "DB_USER", "DB_PASSWORD")


class DatabaseError(Exception):
    pass


def build_connection_string() -> str:
    missing = [name for name in REQUIRED_SETTINGS if not os.environ.get(name)]
    if missing:
        raise DatabaseError("Nedostaju postavke baze u .env fajlu: " + ", ".join(missing))
    driver = os.environ.get("DB_DRIVER", "ODBC Driver 18 for SQL Server")
    trust_certificate = os.environ.get("DB_TRUST_CERT", "yes")
    return (
        f"DRIVER={{{driver}}};"
        f"SERVER={os.environ['DB_SERVER']};"
        f"DATABASE={os.environ['DB_NAME']};"
        f"UID={os.environ['DB_USER']};"
        f"PWD={os.environ['DB_PASSWORD']};"
        f"TrustServerCertificate={trust_certificate}"
    )


def connect():
    import pyodbc

    connection_string = build_connection_string()
    try:
        return pyodbc.connect(connection_string, timeout=5)
    except pyodbc.Error as error:
        raise DatabaseError(
            "Nije moguće spojiti se na bazu. Provjeri adresu servera, korisnika, lozinku i ODBC drajver."
        ) from error

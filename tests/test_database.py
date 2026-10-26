import pytest

from database import REQUIRED_SETTINGS, DatabaseError, build_connection_string


@pytest.fixture
def clean_environment(monkeypatch):
    for name in (*REQUIRED_SETTINGS, "DB_PORT", "DB_DRIVER", "DB_TRUST_CERT"):
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def test_missing_settings_are_reported(clean_environment):
    clean_environment.setenv("DB_SERVER", "host")
    with pytest.raises(DatabaseError) as error:
        build_connection_string()
    assert "DB_NAME" in str(error.value)
    assert "DB_USER" in str(error.value)
    assert "DB_PASSWORD" in str(error.value)
    assert "DB_SERVER" not in str(error.value)


def test_connection_string_contains_settings(clean_environment):
    clean_environment.setenv("DB_SERVER", "host,1433")
    clean_environment.setenv("DB_NAME", "shop")
    clean_environment.setenv("DB_USER", "reader")
    clean_environment.setenv("DB_PASSWORD", "secret")
    connection_string = build_connection_string()
    assert "SERVER=host,1433" in connection_string
    assert "DATABASE=shop" in connection_string
    assert "DRIVER={ODBC Driver 18 for SQL Server}" in connection_string


def test_error_message_does_not_leak_password(clean_environment):
    clean_environment.setenv("DB_SERVER", "host")
    with pytest.raises(DatabaseError) as error:
        build_connection_string()
    assert "secret" not in str(error.value)


def test_settings_override_env_and_add_port(clean_environment):
    import database

    clean_environment.setenv("DB_SERVER", "envhost")
    clean_environment.setenv("DB_NAME", "envdb")
    clean_environment.setenv("DB_USER", "reader")
    clean_environment.setenv("DB_PASSWORD", "secret")
    try:
        database.configure("10.20.10.5\\PENNYPLUS", "49725", "PENNY2", "", "")
        connection_string = build_connection_string()
        assert "SERVER=10.20.10.5\\PENNYPLUS,49725" in connection_string
        assert "DATABASE=PENNY2" in connection_string
        assert "UID=reader" in connection_string
    finally:
        database.configure()
    assert "SERVER=envhost;" in build_connection_string()

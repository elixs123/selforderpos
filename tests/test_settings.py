from settings import Settings, load_settings, save_settings


def test_missing_file_gives_defaults(tmp_path):
    settings = load_settings(tmp_path / "settings.json")
    assert settings.terminal_url == "http://127.0.0.1:3421"
    assert settings.demo_payments is False


def test_round_trip(tmp_path):
    path = tmp_path / "settings.json"
    settings = Settings(register_id="K7", terminal_slip_copies=2, fiscal_enabled=True)
    save_settings(settings, path)
    loaded = load_settings(path)
    assert loaded.register_id == "K7"
    assert loaded.terminal_slip_copies == 2
    assert loaded.fiscal_enabled is True


def test_broken_file_and_bad_values(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("{ nije json", encoding="utf-8")
    assert load_settings(path).register_id == "K1"
    path.write_text('{"terminal_slip_copies": "abc", "register_id": "K2", "unknown": 1}', encoding="utf-8")
    loaded = load_settings(path)
    assert loaded.terminal_slip_copies == 1
    assert loaded.register_id == "K2"

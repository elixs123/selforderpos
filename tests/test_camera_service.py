import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from camera_service import hosts_from_env
from settings import Settings


def test_env_hosts_replace_saved_settings(monkeypatch):
    monkeypatch.setenv("CAM_A_HOST", "10.0.0.1")
    monkeypatch.setenv("CAM_B_HOST", "10.0.0.2")
    monkeypatch.setenv("CAM_A2_HOST", "")
    saved = Settings(camera_a_host="1.1.1.1", camera_a2_host="1.1.1.9", camera_b_host="1.1.1.1")
    result = hosts_from_env(saved)
    assert (result.camera_a_host, result.camera_a2_host, result.camera_b_host) == ("10.0.0.1", "", "10.0.0.2")


def test_saved_settings_kept_without_env_hosts(monkeypatch):
    monkeypatch.delenv("CAM_A_HOST", raising=False)
    monkeypatch.delenv("CAM_B_HOST", raising=False)
    saved = Settings(camera_a_host="1.1.1.1", camera_b_host="1.1.1.2")
    assert hosts_from_env(saved) == saved

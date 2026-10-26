import os
import socket
import sys
from dataclasses import replace
from pathlib import Path

CAMERAS_FOLDER = Path(__file__).resolve().parent / "cameras"
if str(CAMERAS_FOLDER) not in sys.path:
    sys.path.insert(0, str(CAMERAS_FOLDER))

from settings import Settings

ENV_THRESHOLD = os.environ.get("CAM_MATCH_THRESHOLD", "")


class CameraSetupError(Exception):
    pass


ENV_CAMERA_KEYS = {
    "camera_a_host": "CAM_A_HOST", "camera_a2_host": "CAM_A2_HOST", "camera_b_host": "CAM_B_HOST",
    "camera_b2_host": "CAM_B2_HOST", "camera_c_host": "CAM_C_HOST", "camera_c2_host": "CAM_C2_HOST",
    "camera_channel": "CAM_CHANNEL",
}


def env_defines_cameras() -> bool:
    return bool(os.environ.get("CAM_A_HOST") and os.environ.get("CAM_B_HOST"))


def hosts_from_env(settings: Settings) -> Settings:
    if not env_defines_cameras():
        return settings
    return replace(settings, **{name: os.environ[key] for name, key in ENV_CAMERA_KEYS.items() if key in os.environ})


def port_reason(host: str, port: int = 554) -> str:
    try:
        with socket.create_connection((host, port), timeout=2):
            return f"port {port} se otvara, provjerite CAM_USER i CAM_PASSWORD"
    except OSError as error:
        return f"port {port} se ne otvara ({error}); provjerite mrežu i dozvolu za lokalnu mrežu u macOS postavkama"


def start_remote_guard(settings: Settings):
    from remote_guard import RemoteGuard

    token = os.environ.get("CAM_SERVER_TOKEN", "")
    if not token:
        raise CameraSetupError("Upišite CAM_SERVER_TOKEN u .env.")
    guard = RemoteGuard(settings.vision_server_url, token)
    guard.start()
    return guard


def start_guard(settings: Settings):
    os.environ["CAM_MODEL"] = settings.camera_model
    os.environ["CAM_COUNTER"] = "yolox" if settings.yolox_enabled else "off"
    os.environ["CAM_CLIPS"] = "da" if settings.alarm_clips else "ne"
    if settings.match_threshold > 0:
        os.environ["CAM_MATCH_THRESHOLD"] = str(settings.match_threshold)
    elif ENV_THRESHOLD:
        os.environ["CAM_MATCH_THRESHOLD"] = ENV_THRESHOLD
    else:
        os.environ.pop("CAM_MATCH_THRESHOLD", None)
    from config import CameraSettings, build_rtsp_url
    from guard import CheckoutGuard
    from reader import CameraReader

    user = os.environ.get("CAM_USER", "")
    password = os.environ.get("CAM_PASSWORD", "")
    if not user or not password:
        raise CameraSetupError("Upišite CAM_USER i CAM_PASSWORD u .env.")
    if not settings.camera_a_host or not settings.camera_b_host:
        raise CameraSetupError("Upišite IP adrese kamera A i B u postavkama.")
    hosts = {
        "A": settings.camera_a_host, "A2": settings.camera_a2_host, "B": settings.camera_b_host, "B2": settings.camera_b2_host,
        "C": settings.camera_c_host, "C2": settings.camera_c2_host,
    }
    hosts = {name: host for name, host in hosts.items() if host}
    readers = {
        name: CameraReader(CameraSettings(name, host, build_rtsp_url(host, user, password, settings.camera_channel)))
        for name, host in hosts.items()
    }
    guard = CheckoutGuard(readers)
    guard.start()
    return guard

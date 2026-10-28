import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

from dotenv import load_dotenv

from locations import env_file

load_dotenv(env_file())

CAMERA_NAMES = ("A", "A2", "A3", "B", "B2", "B3", "C", "C2")


@dataclass(frozen=True)
class CameraSettings:
    name: str
    host: str
    rtsp_url: str


class CameraConfigError(Exception):
    pass


def build_rtsp_url(host: str, user: str, password: str, channel: str) -> str:
    return f"rtsp://{quote(user, safe='')}:{quote(password, safe='')}@{host}:554/Streaming/Channels/{channel}"


def load_cameras() -> list[CameraSettings]:
    user = os.environ.get("CAM_USER", "")
    password = os.environ.get("CAM_PASSWORD", "")
    channel = os.environ.get("CAM_CHANNEL", "102")
    if not user or not password:
        raise CameraConfigError("Upiši CAM_USER i CAM_PASSWORD u .env.")
    cameras = []
    for name in CAMERA_NAMES:
        host = os.environ.get(f"CAM_{name}_HOST", "")
        if host:
            cameras.append(CameraSettings(name, host, build_rtsp_url(host, user, password, channel)))
    if not cameras:
        raise CameraConfigError("Upiši CAM_A_HOST i CAM_B_HOST u .env.")
    return cameras

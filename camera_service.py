import os
import sys
from pathlib import Path

CAMERAS_FOLDER = Path(__file__).resolve().parent / "cameras"
if str(CAMERAS_FOLDER) not in sys.path:
    sys.path.insert(0, str(CAMERAS_FOLDER))

from settings import Settings


class CameraSetupError(Exception):
    pass


def start_guard(settings: Settings):
    os.environ["CAM_MODEL"] = settings.camera_model
    if settings.match_threshold > 0:
        os.environ["CAM_MATCH_THRESHOLD"] = str(settings.match_threshold)
    else:
        os.environ.pop("CAM_MATCH_THRESHOLD", None)
    from config import CameraSettings, build_rtsp_url
    from guard import CheckoutGuard
    from reader import CameraReader

    user = os.environ.get("CAM_USER", "")
    password = os.environ.get("CAM_PASSWORD", "")
    if not user or not password:
        raise CameraSetupError("Upišite CAM_USER i CAM_PASSWORD u .env.")
    hosts = {"A": settings.camera_a_host, "B": settings.camera_b_host}
    if not all(hosts.values()):
        raise CameraSetupError("Upišite IP adrese kamera A i B u postavkama.")
    readers = {
        name: CameraReader(CameraSettings(name, host, build_rtsp_url(host, user, password, settings.camera_channel)))
        for name, host in hosts.items()
    }
    guard = CheckoutGuard(readers)
    guard.start()
    return guard

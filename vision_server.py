import argparse
import os
import sys
import threading
import time
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QStandardPaths
from PySide6.QtWidgets import QApplication

from camera_service import CameraSetupError, env_defines_cameras, hosts_from_env, port_reason, start_guard
from locations import app_folder
from settings import load_settings
from vision_api import DEFAULT_PORT, make_server


def settings_path() -> Path:
    return Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)) / "settings.json"


def report_cameras(guard) -> None:
    time.sleep(6)
    for name, reader in guard.readers.items():
        host = reader.settings.host
        if reader.status == "uživo":
            print(f"Kamera {name} ({host}): uživo")
        else:
            print(f"Kamera {name} ({host}): {reader.status}, {port_reason(host)}")
    for _ in range(12):
        if guard.zone_a_ready:
            print("Zona A je spremna.")
            return
        print(f"Zona A još nije spremna: {guard.zone_a_waiting_reason()}")
        time.sleep(5)


def main() -> None:
    parser = argparse.ArgumentParser(description="Server kamera i AI provjere za samouslužnu kasu")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--monitor", action="store_true")
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--model", default="", help="AI model: dinov2, dinov2-base, clip ili mobilenet (zadano iz CAM_MODEL u .env)")
    arguments = parser.parse_args()

    token = os.environ.get("CAM_SERVER_TOKEN", "")
    if not token:
        sys.exit("Upišite CAM_SERVER_TOKEN u .env (isti na ovom računaru i na kasi).")
    application = QApplication(sys.argv[:1]) if arguments.monitor else QCoreApplication(sys.argv[:1])
    application.setOrganizationName("Penny")
    application.setApplicationName("selforderpos")

    settings = hosts_from_env(load_settings(settings_path()))
    model = arguments.model or os.environ.get("CAM_MODEL", "")
    if model:
        settings = replace(settings, camera_model=model)
    print(f"AI model: {settings.camera_model}")
    print(f"Adrese kamera su iz {'.env' if env_defines_cameras() else 'postavki (settings.json)'}:")
    for name, host in (("A", settings.camera_a_host), ("A2", settings.camera_a2_host), ("B", settings.camera_b_host), ("B2", settings.camera_b2_host),
                      ("C", settings.camera_c_host), ("C2", settings.camera_c2_host)):
        if host:
            print(f"  {name}: {host}")
    try:
        guard = start_guard(settings)
    except CameraSetupError as error:
        sys.exit(str(error))
    if arguments.debug:
        guard.enable_debug(app_folder() / "data" / "debug" / datetime.now().strftime("%Y%m%d-%H%M%S"))
    threading.Thread(target=report_cameras, args=(guard,), daemon=True).start()
    server = make_server(guard, token, arguments.host, arguments.port)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f"Server kamera radi na portu {arguments.port}. U kasi upišite adresu http://<IP ovog računara>:{arguments.port}")

    try:
        if arguments.monitor:
            from screens.diagnostics import DiagnosticsWindow

            window = DiagnosticsWindow(lambda: guard)
            window.show()
            application.exec()
        else:
            while True:
                time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        guard.stop()


if __name__ == "__main__":
    main()

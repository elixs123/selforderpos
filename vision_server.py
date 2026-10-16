import argparse
import os
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QStandardPaths
from PySide6.QtWidgets import QApplication

from camera_service import CameraSetupError, start_guard
from locations import app_folder
from settings import load_settings
from vision_api import DEFAULT_PORT, make_server


def settings_path() -> Path:
    return Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)) / "settings.json"


def main() -> None:
    parser = argparse.ArgumentParser(description="Server kamera i AI provjere za samouslužnu kasu")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--monitor", action="store_true")
    parser.add_argument("--debug", action="store_true")
    arguments = parser.parse_args()

    token = os.environ.get("CAM_SERVER_TOKEN", "")
    if not token:
        sys.exit("Upišite CAM_SERVER_TOKEN u .env (isti na ovom računaru i na kasi).")
    application = QApplication(sys.argv[:1]) if arguments.monitor else QCoreApplication(sys.argv[:1])
    application.setOrganizationName("Penny")
    application.setApplicationName("selforderpos")

    settings = load_settings(settings_path())
    try:
        guard = start_guard(settings)
    except CameraSetupError as error:
        sys.exit(str(error))
    if arguments.debug:
        guard.enable_debug(app_folder() / "data" / "debug" / datetime.now().strftime("%Y%m%d-%H%M%S"))
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

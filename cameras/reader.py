import os

os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp")

import threading
import time
from collections import deque

import cv2
import numpy as np

from config import CameraSettings

RECONNECT_SECONDS = 2


class FpsMeter:
    def __init__(self, window: int = 30) -> None:
        self.times: deque[float] = deque(maxlen=window)

    def tick(self) -> float:
        self.times.append(time.perf_counter())
        if len(self.times) < 2:
            return 0.0
        return (len(self.times) - 1) / (self.times[-1] - self.times[0])


class CameraReader(threading.Thread):
    def __init__(self, settings: CameraSettings) -> None:
        super().__init__(daemon=True)
        self.settings = settings
        self.status = "spajanje"
        self.fps = 0.0
        self.frame_number = 0
        self._frame: np.ndarray | None = None
        self._lock = threading.Lock()
        self._running = True

    def run(self) -> None:
        while self._running:
            camera = cv2.VideoCapture(self.settings.rtsp_url, cv2.CAP_FFMPEG)
            if not camera.isOpened():
                self.status = "nema veze"
                time.sleep(RECONNECT_SECONDS)
                continue
            self.status = "uživo"
            meter = FpsMeter()
            while self._running:
                ok, frame = camera.read()
                if not ok:
                    self.status = "prekid, ponovo spajam"
                    break
                with self._lock:
                    self._frame = frame
                    self.frame_number += 1
                self.fps = meter.tick()
            camera.release()
            if self._running:
                time.sleep(RECONNECT_SECONDS)

    def latest(self) -> np.ndarray | None:
        with self._lock:
            return None if self._frame is None else self._frame.copy()

    def stop(self) -> None:
        self._running = False

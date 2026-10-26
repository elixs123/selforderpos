import json
import time
from pathlib import Path

import cv2
import numpy as np

SIZE = (320, 180)
COVERED_STD = 6.0
DARK_MEAN = 12.0
BLUR_RATIO = 0.2
MOVED_SHARE = 0.06
MOVED_MIN_RESPONSE = 0.08
PROBLEM_SECONDS = 10.0

COVERED = "prekrivena ili bez slike"
DARK = "slika je tamna (prekrivena?)"
BLURRED = "slika je mutna (prljavo ili prekriveno sočivo)"
MOVED = "kamera je pomjerena"


def _gray(frame: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(cv2.resize(frame, SIZE, interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY).astype(np.float32)


def sharpness(gray: np.ndarray) -> float:
    return float(cv2.Laplacian(gray, cv2.CV_32F).var())


def shift(reference: np.ndarray, gray: np.ndarray) -> tuple[float, float]:
    """Pomak cijele slike u pikselima (SIZE) i koliko je pomak pouzdan; ljudi u kadru ga malo mijenjaju, pozadina dominira."""
    window = cv2.createHanningWindow(SIZE, cv2.CV_32F)
    (dx, dy), response = cv2.phaseCorrelate(reference, gray, window)
    return float(np.hypot(dx, dy)), float(response)


class TamperCheck:
    """Prekrivena, mutna ili pomjerena kamera: poredi sliku sa referencom snimljenom dok je kamera bila ispravna."""

    def __init__(self, folder: Path, zones_changed_at: str = "") -> None:
        self.folder = folder
        self.folder.mkdir(parents=True, exist_ok=True)
        self.zones_changed_at = zones_changed_at
        self._references: dict[str, tuple[np.ndarray, float]] = {}
        self._since: dict[str, tuple[str, float]] = {}

    def _paths(self, name: str) -> tuple[Path, Path]:
        return self.folder / f"{name}.png", self.folder / f"{name}.json"

    def _reference(self, name: str) -> tuple[np.ndarray, float] | None:
        if name in self._references:
            return self._references[name]
        image_path, info_path = self._paths(name)
        try:
            info = json.loads(info_path.read_text(encoding="utf-8"))
            if info.get("zones") != self.zones_changed_at:
                return None
            image = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
        except (OSError, ValueError):
            return None
        if image is None:
            return None
        self._references[name] = (image.astype(np.float32), float(info["sharpness"]))
        return self._references[name]

    def _remember(self, name: str, gray: np.ndarray) -> None:
        image_path, info_path = self._paths(name)
        value = sharpness(gray)
        cv2.imwrite(str(image_path), gray.astype(np.uint8))
        info_path.write_text(json.dumps({"sharpness": value, "zones": self.zones_changed_at}), encoding="utf-8")
        self._references[name] = (gray, value)

    def reset(self, name: str) -> None:
        self._references.pop(name, None)
        for path in self._paths(name):
            path.unlink(missing_ok=True)

    def raw_problem(self, name: str, frame: np.ndarray) -> str:
        gray = _gray(frame)
        if float(gray.std()) < COVERED_STD:
            return DARK if float(gray.mean()) < DARK_MEAN else COVERED
        reference = self._reference(name)
        if reference is None:
            self._remember(name, gray)
            return ""
        image, reference_sharpness = reference
        if reference_sharpness > 0 and sharpness(gray) < reference_sharpness * BLUR_RATIO:
            return BLURRED
        distance, response = shift(image, gray)
        if response >= MOVED_MIN_RESPONSE and distance > MOVED_SHARE * SIZE[0]:
            return MOVED
        return ""

    def check(self, name: str, frame: np.ndarray | None, now: float | None = None) -> str:
        """Problem koji traje bar PROBLEM_SECONDS (prolazak kupca ispred kamere se ne računa)."""
        now = time.monotonic() if now is None else now
        problem = self.raw_problem(name, frame) if frame is not None and frame.size else ""
        if not problem:
            self._since.pop(name, None)
            return ""
        kind, since = self._since.get(name, ("", now))
        if kind != problem:
            self._since[name] = (problem, now)
            return ""
        return problem if now - since >= PROBLEM_SECONDS else ""

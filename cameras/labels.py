import os
import re
import threading
from difflib import SequenceMatcher

import cv2
import numpy as np

MIN_SIDE = 150
MAX_CROPS = 2
OCR_SIDE = 640
MIN_CONFIDENCE = 0.5
MIN_LETTERS = 3
WORD_MATCH = 0.8
GENERIC_WORDS = {"VODA", "PET", "PIVO", "SOK", "LIMENKA", "BOCA", "NOVO", "NATURAL", "PRIRODNA", "MINERALNA", "GAZIRANA"}

_ocr = None
_failed = False
_lock = threading.Lock()


def enabled() -> bool:
    """Čitanje etikete; uključuje se u Postavke > Kamere (upisuje se u CAM_OCR pri pokretanju kamera)."""
    return os.environ.get("CAM_OCR", "da").lower() not in ("", "off", "0", "ne")


def _engine():
    global _ocr, _failed
    if _ocr is None and not _failed:
        try:
            from rapidocr_onnxruntime import RapidOCR

            _ocr = RapidOCR()
        except Exception as error:
            print(f"Čitanje etikete (RapidOCR) nije dostupno: {error}")
            _failed = True
    return _ocr


def normalize(text: str) -> list[str]:
    """Riječi velikim slovima bez kvačica; samo one sa bar MIN_LETTERS slova (0.5L, 1891 i slično se ne računaju)."""
    plain = text.upper().translate(str.maketrans("ČĆŽŠĐ", "CCZSD"))
    words = re.findall(r"[A-Z0-9]+", plain)
    return [word for word in words
            if sum(char.isalpha() for char in word) >= MIN_LETTERS and len(word) >= 4 and word not in GENERIC_WORDS]


def name_words(name: str | None) -> set[str]:
    return set(normalize(name or ""))


def similar(first: str, second: str) -> bool:
    """OCR griješi u slovu-dva (KISELJAK -> KISELAK) i spaja riječi (ROGASKA SLATINA -> OCASKASLATINA)."""
    if first == second:
        return True
    shorter, longer = sorted((first, second), key=len)
    if len(shorter) >= 5 and shorter in longer:
        return True
    return SequenceMatcher(None, first, second).ratio() >= WORD_MATCH


def read_words(image: np.ndarray | None) -> set[str]:
    """Riječi sa etikete; male slike se preskaču (OCR na njima ništa ne pročita, a troši vrijeme)."""
    if image is None or not image.size or max(image.shape[:2]) < MIN_SIDE or not enabled():
        return set()
    engine = _engine()
    if engine is None:
        return set()
    found: set[str] = set()
    for rotation in (None, cv2.ROTATE_90_CLOCKWISE, cv2.ROTATE_90_COUNTERCLOCKWISE):
        rotated = image if rotation is None else cv2.rotate(image, rotation)
        scale = max(1.0, OCR_SIDE / max(rotated.shape[:2]))
        resized = cv2.resize(rotated, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        try:
            with _lock:
                result, _ = engine(resized)
        except Exception as error:
            print(f"Čitanje etikete: {error}")
            return found
        for _, text, confidence in result or []:
            if float(confidence) >= MIN_CONFIDENCE:
                found.update(normalize(text))
    return found


def read_crops(crops: list[np.ndarray]) -> list[set[str]]:
    """Čita samo MAX_CROPS najvećih slika (male ne daju tekst), svaku u tri položaja jer boca može ležati."""
    if not enabled():
        return [set() for _ in crops]
    sizes = sorted(range(len(crops)), key=lambda index: -crops[index].size if crops[index] is not None else 0)
    chosen = set(sizes[:MAX_CROPS])
    return [read_words(crop) if index in chosen else set() for index, crop in enumerate(crops)]


def distinctive(products: dict[str, set[str]]) -> dict[str, set[str]]:
    """Izbaci riječi koje se nađu na više artikala (npr. ime proizvođača) - one ne razlikuju artikle."""
    result = {}
    for code, words in products.items():
        others = [word for other, other_words in products.items() if other != code for word in other_words]
        result[code] = {word for word in words if not any(similar(word, other) for other in others)}
    return result


def check(read: set[str], scanned_code: str | None, products: dict[str, set[str]]) -> tuple[str, str, str | None]:
    """('match' | 'other' | 'unknown', pročitana riječ, šifra drugog artikla).

    products: šifra -> riječi (iz naziva i naučene sa etikete), uključujući skenirani artikal."""
    if not read:
        return "unknown", "", None
    words = distinctive(products)
    scanned = words.get(scanned_code or "", set())
    for word in sorted(read):
        if any(similar(word, known) for known in scanned):
            return "match", word, None
    for word in sorted(read):
        for code, known in words.items():
            if code != scanned_code and any(similar(word, other) for other in known):
                return "other", word, code
    return "unknown", "", None

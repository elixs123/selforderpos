import numpy as np

from archive import image_problem
from watcher import ZoneWatcher

# Koliko različitih strana artikla osoblje treba uslikati (svaka strana = sve kamere zone B odjednom).
CAPTURE_VIEWS = 6
# Slika koja ovoliko liči na već uslikanu stranu (CLIP otisak, ista kamera) je ista strana; prag provizoran.
SAME_VIEW = 0.92
# Poslije prve kamere koja javi miran artikal, ostale kamere zone B imaju ovoliko vremena da i one jave.
COLLECT_SECONDS = 1.0
HAND_CHECK_SECONDS = 0.5
CROP_PADDING = 12

PLACE_MESSAGE = "Ispraznite zonu B, pa stavite artikal na sredinu zone B i sklonite ruku."
TURN_MESSAGE = "Okrenite artikal na drugu stranu i sklonite ruku."


class CaptureSession:
    """Osoblje snima artikal u zoni B, strana po strana, dok kasa ne skupi CAPTURE_VIEWS različitih strana.

    Kasa sama slika kad je artikal miran i nema ruke, pa kaže šta dalje ("sklonite ruku", "okrenite artikal").
    Slike idu u reference za prepoznavanje (potvrdilo osoblje) i u arhivu izgleda artikla.
    """

    def __init__(self, rois, find_hand, embed, save, product_name: str, target: int = CAPTURE_VIEWS) -> None:
        self._rois = rois
        self._find_hand = find_hand
        self._embed = embed
        self._save = save
        self.product_name = product_name
        self.target = target
        self.views = 0
        self.state = "place"
        self.message = PLACE_MESSAGE
        self._watchers: dict[str, ZoneWatcher] = {}
        self._vectors: dict[str, list[np.ndarray]] = {}
        self._pending: dict[str, np.ndarray] = {}
        self._first_at: float | None = None
        self._hand_checked_at = -1000.0
        self._hand = False
        # Prazna zona B na početku je osnova: artikal je ono što se od nje razlikuje.
        for name, roi in rois().items():
            watcher = ZoneWatcher()
            watcher.arm(roi)
            self._watchers[name] = watcher

    def status(self) -> dict:
        return {"active": self.state != "done", "state": self.state, "message": self.message,
                "views": self.views, "target": self.target, "product_name": self.product_name}

    def step(self, now: float) -> None:
        if self.state == "done":
            return
        rois = self._rois()
        if not rois or not self._watchers:
            self.message = "Kamere zone B nemaju sliku. Provjerite kamere."
            return
        if now - self._hand_checked_at >= HAND_CHECK_SECONDS:
            self._hand_checked_at = now
            self._hand = any(self._find_hand(roi) for roi in rois.values())
        for name, watcher in self._watchers.items():
            roi = rois.get(name)
            if roi is None or name in self._pending:
                continue
            placement = watcher.update(roi, now)
            if placement is None:
                continue
            if self._hand:
                watcher.rearm()
                continue
            x, y, w, h = placement.box
            top, left = max(0, y - CROP_PADDING), max(0, x - CROP_PADDING)
            self._pending[name] = roi[top:y + h + CROP_PADDING, left:x + w + CROP_PADDING].copy()
            if self._first_at is None:
                self._first_at = now
        if self._hand:
            self.message = "Sklonite ruku iz zone B, kasa slika kad je artikal miran."
        if self._first_at is not None and (now - self._first_at >= COLLECT_SECONDS or len(self._pending) == len(self._watchers)):
            self._take(self._pending)
            self._pending, self._first_at = {}, None
            for watcher in self._watchers.values():
                watcher.rearm()

    def _take(self, crops: dict[str, np.ndarray]) -> None:
        good = {name: crop for name, crop in crops.items() if not image_problem(crop) and not self._find_hand(crop)}
        if not good:
            self.message = "Slika nije dobra (artikal premali, mutan ili ruka na slici). Pomjerite artikal na sredinu zone B."
            return
        vectors = {name: self._vector(crop) for name, crop in good.items()}
        if self.views and all(self._seen(name, vector) for name, vector in vectors.items()):
            self.message = "Ova strana je već uslikana. " + TURN_MESSAGE
            return
        for name, crop in good.items():
            self._save(name, crop)
            if vectors[name] is not None:
                self._vectors.setdefault(name, []).append(vectors[name])
        self.views += 1
        if self.views >= self.target:
            self.state, self.message = "done", f"Gotovo: artikal je uslikan sa {self.views} strana. Možete ga skloniti."
        else:
            self.state, self.message = "turn", f"Uslikano {self.views} od {self.target}. {TURN_MESSAGE}"

    def _vector(self, crop: np.ndarray) -> np.ndarray | None:
        vector = self._embed(crop) if self._embed is not None else None
        if vector is None:
            return None
        vector = np.asarray(vector, dtype=np.float32).reshape(-1)
        return vector / max(float(np.linalg.norm(vector)), 1e-6)

    def _seen(self, name: str, vector: np.ndarray | None) -> bool:
        if vector is None:
            return False
        return any(float(vector @ previous) >= SAME_VIEW for previous in self._vectors.get(name, []))

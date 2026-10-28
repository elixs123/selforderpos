import sys

import pytest


@pytest.fixture(autouse=True)
def no_hand_model(monkeypatch):
    """Testovi ne trebaju MediaPipe model za ruke; njegov __del__ zna zaglaviti pytest kad ga GC briše."""
    guard = sys.modules.get("guard")
    if guard is not None:
        monkeypatch.setattr(guard, "load_hand_detector", lambda: None)


@pytest.fixture(autouse=True)
def no_label_reading(monkeypatch):
    """OCR etikete je spor za učitati; testovi koji ga trebaju sami ga uključe (CAM_OCR=da)."""
    monkeypatch.setenv("CAM_OCR", "ne")

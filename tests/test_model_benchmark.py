import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "cameras"))

from benchmark_models import auc, load_crops
from embedder import CLIP_MEAN, CLIP_STD, MODELS, to_blob
from samples import SampleStore


def test_every_model_has_a_blob_of_the_right_shape():
    image = np.full((90, 60, 3), 120, dtype=np.uint8)
    for spec in MODELS.values():
        assert to_blob(image, spec.mean, spec.std).shape == (1, 3, 224, 224)


def test_clip_uses_its_own_normalisation():
    image = np.full((50, 50, 3), 120, dtype=np.uint8)
    assert not np.allclose(to_blob(image), to_blob(image, CLIP_MEAN, CLIP_STD))
    assert MODELS["clip"].mean == CLIP_MEAN and MODELS["clip"].std == CLIP_STD


def test_auc_separates_and_overlaps():
    assert auc(np.array([0.9, 0.8]), np.array([0.2, 0.1])) == 1.0
    assert auc(np.array([0.5]), np.array([0.5])) == 0.5
    assert auc(np.array([0.1]), np.array([0.9])) == 0.0


def test_only_accepted_placements_are_used(tmp_path):
    store = SampleStore(tmp_path)
    image = np.full((40, 40, 3), 120, dtype=np.uint8)
    store.save("placed", "1", "A1", "Mlijeko", "B", crop_image=image, verdict="ok")
    store.save("placed", "1", "A1", "Mlijeko", "B2", crop_image=image, verdict="learned")
    store.save("placed", "1", "A1", "Mlijeko", "B", crop_image=image, verdict="mismatch")
    store.save("taken", "1", "A1", "Mlijeko", "A1", crop_image=image)
    crops = load_crops(store, "")
    assert len(crops) == 2
    assert {camera for _, _, camera, _ in crops} == {"B", "B2"}

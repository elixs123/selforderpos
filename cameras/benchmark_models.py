import argparse
import itertools
import sqlite3
import sys
import time
from contextlib import closing
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent))

from embedder import MODELS, Embedder
from samples import SampleStore
from similarity import color_histogram, histogram_overlap, _prepare

GOOD_CROPS = """
SELECT id, product_code, camera, crop_path FROM samples
WHERE event = 'placed' AND verdict IN ('learned', 'ok') AND crop_path IS NOT NULL AND product_code IS NOT NULL
AND created_at >= ? ORDER BY id
"""


def load_crops(store: SampleStore, since: str) -> list[tuple[int, str, str, np.ndarray]]:
    with closing(sqlite3.connect(store.database)) as connection:
        rows = connection.execute(GOOD_CROPS, (since,)).fetchall()
    crops = []
    for row_id, product, camera, path in rows:
        image = store.load_image(path)
        if image is not None:
            crops.append((row_id, product, camera, image))
    return crops


def auc(same: np.ndarray, different: np.ndarray) -> float:
    return float((same[:, None] > different[None, :]).mean() + 0.5 * (same[:, None] == different[None, :]).mean())


def report(title: str, same: list[float], different: list[float]) -> None:
    if not same or not different:
        print(f"  {title}: premalo parova ({len(same)} isti, {len(different)} različit)")
        return
    same_scores, different_scores = np.array(same), np.array(different)
    low, high = float(np.percentile(same_scores, 10)), float(np.percentile(different_scores, 90))
    advice = f"prag oko {(low + high) / 2:.2f}" if low > high else "isti i različiti artikli se preklapaju"
    print(
        f"  {title}: {len(same)} isti, {len(different)} različit | AUC {auc(same_scores, different_scores):.3f} | "
        f"isti min {same_scores.min():.2f} / p10 {low:.2f} / sred {same_scores.mean():.2f} | "
        f"različit sred {different_scores.mean():.2f} / p90 {high:.2f} / max {different_scores.max():.2f} | {advice}"
    )


def evaluate(name: str, crops: list, weight: float) -> None:
    try:
        embedder = Embedder(name)
    except Exception as error:
        print(f"\n{name}: preskačem ({error})")
        return
    if embedder.name != name:
        print(f"\n{name}: model se nije mogao učitati, preskačem")
        return
    started = time.perf_counter()
    vectors = [embedder.embed(image) for _, _, _, image in crops]
    per_image = (time.perf_counter() - started) * 1000 / len(crops)
    histograms = [color_histogram(_prepare(image)) for _, _, _, image in crops]
    print(f"\n{name}: {per_image:.0f} ms po slici, zadani prag {embedder.threshold}")
    for label, use_color in (("samo AI", False), (f"AI {weight:.1f} + boja {1 - weight:.1f} (kao kasa)", True)):
        same_all, different_all, same_cross, different_cross, same_one, different_one = [], [], [], [], [], []
        for first, second in itertools.combinations(range(len(crops)), 2):
            ai = float(vectors[first] @ vectors[second])
            value = weight * ai + (1 - weight) * histogram_overlap(histograms[first], histograms[second]) if use_color else ai
            same = crops[first][1] == crops[second][1]
            (same_all if same else different_all).append(value)
            if crops[first][2] != crops[second][2]:
                (same_cross if same else different_cross).append(value)
            else:
                (same_one if same else different_one).append(value)
        print(f" {label}")
        report("sve kamere", same_all, different_all)
        report("različite kamere (B i B2)", same_cross, different_cross)
        report("ista kamera", same_one, different_one)


def main() -> None:
    parser = argparse.ArgumentParser(description="Poredi AI modele na snimcima odobrenih odlaganja iz data/samples.")
    parser.add_argument("--models", default=",".join(MODELS), help="npr. dinov2,dinov2-base,clip,mobilenet")
    parser.add_argument("--since", default="", help="samo snimci od ovog datuma, npr. 2026-10-16T16:06")
    parser.add_argument("--weight", type=float, default=0.7, help="udio AI-ja u ocjeni (ostalo je boja)")
    arguments = parser.parse_args()
    store = SampleStore()
    crops = load_crops(store, arguments.since)
    products = sorted({product for _, product, _, _ in crops})
    print(f"Snimaka odobrenih odlaganja: {len(crops)}, artikala: {len(products)}")
    if len(crops) < 6 or len(products) < 2:
        print("Premalo podataka: treba bar 2 različita artikla s po nekoliko odobrenih odlaganja (zelena ili 'learned' presuda).")
        return
    for name in arguments.models.split(","):
        evaluate(name.strip(), crops, arguments.weight)


if __name__ == "__main__":
    main()

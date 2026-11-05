import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "cameras"))

from PySide6.QtWidgets import QApplication

from declarations import count_declarations, find_declarations, group_declarations
from test_guard_ready import FakeReader, make_guard

APP = QApplication.instance() or QApplication([])


def draw_label(image: np.ndarray, x: int, y: int) -> None:
    """Deklaracija: zeleno polje, bijelo polje, crvena traka uz desni rub."""
    image[y:y + 120, x:x + 60] = (40, 160, 60)
    image[y:y + 120, x + 60:x + 150] = (245, 245, 245)
    image[y + 10:y + 110, x + 66:x + 144:4] = (20, 20, 20)  # barkod
    image[y:y + 120, x + 150:x + 170] = (40, 40, 210)


def box_with_labels(count: int) -> np.ndarray:
    image = np.full((480, 640, 3), 130, dtype=np.uint8)
    for index in range(count):
        draw_label(image, 40 + index * 280, 120)
    return image


def test_counts_each_label():
    assert count_declarations(box_with_labels(0)) == 0
    assert count_declarations(box_with_labels(1)) == 1
    assert count_declarations(box_with_labels(2)) == 2


def test_counts_rotated_label():
    image = box_with_labels(1)
    turn = cv2.getRotationMatrix2D((320, 240), 35, 1.0)
    assert count_declarations(cv2.warpAffine(image, turn, (640, 480), borderValue=(130, 130, 130))) == 1


def test_red_and_green_print_without_white_field_is_not_a_label():
    image = np.full((480, 640, 3), 130, dtype=np.uint8)
    image[100:220, 100:160] = (40, 160, 60)
    image[100:220, 250:270] = (40, 40, 210)
    assert count_declarations(image) == 0
    assert count_declarations(None) == 0


class ArmedWatcher:
    armed = True
    change_ratio = 0.0
    change_min = 1.0
    last_mask = None
    items = []
    parts = 0

    def arm(self, roi):
        self.armed = True

    def rearm(self):
        self.armed = True

    def disarm(self):
        self.armed = False


def armed_guard(monkeypatch, tmp_path, labels: int):
    readers = {"A": FakeReader(), "B": FakeReader()}
    guard = make_guard(monkeypatch, tmp_path, readers)
    guard.watchers = {name: ArmedWatcher() for name in guard.watchers} or {"B": ArmedWatcher()}
    guard.zones = {}
    now = time.monotonic()
    guard._note_labels("A", find_declarations(box_with_labels(labels)), now - 2)
    guard._note_labels("A", [], now - 1)  # kutija je uzeta iz zone
    guard.barcode, guard.product_code, guard.product_name = "2890619002483", "097992", "DINJA"
    guard._start_labels("2890619002483", True)
    guard._wait_for_zone_b([(box_with_labels(labels), None, now, "A")])
    return guard


def test_all_labels_must_be_scanned(monkeypatch, tmp_path):
    guard = armed_guard(monkeypatch, tmp_path, 2)
    assert guard.state == "waiting_labels"
    assert guard.labels_required == 2
    assert guard.labels_missing == 1
    assert guard.product_code is None  # miješana kutija se ne poredi sa slikama artikla
    assert guard.scan("2890619002483", "097992", "DINJA", True) is False  # ista deklaracija
    assert guard.labels_missing == 1
    assert guard.scan("2890626002223", "097999", "ANANAS", True) is True
    assert guard.labels_missing == 0
    assert guard.state == "waiting_place"


def test_box_still_in_zone_a_counts_its_labels(monkeypatch, tmp_path):
    readers = {"A": FakeReader(), "B": FakeReader()}
    guard = make_guard(monkeypatch, tmp_path, readers)
    now = time.monotonic()
    guard._note_labels("A", find_declarations(box_with_labels(2)), now)
    assert guard._labels_taken_from_a(now) == 2


def test_only_the_box_that_left_zone_a_counts(monkeypatch, tmp_path):
    readers = {"A": FakeReader(), "B": FakeReader()}
    guard = make_guard(monkeypatch, tmp_path, readers)
    now = time.monotonic()
    left = (100.0, 100.0, 100.0)
    stays = [(1000.0, 100.0, 100.0), (1000.0, 300.0, 100.0)]
    guard._note_labels("A", [left] + stays, now - 2)
    guard._note_labels("A", stays, now - 1)
    assert guard._labels_taken_from_a(now) == 1


def test_labels_of_previous_box_are_forgotten(monkeypatch, tmp_path):
    guard = armed_guard(monkeypatch, tmp_path, 2)
    guard._finish("accepted", "ok", "Kutija odgovara.")
    assert guard._labels_taken_from_a(time.monotonic()) == 0


def test_group_declarations_splits_far_boxes():
    groups = group_declarations([(0.0, 0.0, 100.0), (200.0, 0.0, 100.0), (2000.0, 0.0, 100.0)])
    assert sorted(len(group) for group in groups) == [1, 2]


def test_zone_b_finds_label_that_zone_a_did_not_see(monkeypatch, tmp_path):
    guard = armed_guard(monkeypatch, tmp_path, 1)
    assert guard.labels_missing == 0
    name = next(iter(guard.watchers))
    placement = SimpleNamespace(change_ratio=0.5, box=(0, 0, 640, 480))
    guard._on_placed({name: placement}, {name: (box_with_labels(2), (0, 0))}, time.monotonic())
    assert guard.labels_missing == 1
    assert guard.state == "waiting_labels"
    assert not guard._judging
    assert guard.zone_b_armed


def test_single_label_stays_normal_article(monkeypatch, tmp_path):
    guard = armed_guard(monkeypatch, tmp_path, 1)
    assert guard.state == "waiting_place"
    assert guard.product_code == "097992"
    assert guard.labels_missing == 0


def test_ordinary_scan_does_not_count_labels(monkeypatch, tmp_path):
    readers = {"A": FakeReader(), "B": FakeReader()}
    guard = make_guard(monkeypatch, tmp_path, readers)
    guard.watchers = {name: ArmedWatcher() for name in guard.watchers} or {"B": ArmedWatcher()}
    guard._note_labels("A", find_declarations(box_with_labels(2)), time.monotonic())
    guard._start_labels("1001", False)
    guard.product_code = "A1"
    guard._wait_for_zone_b([(box_with_labels(2), None, time.monotonic(), "A")])
    assert guard.state == "waiting_place"
    assert guard.product_code == "A1"


class FakeGuard:
    state = "waiting_labels"
    message = "Na kutiji je više deklaracija. Skenirano 1 od 2. Skenirajte i ostale."
    outcome = None
    held_message = ""
    labels_required = 2

    def __init__(self):
        self.scans = []

    def scan(self, barcode, code, name, weighed=False):
        if barcode in self.scans:
            self.message = "Ova deklaracija je već skenirana. Skenirajte drugu."
            return False
        self.scans.append(barcode)
        return True


def test_drop_screen_collects_all_labels(monkeypatch):
    import screens.drop as drop_module
    from catalog import Product

    melon = Product("097992", "2890619002483", "DINJA", 5.95, 248)
    pineapple = Product("097999", "2097999002223", "ANANAS", 3.95, 222)
    monkeypatch.setattr(drop_module, "find_by_barcode", {pineapple.barcode: pineapple, melon.barcode: melon, "1001": Product("A1", "1001", "Mlijeko", 1.0)}.get)
    screen = drop_module.DropScreen()
    accepted = []
    screen.accepted.connect(accepted.append)
    guard = FakeGuard()
    screen.begin(melon, guard, 0)
    assert screen.pages.currentWidget() is screen.labels_page
    assert screen.labels_step.text() == "Skenirajte deklaraciju 2 od 2"
    for barcode in ("1001", pineapple.barcode):
        screen.barcode_input.setText(barcode)
        screen._on_barcode_entered()
    assert guard.scans == [pineapple.barcode]  # obični artikal se ne prima kao deklaracija
    assert "0,470 kg" in screen.price_label.text()
    assert "2,36" in screen.price_label.text()  # 1,48 + 0,88
    guard.outcome = SimpleNamespace(number=1, kind="accepted", message="")
    screen._poll()
    assert accepted == [melon, pineapple]


def test_double_read_on_finished_box_keeps_state(monkeypatch, tmp_path):
    guard = armed_guard(monkeypatch, tmp_path, 1)
    assert guard.scan("2890619002483", "097992", "DINJA", True) is False
    assert guard.state == "waiting_place"
    assert "već skenirana" in guard.message


def test_scan_while_judging_does_not_change_article(monkeypatch, tmp_path):
    guard = armed_guard(monkeypatch, tmp_path, 1)
    for watcher in guard.watchers.values():
        watcher.disarm()
    guard._judging = True
    assert guard.scan("2890626002223", "097999", "ANANAS", True) is False
    assert guard.product_code == "097992"
    assert guard.barcode == "2890619002483"


def test_item_taken_after_all_labels_scanned_still_counts(monkeypatch, tmp_path):
    guard = armed_guard(monkeypatch, tmp_path, 1)
    tracker = next(iter(guard.trackers.values()))
    tracker.last_before = box_with_labels(0)
    camera = next(iter(guard.trackers))
    event = SimpleNamespace(kind="taken", item=box_with_labels(0), extra=())
    guard._taken_at = 0.0
    guard._on_zone_a_event(camera, event, time.monotonic(), sync=False)
    assert len(guard._takes) == 1

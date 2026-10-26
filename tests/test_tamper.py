import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "cameras"))

from tamper import BLURRED, COVERED, DARK, MOVED, PROBLEM_SECONDS, TamperCheck


def scene(offset: int = 0) -> np.ndarray:
    random = np.random.default_rng(7)
    big = random.integers(0, 255, (400, 700, 3), dtype=np.uint8)
    big = cv2.GaussianBlur(big, (5, 5), 0)
    for index in range(12):
        cv2.rectangle(big, (40 + index * 50, 60), (70 + index * 50, 300), (30 * index % 255, 200, 90), -1)
    return big[20:380, 20 + offset:660 + offset].copy()


def confirmed(check: TamperCheck, frame, start: float = 0.0) -> str:
    check.check("A", frame, start)
    return check.check("A", frame, start + PROBLEM_SECONDS)


def test_healthy_camera_has_no_problem(tmp_path):
    check = TamperCheck(tmp_path)
    assert check.check("A", scene(), 0.0) == ""
    assert confirmed(check, scene(), 1.0) == ""


def test_covered_dark_blurred_and_moved_camera(tmp_path):
    check = TamperCheck(tmp_path)
    check.check("A", scene(), 0.0)
    assert confirmed(check, np.full((360, 640, 3), 128, np.uint8), 1.0) == COVERED
    assert confirmed(check, np.zeros((360, 640, 3), np.uint8), 100.0) == DARK
    assert confirmed(check, cv2.GaussianBlur(scene(), (31, 31), 12), 200.0) == BLURRED
    assert confirmed(check, scene(offset=60), 300.0) == MOVED


def test_short_problem_is_ignored_and_reference_survives_restart(tmp_path):
    check = TamperCheck(tmp_path)
    check.check("A", scene(), 0.0)
    covered = np.full((360, 640, 3), 128, np.uint8)
    check.check("A", covered, 1.0)
    assert check.check("A", covered, 1.0 + PROBLEM_SECONDS / 2) == ""
    assert check.check("A", scene(), 7.0) == ""
    again = TamperCheck(tmp_path)
    assert confirmed(again, scene(offset=60), 10.0) == MOVED


def test_new_zones_take_a_new_reference(tmp_path):
    TamperCheck(tmp_path, "2026-10-01").check("A", scene(), 0.0)
    check = TamperCheck(tmp_path, "2026-10-26")
    assert confirmed(check, scene(offset=60), 1.0) == ""


def test_person_in_front_of_camera_is_not_moved_camera(tmp_path):
    check = TamperCheck(tmp_path)
    check.check("A", scene(), 0.0)
    person = scene()
    cv2.ellipse(person, (300, 200), (130, 220), 0, 0, 360, (40, 50, 60), -1)
    assert confirmed(check, person, 1.0) == ""

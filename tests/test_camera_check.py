import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QWidget

import app as app_module
from camera_check import cameras_problem
from screens.cameras_down import CamerasDownScreen
from screens.scan import payment_allowed
from settings import Settings

APP = QApplication.instance() or QApplication([])


def local_guard(**statuses):
    return SimpleNamespace(state="ready", readers={name: SimpleNamespace(status=status) for name, status in statuses.items()})


def test_problem_when_any_camera_has_no_picture():
    assert cameras_problem(local_guard(A2="uživo", B2="uživo"), True) == ""
    assert "B2 (nema veze)" in cameras_problem(local_guard(A2="uživo", B2="nema veze"), True)
    assert cameras_problem(None, True) == "Kamere nisu pokrenute."
    assert cameras_problem(None, False) == ""


def test_problem_when_camera_server_is_offline_or_reports_dead_camera():
    remote = SimpleNamespace(state="offline", message="Server kamera nije dostupan. Pozovite osoblje.", camera_statuses={})
    assert "Server kamera" in cameras_problem(remote, True)
    remote = SimpleNamespace(state="ready", message="", camera_statuses={"A2": "uživo", "B2": "prekid, ponovo spajam"})
    assert "B2" in cameras_problem(remote, True)


def test_offline_server_locks_payment_unless_admin_allows():
    offline = SimpleNamespace(state="offline", unscanned=0, zone_a_left=0)
    assert not payment_allowed(offline)
    assert payment_allowed(offline, allow_without_cameras=True)


def fake_window(guard, settings, current):
    screens = SimpleNamespace(widget=current)
    screens.currentWidget = lambda: screens.widget
    screens.setCurrentWidget = lambda widget: setattr(screens, "widget", widget)
    window = SimpleNamespace(
        settings=settings, guard=guard, screens=screens, scan=SimpleNamespace(), cameras_down=CamerasDownScreen(),
        welcome=QWidget(), drop=QWidget(), payment=QWidget(), cameras_down_since=None,
    )
    window.close_settings = lambda: screens.setCurrentWidget(window.welcome)
    return window


def test_register_locks_after_grace_and_unlocks_when_cameras_return(monkeypatch):
    guard = local_guard(A2="nema veze")
    settings = Settings(cameras_enabled=True)
    window = fake_window(guard, settings, None)
    window.screens.setCurrentWidget(window.welcome)
    clock = [100.0]
    monkeypatch.setattr(app_module.time, "monotonic", lambda: clock[0])

    app_module.MainWindow.check_cameras(window)
    assert window.screens.currentWidget() is window.welcome
    clock[0] += app_module.CAMERAS_DOWN_SECONDS
    app_module.MainWindow.check_cameras(window)
    assert window.screens.currentWidget() is window.cameras_down
    assert "A2" in window.cameras_down.reason.text()

    guard.readers["A2"].status = "uživo"
    app_module.MainWindow.check_cameras(window)
    assert window.screens.currentWidget() is window.welcome


def test_admin_setting_keeps_register_working(monkeypatch):
    window = fake_window(local_guard(A2="nema veze"), Settings(cameras_enabled=True, allow_without_cameras=True), None)
    window.screens.setCurrentWidget(window.welcome)
    monkeypatch.setattr(app_module, "CAMERAS_DOWN_SECONDS", 0)
    app_module.MainWindow.check_cameras(window)
    assert window.screens.currentWidget() is window.welcome
    assert window.scan.allow_without_cameras is True


def test_problem_when_yolox_cannot_count():
    guard = local_guard(A2="uživo", B2="uživo")
    guard.counter_problem = "Brojač artikala (YOLOX) se nije učitao."
    assert "YOLOX" in cameras_problem(guard, True)

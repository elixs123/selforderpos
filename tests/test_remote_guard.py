import json
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import remote_guard
from remote_guard import RemoteGuard
from vision_api import make_server


class FakeGuard:
    def __init__(self) -> None:
        self.state = "ready"
        self.message = "Spremno"
        self.busy = False
        self.outcome = None
        self.scans = []
        self.approved = 0
        self.reject = False

    def scan(self, barcode, product_code, product_name):
        self.scans.append((barcode, product_code, product_name))
        if self.reject:
            self.state, self.message = "rejected", "Stavite korpu u zonu A."
            self.outcome = SimpleNamespace(number=4, kind="rejected", verdict="zone_a_empty", barcode=barcode, product_code=product_code, message=self.message)
            return False
        self.state, self.message, self.busy = "waiting_take", "Čekam", True
        return True

    def cancel(self):
        self.state, self.busy = "ready", False

    def approve(self):
        self.approved += 1
        self.outcome = SimpleNamespace(number=1, kind="accepted", verdict="staff", barcode="1", product_code=None, message="Osoblje je odobrilo artikal.")


def start_server(guard, token="tajna", port=0):
    server = make_server(guard, token, "127.0.0.1", port)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def wait_for(check, seconds=3.0):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if check():
            return True
        time.sleep(0.01)
    return False


def connect(server, token="tajna"):
    client = RemoteGuard(f"127.0.0.1:{server.server_address[1]}", token)
    client.start()
    return client


def test_state_reaches_client(monkeypatch):
    monkeypatch.setattr(remote_guard, "POLL_SECONDS", 0.02)
    guard = FakeGuard()
    server = start_server(guard)
    client = connect(server)
    try:
        assert wait_for(lambda: client.online and client.state == "ready")
        guard.state = "empty"
        assert wait_for(lambda: client.state == "empty")
    finally:
        client.stop()
        server.shutdown()


def test_scan_passes_product_and_returns_result(monkeypatch):
    monkeypatch.setattr(remote_guard, "POLL_SECONDS", 0.02)
    guard = FakeGuard()
    server = start_server(guard)
    client = connect(server)
    try:
        assert client.scan("3838", "070864", "DONAT") is True
        assert guard.scans == [("3838", "070864", "DONAT")]
        assert client.state == "waiting_take" and client.busy
        guard.reject = True
        guard.busy = False
        assert client.scan("3838", None, None) is False
        assert client.message == "Stavite korpu u zonu A."
        assert client.outcome.kind == "rejected" and client.outcome.number == 4
    finally:
        client.stop()
        server.shutdown()


def test_wrong_token_is_refused(monkeypatch):
    monkeypatch.setattr(remote_guard, "POLL_SECONDS", 0.02)
    server = start_server(FakeGuard())
    client = connect(server, token="pogresna")
    try:
        assert wait_for(lambda: client.state == "offline")
        assert "TOKEN" in client.message
        request = urllib.request.Request(f"http://127.0.0.1:{server.server_address[1]}/state")
        try:
            urllib.request.urlopen(request, timeout=2)
            assert False
        except urllib.error.HTTPError as error:
            assert error.code == 401
    finally:
        client.stop()
        server.shutdown()


def test_server_down_goes_offline_and_staff_can_approve(monkeypatch):
    monkeypatch.setattr(remote_guard, "POLL_SECONDS", 0.02)
    guard = FakeGuard()
    guard.outcome = SimpleNamespace(number=3, kind="accepted", verdict="ok", barcode="1", product_code=None, message="ok")
    server = start_server(guard)
    client = connect(server)
    try:
        assert wait_for(lambda: client.outcome is not None and client.outcome.number == 3)
        server.shutdown()
        server.server_close()
        assert wait_for(lambda: client.state == "offline")
        assert client.busy is False
        assert client.scan("1", None, None) is False
        client.approve()
        assert client.outcome.number == 4 and client.outcome.kind == "accepted" and client.outcome.verdict == "staff"
    finally:
        client.stop()


def test_outcome_numbers_keep_growing_after_server_restart(monkeypatch):
    monkeypatch.setattr(remote_guard, "POLL_SECONDS", 0.02)
    first = FakeGuard()
    first.outcome = SimpleNamespace(number=5, kind="accepted", verdict="ok", barcode="1", product_code=None, message="ok")
    server = start_server(first)
    port = server.server_address[1]
    client = connect(server)
    try:
        assert wait_for(lambda: client.outcome is not None and client.outcome.number == 5)
        server.shutdown()
        server.server_close()
        second = FakeGuard()
        second.outcome = SimpleNamespace(number=1, kind="mismatch", verdict="x", barcode="2", product_code=None, message="ne odgovara")
        server = start_server(second, port=port)
        assert wait_for(lambda: client.outcome.number == 6)
        assert client.outcome.kind == "mismatch"
    finally:
        client.stop()
        server.shutdown()


def test_ping_reports_server_state(monkeypatch):
    server = start_server(FakeGuard())
    try:
        address = f"127.0.0.1:{server.server_address[1]}"
        assert "radi, stanje: ready" in RemoteGuard(address, "tajna").ping()
        assert "TOKEN" in RemoteGuard(address, "pogresna").ping()
    finally:
        server.shutdown()
        server.server_close()
    assert "nije dostupan" in RemoteGuard(address, "tajna").ping()

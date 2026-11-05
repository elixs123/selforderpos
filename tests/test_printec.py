import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

import printec
from printec import APPROVED, DECLINED, FAILED, PENDING, RETRY, UNREACHABLE, PrintecClient, amount_minor

ANSWERS = {}
SEEN = []


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        SEEN.append((self.path, body, self.headers.get("X-Api-Key")))
        status, answer = ANSWERS[body["invoice_id"]]
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(answer).encode())

    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(json.dumps({"status": "ok", "terminal": {"ready": True}}).encode())

    def log_message(self, *args):
        pass


@pytest.fixture(scope="module")
def server():
    httpd = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_port}"
    httpd.shutdown()


def test_amount_minor():
    assert amount_minor(12.5) == 1250
    assert amount_minor(25.369999999) == 2537
    assert amount_minor(0.1 + 0.2) == 30


@pytest.mark.parametrize(
    "status, answer, outcome",
    [
        (200, {"status": "ok", "approval_code": "123", "response_message": "Approved"}, APPROVED),
        (200, {"status": "error", "response_message": "Declined"}, PENDING),
        (200, {}, PENDING),
        (400, {"status": "error", "response_message": "Declined", "is_retryable": True}, DECLINED),
        (504, {"status": "error", "retryable": True}, RETRY),
        (500, {"status": "error", "internal_error": True}, RETRY),
        (409, {"status": "pending_verification"}, PENDING),
        (401, {"status": "error"}, FAILED),
    ],
)
def test_purchase_outcomes(server, status, answer, outcome):
    invoice = f"K1-{status}-{outcome}"
    ANSWERS[invoice] = (status, answer)
    result = PrintecClient(server, "tajna").purchase(invoice, 1250, print_slip=True, copies=2)
    assert result.outcome == outcome
    path, body, key = SEEN[-1]
    assert path == "/api/transaction"
    assert body == {"transaction_type": "purchase", "invoice_id": invoice, "amount": 1250,
                    "print_slip": True, "copies": 2, "include_slip": False}
    assert key == "tajna"


def test_status(server):
    assert PrintecClient(server).status()["terminal"]["ready"] is True


def test_unreachable():
    result = PrintecClient("http://127.0.0.1:1").purchase("K1-x", 100)
    assert result.outcome == UNREACHABLE


@pytest.fixture
def log_lines(tmp_path, monkeypatch):
    monkeypatch.setattr(printec, "log_folder", tmp_path)

    def read():
        files = list(tmp_path.glob("terminal-*.log"))
        return files[0].read_text(encoding="utf-8").splitlines() if files else []

    return read


def test_log_keeps_what_terminal_said(server, log_lines):
    ANSWERS["K1-log-ok"] = (200, {"status": "ok", "approval_code": "A7", "rrn": "123456789012", "card_number": "4111111111111111"})
    ANSWERS["K1-log-no"] = (400, {"status": "error", "response_code": "05", "response_message": "Do not honor"})
    PrintecClient(server).purchase("K1-log-ok", 1250)
    PrintecClient(server).purchase("K1-log-no", 700)
    lines = log_lines()
    assert len(lines) == 4
    assert "ZAHTJEV invoice=K1-log-ok iznos=1250" in lines[0]
    assert "ishod=approved http=200" in lines[1] and '"approval_code": "A7"' in lines[1]
    assert "123456789012" in lines[1] and "4111111111111111" not in lines[1] and "****1111" in lines[1]
    assert "ZAHTJEV invoice=K1-log-no iznos=700" in lines[2]
    assert "ishod=declined http=400" in lines[3] and "Do not honor" in lines[3] and '"response_code": "05"' in lines[3]


def test_log_unreachable(log_lines):
    PrintecClient("http://127.0.0.1:1").purchase("K1-log-x", 100)
    assert "ishod=unreachable http=0" in log_lines()[-1]


def test_log_failure_does_not_stop_payment(server, tmp_path, monkeypatch):
    blocker = tmp_path / "datoteka"
    blocker.write_text("")
    monkeypatch.setattr(printec, "log_folder", blocker)
    ANSWERS["K1-log-ro"] = (200, {"status": "ok"})
    assert PrintecClient(server).purchase("K1-log-ro", 100).outcome == APPROVED

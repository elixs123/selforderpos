import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

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

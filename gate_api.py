import hmac
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from receipts import ReceiptStore

DEFAULT_PORT = 8770
MAX_BODY = 4096


class GateHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args) -> None:
        return

    def _send(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self) -> bool:
        given = self.headers.get("X-Token", "").encode("utf-8")
        return hmac.compare_digest(given, self.server.token.encode("utf-8"))

    def _body(self) -> dict:
        try:
            length = min(int(self.headers.get("Content-Length") or 0), MAX_BODY)
            data = json.loads(self.rfile.read(length)) if length > 0 else {}
        except (ValueError, UnicodeDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    def do_POST(self) -> None:
        if not self._authorized():
            self._send(401, {"error": "token"})
        elif self.path == "/gate/receipt":
            body = self._body()
            fiscal_number = str(body.get("bf") or "")
            try:
                allowed, reason = self.server.store.claim_for_gate(fiscal_number)
            except Exception as error:
                self._send(500, {"error": str(error)})
                return
            print(f"Vrata: BF {fiscal_number or '-'} (IBFM {body.get('ibfm') or '-'}) -> {'otvori' if allowed else 'odbijeno'}: {reason}")
            self._send(200, {"open": allowed, "reason": reason})
        else:
            self._send(404, {"error": "nepoznata adresa"})


class GateServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address: tuple[str, int], store: ReceiptStore, token: str) -> None:
        super().__init__(address, GateHandler)
        self.store = store
        self.token = token


def make_server(store: ReceiptStore, token: str, host: str = "0.0.0.0", port: int = DEFAULT_PORT) -> GateServer:
    if not token:
        raise ValueError("Upišite GATE_API_TOKEN u .env.")
    return GateServer((host, port), store, token)


def start_from_env(store: ReceiptStore) -> GateServer | None:
    """Pokreće servis za vrata ako je GATE_API_TOKEN upisan u .env."""
    token = os.environ.get("GATE_API_TOKEN", "")
    if not token:
        return None
    port = int(os.environ.get("GATE_API_PORT") or DEFAULT_PORT)
    server = make_server(store, token, port=port)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f"Servis za vrata radi na portu {port}.")
    return server

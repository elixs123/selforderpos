import hmac
import json
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DEFAULT_PORT = 8765
MAX_BODY = 4096


def outcome_data(outcome) -> dict | None:
    if outcome is None:
        return None
    return {
        "number": outcome.number, "kind": outcome.kind, "verdict": outcome.verdict,
        "barcode": outcome.barcode, "product_code": outcome.product_code, "message": outcome.message,
    }


def cameras_data(guard) -> dict:
    readers = getattr(guard, "readers", {})
    return {name: {"status": reader.status, "fps": round(reader.fps, 1)} for name, reader in readers.items()}


def snapshot(guard, boot: str) -> dict:
    return {
        "boot": boot, "state": guard.state, "message": guard.message, "busy": bool(guard.busy),
        "outcome": outcome_data(guard.outcome), "cameras": cameras_data(guard),
        "zone_a_ready": bool(getattr(guard, "zone_a_ready", True)),
        "unscanned": int(getattr(guard, "unscanned", 0)),
        "zone_a_left": int(getattr(guard, "zone_a_left", 0)),
        "alert": bool(getattr(guard, "alert", False)),
        "held": str(getattr(guard, "held_message", "")),
        "guess": str(getattr(guard, "unscanned_guess", "")),
        "checking": bool(getattr(guard, "checking", False)),
        "zone_a_reason": guard.zone_a_waiting_reason() if hasattr(guard, "zone_a_waiting_reason") else "-",
    }


class VisionHandler(BaseHTTPRequestHandler):
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

    def do_GET(self) -> None:
        if not self._authorized():
            self._send(401, {"error": "token"})
        elif self.path == "/state":
            self._send(200, snapshot(self.server.guard, self.server.boot))
        else:
            self._send(404, {"error": "nepoznata adresa"})

    def do_POST(self) -> None:
        if not self._authorized():
            self._send(401, {"error": "token"})
            return
        guard = self.server.guard
        try:
            if self.path == "/scan":
                body = self._body()
                barcode = str(body.get("barcode") or "")
                if not barcode:
                    self._send(400, {"error": "nema barkoda"})
                    return
                code, name = body.get("product_code"), body.get("product_name")
                accepted = guard.scan(barcode, str(code) if code else None, str(name) if name else None)
                self._send(200, {**snapshot(guard, self.server.boot), "ok": bool(accepted)})
            elif self.path == "/cancel":
                guard.cancel()
                self._send(200, {**snapshot(guard, self.server.boot), "ok": True})
            elif self.path == "/approve":
                guard.approve(learn=bool(self._body().get("learn")))
                self._send(200, {**snapshot(guard, self.server.boot), "ok": True})
            elif self.path == "/forgive":
                guard.forgive_unscanned()
                self._send(200, {**snapshot(guard, self.server.boot), "ok": True})
            else:
                self._send(404, {"error": "nepoznata adresa"})
        except Exception as error:
            self._send(500, {"error": str(error)})


class VisionServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address: tuple[str, int], guard, token: str) -> None:
        super().__init__(address, VisionHandler)
        self.guard = guard
        self.token = token
        self.boot = uuid.uuid4().hex


def make_server(guard, token: str, host: str = "0.0.0.0", port: int = DEFAULT_PORT) -> VisionServer:
    if not token:
        raise ValueError("Upišite CAM_SERVER_TOKEN u .env.")
    return VisionServer((host, port), guard, token)

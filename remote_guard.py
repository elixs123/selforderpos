import json
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

POLL_SECONDS = 0.15
POLL_TIMEOUT = 1.5
ACTION_TIMEOUT = 8.0
OFFLINE_AFTER = 3


class RemoteError(Exception):
    def __init__(self, message: str, status: int = 0) -> None:
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class Outcome:
    number: int
    kind: str
    verdict: str
    barcode: str
    product_code: str | None
    message: str


def normalize_url(url: str) -> str:
    url = url.strip().rstrip("/")
    return url if url.startswith(("http://", "https://")) else f"http://{url}"


class RemoteGuard:
    remote = True

    def __init__(self, url: str, token: str) -> None:
        self.url = normalize_url(url)
        self.token = token
        self.state = "learning"
        self.message = "Spajam se na server kamera…"
        self.busy = False
        self.unscanned = 0
        self.zone_a_left = 0
        self.alert = False
        self.held_message = ""
        self.checking = False
        self.outcome: Outcome | None = None
        self.online = False
        self.camera_statuses: dict[str, str] = {}
        self.unscanned_guess = ""
        self._boot: str | None = None
        self._offset = 0
        self._number = 0
        self._failures = 0
        self._barcode = ""
        self._product_code: str | None = None
        self._running = False
        self._lock = threading.Lock()

    def start(self) -> None:
        self._running = True
        threading.Thread(target=self._poll, daemon=True).start()

    def stop(self) -> None:
        self._running = False

    def scan(self, barcode: str, product_code: str | None, product_name: str | None) -> bool:
        self._barcode, self._product_code = barcode, product_code
        try:
            data = self._request("POST", "/scan", {"barcode": barcode, "product_code": product_code, "product_name": product_name}, ACTION_TIMEOUT)
        except RemoteError as error:
            self._fail(error, immediately=True)
            return False
        self._apply(data)
        return bool(data.get("ok"))

    def ping(self) -> str:
        try:
            data = self._request("GET", "/state", None, POLL_TIMEOUT * 2)
        except RemoteError as error:
            if error.status == 401:
                return "server odgovara, ali CAM_SERVER_TOKEN nije isti kao na serveru."
            return f"server nije dostupan ({error})."
        cameras = data.get("cameras") or {}
        names = ", ".join(f"{name} {info.get('status')}" for name, info in cameras.items()) or "nema podataka o kamerama"
        zone = "zona A spremna" if data.get("zone_a_ready", True) else f"zona A nije spremna ({data.get('zone_a_reason')})"
        return f"server radi, stanje: {data.get('state')}. Kamere: {names}. {zone}."

    def cancel(self) -> None:
        threading.Thread(target=self._send_quietly, args=("/cancel",), daemon=True).start()

    def approve(self, learn: bool = False) -> None:
        try:
            self._apply(self._request("POST", "/approve", {"learn": learn}, ACTION_TIMEOUT))
        except RemoteError:
            with self._lock:
                self._number += 1
                self._offset += 1
                self.outcome = Outcome(self._number, "accepted", "staff", self._barcode, self._product_code, "Osoblje je odobrilo artikal.")

    def forgive_unscanned(self) -> None:
        try:
            self._apply(self._request("POST", "/forgive", {}, ACTION_TIMEOUT))
        except RemoteError as error:
            self._fail(error)

    def _send_quietly(self, path: str) -> None:
        try:
            self._apply(self._request("POST", path, {}, ACTION_TIMEOUT))
        except RemoteError:
            pass

    def _poll(self) -> None:
        while self._running:
            started = time.monotonic()
            try:
                self._apply(self._request("GET", "/state", None, POLL_TIMEOUT))
            except RemoteError as error:
                self._fail(error)
            time.sleep(max(0.0, POLL_SECONDS - (time.monotonic() - started)))

    def _request(self, method: str, path: str, body: dict | None, timeout: float) -> dict:
        data = None if body is None else json.dumps(body).encode("utf-8")
        request = urllib.request.Request(
            self.url + path, data=data, method=method,
            headers={"X-Token": self.token, "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            raise RemoteError(str(error), error.code) from error
        except (urllib.error.URLError, OSError, ValueError) as error:
            raise RemoteError(str(error)) from error

    def _apply(self, data: dict) -> None:
        with self._lock:
            boot = data.get("boot")
            if self._boot is not None and boot != self._boot:
                self._offset = self._number
            self._boot = boot
            self.state = str(data.get("state", "ready"))
            self.message = str(data.get("message", ""))
            self.busy = bool(data.get("busy"))
            self.unscanned = int(data.get("unscanned") or 0)
            self.zone_a_left = int(data.get("zone_a_left") or 0)
            self.alert = bool(data.get("alert"))
            self.held_message = str(data.get("held") or "")
            self.checking = bool(data.get("checking"))
            self.unscanned_guess = str(data.get("guess") or "")
            if "cameras" in data:
                self.camera_statuses = {str(name): str((info or {}).get("status", "")) for name, info in (data.get("cameras") or {}).items()}
            raw = data.get("outcome")
            if raw:
                total = self._offset + int(raw["number"])
                if total > self._number:
                    self._number = total
                    self.outcome = Outcome(
                        total, str(raw["kind"]), str(raw["verdict"]), str(raw["barcode"]),
                        raw.get("product_code"), str(raw["message"]),
                    )
            self._failures = 0
            self.online = True

    def _fail(self, error: RemoteError, immediately: bool = False) -> None:
        with self._lock:
            self._failures = OFFLINE_AFTER if immediately else self._failures + 1
            if self._failures < OFFLINE_AFTER:
                return
            self.online = False
            self.busy = False
            self.unscanned = 0
            self.zone_a_left = 0
            self.alert = False
            self.held_message = ""
            self.checking = False
            self.state = "offline"
            self.message = "Pogrešan CAM_SERVER_TOKEN." if error.status == 401 else "Server kamera nije dostupan. Pozovite osoblje."

import http.client
import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

APPROVED = "approved"
DECLINED = "declined"
RETRY = "retry"
PENDING = "pending"
UNREACHABLE = "unreachable"
FAILED = "failed"

PAYMENT_TIMEOUT = 160
STATUS_TIMEOUT = 5

CARD_NUMBER = re.compile(r"\d{9,15}(\d{4})(?!\d)")

log_folder: Path | None = None


def use_log_folder(folder: Path) -> None:
    global log_folder
    log_folder = folder


def log_event(text: str) -> None:
    """Zapis plaćanja u logs/terminal-GGGGMMDD.log; uvijek uključen, greška pri upisu ne smije zaustaviti naplatu."""
    if log_folder is None:
        return
    moment = datetime.now()
    try:
        log_folder.mkdir(parents=True, exist_ok=True)
        with open(log_folder / f"terminal-{moment:%Y%m%d}.log", "a", encoding="utf-8") as file:
            file.write(f"{moment:%H:%M:%S.%f}"[:-3] + f" {text}\n")
    except OSError:
        pass


def _masked(data: dict) -> str:
    """Odgovor terminala kako je stigao; broj kartice bi u logu ostao samo sa zadnje 4 cifre."""
    return CARD_NUMBER.sub(r"****\1", json.dumps(data, ensure_ascii=False))


@dataclass(frozen=True)
class PaymentResult:
    outcome: str
    http_status: int
    message: str
    data: dict = field(default_factory=dict)


class TerminalUnreachable(Exception):
    pass


class TerminalLost(TerminalUnreachable):
    """Zahtjev je poslan, a odgovor nije stigao: terminal je možda naplatio."""


class TerminalTimeout(Exception):
    pass


def amount_minor(total: float) -> int:
    return int(round(total * 100))


class PrintecClient:
    def __init__(self, base_url: str, api_key: str = "") -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    def _request(self, method: str, path: str, body: dict | None, timeout: float) -> tuple[int, dict]:
        data = None if body is None else json.dumps(body).encode()
        request = urllib.request.Request(self.base_url + path, data=data, method=method)
        request.add_header("Content-Type", "application/json")
        if self.api_key:
            request.add_header("X-Api-Key", self.api_key)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.status, self._parse(response.read())
        except urllib.error.HTTPError as error:
            return error.code, self._parse(error.read())
        except TimeoutError as error:
            raise TerminalTimeout(str(error)) from error
        except urllib.error.URLError as error:
            if isinstance(error.reason, TimeoutError):
                raise TerminalTimeout(str(error.reason)) from error
            raise TerminalUnreachable(str(error.reason)) from error
        except (ConnectionError, http.client.HTTPException) as error:
            raise TerminalLost(str(error) or type(error).__name__) from error

    def _parse(self, raw: bytes) -> dict:
        try:
            value = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            return {"raw": raw.decode(errors="replace")[:2000]}
        return value if isinstance(value, dict) else {"raw": value}

    def purchase(self, invoice_id: str, amount: int, print_slip: bool = False, copies: int = 1) -> PaymentResult:
        body = {"transaction_type": "purchase", "invoice_id": invoice_id, "amount": amount}
        if print_slip:
            body["print_slip"] = True
            body["copies"] = copies
            body["include_slip"] = False
        log_event(f"ZAHTJEV invoice={invoice_id} iznos={amount}")
        result = self._purchase(body)
        log_event(f"ODGOVOR invoice={invoice_id} iznos={amount} ishod={result.outcome} http={result.http_status} "
                  f"poruka={result.message!r} podaci={_masked(result.data)}")
        return result

    def _purchase(self, body: dict) -> PaymentResult:
        try:
            status, data = self._request("POST", "/api/transaction", body, PAYMENT_TIMEOUT)
        except TerminalLost as error:
            # Kupac je možda naplaćen: nema "ništa nije naplaćeno" ni ponovne naplate dok osoblje ne provjeri terminal.
            return PaymentResult(PENDING, 0, f"Veza sa terminalom je prekinuta poslije slanja: {error}")
        except TerminalUnreachable as error:
            return PaymentResult(UNREACHABLE, 0, f"Servis terminala nije dostupan: {error}")
        except TerminalTimeout:
            return PaymentResult(RETRY, 0, "Terminal nije odgovorio na vrijeme.")
        message = str(data.get("response_message", ""))
        if status == 200 and data.get("status") == "ok":
            return PaymentResult(APPROVED, status, message, data)
        if status == 200:
            # Nejasan odgovor nije odobrenje: nema računa, a ni ponovne naplate dok osoblje ne provjeri terminal.
            return PaymentResult(PENDING, status, message, data)
        if status == 400:
            return PaymentResult(DECLINED, status, message, data)
        if status == 409 and data.get("status") == "pending_verification":
            return PaymentResult(PENDING, status, message, data)
        if status in (401, 404):
            return PaymentResult(FAILED, status, message or "Pogrešne postavke terminala.", data)
        return PaymentResult(RETRY, status, message, data)

    def status(self) -> dict:
        _, data = self._request("GET", "/api/status", None, STATUS_TIMEOUT)
        return data

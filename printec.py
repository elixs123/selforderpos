import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field

APPROVED = "approved"
DECLINED = "declined"
RETRY = "retry"
PENDING = "pending"
UNREACHABLE = "unreachable"
FAILED = "failed"

PAYMENT_TIMEOUT = 160
STATUS_TIMEOUT = 5


@dataclass(frozen=True)
class PaymentResult:
    outcome: str
    http_status: int
    message: str
    data: dict = field(default_factory=dict)


class TerminalUnreachable(Exception):
    pass


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
        except ConnectionError as error:
            raise TerminalUnreachable(str(error)) from error

    def _parse(self, raw: bytes) -> dict:
        try:
            value = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            return {}
        return value if isinstance(value, dict) else {}

    def purchase(self, invoice_id: str, amount: int, print_slip: bool = False, copies: int = 1) -> PaymentResult:
        body = {"transaction_type": "purchase", "invoice_id": invoice_id, "amount": amount}
        if print_slip:
            body["print_slip"] = True
            body["copies"] = copies
            body["include_slip"] = False
        try:
            status, data = self._request("POST", "/api/transaction", body, PAYMENT_TIMEOUT)
        except TerminalUnreachable as error:
            return PaymentResult(UNREACHABLE, 0, f"Servis terminala nije dostupan: {error}")
        except TerminalTimeout:
            return PaymentResult(RETRY, 0, "Terminal nije odgovorio na vrijeme.")
        message = data.get("response_message", "")
        if status == 200:
            return PaymentResult(APPROVED, status, message, data)
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

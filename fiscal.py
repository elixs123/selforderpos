import re
import urllib.error
import urllib.request
import xml.etree.ElementTree as ElementTree
from dataclasses import dataclass

PRINT_PATH = "/stampatifiskalniracun"
PRINT_TIMEOUT = 30
NAME_LIMIT = 32
FISCAL_NUMBER = re.compile(r"<Naziv>\s*BrojFiskalnogRacuna\s*</Naziv>.*?<Vrijednost[^>]*>\s*([^<]*?)\s*</Vrijednost>", re.DOTALL)


@dataclass(frozen=True)
class FiscalOptions:
    unit: str = "ko"
    tax_label: str = "E"
    card_payment: str = "Kartica"
    qr_payment: str = "Virman"


def _text(parent: ElementTree.Element, tag: str, value) -> ElementTree.Element:
    element = ElementTree.SubElement(parent, tag)
    element.text = str(value)
    return element


def _number(value: float) -> str:
    return f"{value:.2f}"


def build_request(receipt_number: int, cart: dict, payment_method: str, options: FiscalOptions) -> bytes:
    root = ElementTree.Element("RacunZahtjev", {
        "xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
        "xmlns:xsd": "http://www.w3.org/2001/XMLSchema",
    })
    _text(root, "VrstaZahtjeva", 0)
    receipt = ElementTree.SubElement(root, "NoviObjekat")
    items = ElementTree.SubElement(receipt, "StavkeRacuna")
    for item in cart["items"]:
        line = ElementTree.SubElement(items, "RacunStavka")
        article = ElementTree.SubElement(line, "artikal")
        _text(article, "Sifra", item["code"])
        _text(article, "Naziv", item["name"][:NAME_LIMIT])
        _text(article, "JM", options.unit)
        _text(article, "Cijena", _number(item["price"]))
        _text(article, "Stopa", options.tax_label)
        _text(article, "Grupa", 0)
        _text(article, "PLU", 0)
        _text(line, "Kolicina", item["quantity"])
        _text(line, "Rabat", 0)
    payments = ElementTree.SubElement(receipt, "VrstePlacanja")
    payment = ElementTree.SubElement(payments, "VrstaPlacanja")
    _text(payment, "Oznaka", options.card_payment if payment_method == "card" else options.qr_payment)
    _text(payment, "Iznos", _number(cart["total"]))
    _text(receipt, "BrojRacuna", receipt_number)
    return b'<?xml version="1.0" encoding="utf-8"?>\n' + ElementTree.tostring(root, encoding="utf-8")


def parse_fiscal_number(response: str) -> str:
    """Broj fiskalnog računa (BF) iz Tring odgovora: <Naziv>BrojFiskalnogRacuna</Naziv> ... <Vrijednost>84366</Vrijednost>."""
    match = FISCAL_NUMBER.search(response)
    return match.group(1) if match else ""


@dataclass(frozen=True)
class FiscalResult:
    ok: bool
    message: str
    fiscal_number: str = ""


class FiscalPrinter:
    def __init__(self, base_url: str, options: FiscalOptions | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.options = options or FiscalOptions()

    def print_receipt(self, receipt_number: int, cart: dict, payment_method: str) -> FiscalResult:
        body = build_request(receipt_number, cart, payment_method, self.options)
        request = urllib.request.Request(self.base_url + PRINT_PATH, data=body, method="POST")
        request.add_header("Content-Type", "application/xml; charset=utf-8")
        try:
            with urllib.request.urlopen(request, timeout=PRINT_TIMEOUT) as response:
                text = response.read().decode(errors="replace")
                return FiscalResult(True, text, parse_fiscal_number(text))
        except urllib.error.HTTPError as error:
            return FiscalResult(False, f"Printer je odbio račun ({error.code}): {error.read().decode(errors='replace')}")
        except (urllib.error.URLError, TimeoutError, ConnectionError) as error:
            return FiscalResult(False, f"Fiskalni printer nije dostupan: {error}")

    def reachable(self) -> FiscalResult:
        try:
            with urllib.request.urlopen(self.base_url, timeout=5) as response:
                return FiscalResult(True, f"Printer servis odgovara ({response.status}).")
        except urllib.error.HTTPError as error:
            return FiscalResult(True, f"Printer servis odgovara ({error.code}).")
        except (urllib.error.URLError, TimeoutError, ConnectionError) as error:
            return FiscalResult(False, f"Fiskalni printer nije dostupan: {error}")

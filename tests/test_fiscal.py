import threading
import xml.etree.ElementTree as ElementTree
from http.server import BaseHTTPRequestHandler, HTTPServer

from cart import Cart
from catalog import Product
from fiscal import FiscalOptions, FiscalPrinter, build_request

RECEIVED = []


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        RECEIVED.append((self.path, self.headers["Content-Type"], self.rfile.read(int(self.headers["Content-Length"]))))
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

    def log_message(self, *args):
        pass


def sample_cart() -> dict:
    cart = Cart()
    cart.add(Product("078456", "1", "Čokolada mliječna Milka 100 g extra dugi naziv", 0.54), 2)
    cart.add(Product("000008", "2", "SAKSIJA 06025", 0.91))
    return cart.to_dict()


def test_request_matches_tring_format():
    xml = build_request(238000, sample_cart(), "card", FiscalOptions())
    assert xml.startswith(b'<?xml version="1.0" encoding="utf-8"?>')
    root = ElementTree.fromstring(xml)
    assert root.tag == "RacunZahtjev"
    assert root.findtext("VrstaZahtjeva") == "0"
    lines = root.findall("NoviObjekat/StavkeRacuna/RacunStavka")
    assert len(lines) == 2
    article = lines[0].find("artikal")
    assert article.findtext("Sifra") == "078456"
    assert len(article.findtext("Naziv")) == 32
    assert article.findtext("Naziv").startswith("Čokolada")
    assert article.findtext("JM") == "ko"
    assert article.findtext("Cijena") == "0.54"
    assert article.findtext("Stopa") == "E"
    assert lines[0].findtext("Kolicina") == "2"
    assert lines[0].findtext("Rabat") == "0"
    assert root.findtext("NoviObjekat/VrstePlacanja/VrstaPlacanja/Oznaka") == "Kartica"
    assert root.findtext("NoviObjekat/VrstePlacanja/VrstaPlacanja/Iznos") == "1.99"
    assert root.findtext("NoviObjekat/BrojRacuna") == "238000"


def test_qr_uses_qr_payment_label():
    root = ElementTree.fromstring(build_request(1, sample_cart(), "qr", FiscalOptions(qr_payment="Ostalo")))
    assert root.findtext("NoviObjekat/VrstePlacanja/VrstaPlacanja/Oznaka") == "Ostalo"


def test_print_posts_xml_to_tring_route():
    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    result = FiscalPrinter(f"http://127.0.0.1:{server.server_port}").print_receipt(5, sample_cart(), "card")
    server.shutdown()
    assert result.ok
    path, content_type, body = RECEIVED[-1]
    assert path == "/stampatifiskalniracun"
    assert content_type.startswith("application/xml")
    assert b"<RacunZahtjev" in body


def test_print_reports_unreachable_printer():
    result = FiscalPrinter("http://127.0.0.1:1").print_receipt(5, sample_cart(), "card")
    assert not result.ok

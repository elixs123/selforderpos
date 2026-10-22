import json
import threading
import urllib.error
import urllib.request

from cart import Cart
from catalog import Product
from gate_api import make_server
from receipts import ReceiptStore

TOKEN = "tajna"


def started_server(tmp_path):
    store = ReceiptStore(tmp_path / "kasa.db")
    cart = Cart()
    cart.add(Product("A1", "1001", "Mlijeko 1 l", 1.79))
    number = store.save(cart, "card")
    store.mark_fiscal(number, True, "", "84366")
    server = make_server(store, TOKEN, "127.0.0.1", 0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def post(server, body: dict, token: str = TOKEN) -> tuple[int, dict]:
    request = urllib.request.Request(
        f"http://127.0.0.1:{server.server_port}/gate/receipt", data=json.dumps(body).encode(), method="POST"
    )
    request.add_header("Content-Type", "application/json")
    request.add_header("X-Token", token)
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read())


def test_known_receipt_opens_gate(tmp_path):
    server = started_server(tmp_path)
    try:
        assert post(server, {"bf": "084366", "ibfm": "AM040250"}) == (200, {"open": True, "reason": "račun pronađen"})
        status, data = post(server, {"bf": "999"})
        assert status == 200
        assert data["open"] is False
    finally:
        server.shutdown()


def test_wrong_token_is_refused(tmp_path):
    server = started_server(tmp_path)
    try:
        assert post(server, {"bf": "084366"}, token="krivo")[0] == 401
    finally:
        server.shutdown()

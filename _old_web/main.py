"""Pokretač kase: server u pozadini + prozor koji prikazuje ekrane.

Pokretanje:  python main.py
"""
import socket
import threading
import time

import uvicorn
import webview

from server import HOST, PORT, app


def pokreni_server() -> None:
    uvicorn.run(app, host=HOST, port=PORT, log_level="warning")


def cekaj_server(timeout: float = 10.0) -> None:
    """Sačekaj da server počne slušati, da prozor ne otvori praznu stranicu."""
    kraj = time.time() + timeout
    while time.time() < kraj:
        with socket.socket() as s:
            if s.connect_ex((HOST, PORT)) == 0:
                return
        time.sleep(0.1)
    raise RuntimeError("Server se nije pokrenuo")


def main() -> None:
    # daemon=True: kad se prozor zatvori, server se ugasi sa njim
    threading.Thread(target=pokreni_server, daemon=True).start()
    cekaj_server()
    webview.create_window(
        "Penny samouslužna kasa",
        f"http://{HOST}:{PORT}/",
        width=820,
        height=1360,
    )
    webview.start()


if __name__ == "__main__":
    main()

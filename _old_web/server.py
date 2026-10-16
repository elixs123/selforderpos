"""Server kase (FastAPI): ekrani pozivaju ove adrese, a Python računa.

API = application programming interface / aplikacijski programski interfejs.
Ovdje je to skup adresa (/api/...) preko kojih ekran razgovara sa Pythonom.

Za razvoj u browseru pokreni samo server:   python server.py
pa otvori http://127.0.0.1:8765
(Prozor kase pokreće main.py.)
"""
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from katalog import nadji_po_barkodu
from korpa import Korpa

HOST, PORT = "127.0.0.1", 8765
UI_FOLDER = Path(__file__).parent / "ui"

app = FastAPI(title="Penny samouslužna kasa")

# Jedna kasa = jedna korpa. Kasnije će ovo postati "narudžba" u bazi.
korpa = Korpa()


class Skeniranje(BaseModel):
    barkod: str


class Promjena(BaseModel):
    razlika: int  # +1 ili -1


@app.get("/api/korpa")
def citaj_korpu() -> dict:
    return korpa.kao_rjecnik()


@app.post("/api/skeniraj")
def skeniraj(zahtjev: Skeniranje) -> dict:
    artikal = nadji_po_barkodu(zahtjev.barkod.strip())
    if artikal is None:
        raise HTTPException(status_code=404, detail="Artikal nije pronađen")
    korpa.dodaj(artikal)
    odgovor = korpa.kao_rjecnik()
    odgovor["zadnji"] = artikal.naziv
    return odgovor


@app.post("/api/korpa/{sifra}/promjena")
def promijeni(sifra: str, zahtjev: Promjena) -> dict:
    korpa.promijeni_kolicinu(sifra, zahtjev.razlika)
    return korpa.kao_rjecnik()


@app.post("/api/korpa/isprazni")
def isprazni() -> dict:
    korpa.isprazni()
    return korpa.kao_rjecnik()


# MORA biti zadnje: servira ekrane iz foldera ui/ (index.html = dobrodošlica).
app.mount("/", StaticFiles(directory=UI_FOLDER, html=True), name="ui")


if __name__ == "__main__":
    uvicorn.run(app, host=HOST, port=PORT)

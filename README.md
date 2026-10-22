# Penny samouslužna kasa

Desktop aplikacija u Pythonu (PySide6 / Qt).

## Postavljanje (jednom)

```bash
cd ~/Desktop/PYTHON/selforderpos
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Baza (MSSQL)

1. Instaliraj Microsoft ODBC Driver 18 for SQL Server (Mac: Homebrew paket `msodbcsql18`, Windows: instalacija sa Microsoftove stranice).
2. `pip install -r requirements.txt`
3. Kopiraj `.env.example` u `.env` i upiši postavke baze (`.env` nikad ne ide u git).
4. `python check_db.py` provjerava vezu.
5. `python find_columns.py barcode` traži tabele i kolone po dijelu naziva.

## Pokretanje

```bash
python app.py
```

Prozor je zasad umanjen na 60%. Na pravoj kasi: `KASA_SCALE=1.0 python app.py`.

## Testovi

```bash
python -m pytest -v
```

## Struktura

| Fajl | Šta radi |
|---|---|
| `app.py` | glavni prozor |
| `screens/` | po jedan fajl za svaki ekran |
| `styles.py` | boje, skala i ikone |
| `catalog.py` | artikli i cijene (u feninzima) |
| `cart.py` | računanje korpe |
| `database.py` | veza sa MSSQL bazom (postavke iz `.env`) |
| `gate_api.py` | servis za vrata: provjerava BF s računa |
| `check_db.py` | provjera veze sa bazom |
| `find_columns.py` | traženje tabela i kolona u bazi |
| `tests/` | testovi za korpu i katalog |
| `cameras/` | servis za kamere (kasnije) |
| `_old_web/` | stara web verzija, više se ne koristi |


## Vrata (QR kod s računa)

Kad fiskalni printer odštampa račun, kasa sprema broj fiskalnog računa (BF) u `kasa.db`.
Vrata (Odroid, program `qrgate`) skeniraju QR s računa i pitaju kasu postoji li taj BF:
račun otvara vrata samo jednom (ponovni sken u roku od 2 minute se još prihvata).

1. U `.env` na kasi upiši `GATE_API_TOKEN` (i po želji `GATE_API_PORT`, zadano 8770).
2. Port 8770 mora biti dozvoljen u firewallu kase.
3. Na Odroidu u `/home/odroid/qrgate/qrgate.json` upiši `kasa_url` (`http://<IP kase>:8770`) i isti token kao `kasa_token`.

## Kamere na drugom računaru

Laptop (ili server) radi kamere i AI, kasa samo pita:

1. U `.env` na oba računara isti `CAM_SERVER_TOKEN`. Na kasi još `CAM_SERVER_URL=http://10.20.99.50:8765` (ili adresa u postavkama).
2. Na laptopu: `python vision_server.py --monitor` (prozor dijagnostike), bez prozora: `python vision_server.py`. `--debug` sprema slike.
3. Zone se crtaju i reference uče na laptopu (tamo su `cameras/zones.json` i `data/samples`).
4. Laptop ne smije spavati (`caffeinate -i python vision_server.py`), a port 8765 mora biti dozvoljen u firewallu.

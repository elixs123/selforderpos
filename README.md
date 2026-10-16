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
| `check_db.py` | provjera veze sa bazom |
| `find_columns.py` | traženje tabela i kolona u bazi |
| `tests/` | testovi za korpu i katalog |
| `cameras/` | servis za kamere (kasnije) |
| `_old_web/` | stara web verzija, više se ne koristi |

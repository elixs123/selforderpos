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

### Server kamera sa NVIDIA grafičkom (npr. RTX 5060)

YOLOX (brojanje), model prepoznavanja (CLIP) i čitanje etikete (RapidOCR) tada rade na grafičkoj umjesto na procesoru.
Ruka (MediaPipe) ostaje na procesoru, mala je i brza.

1. Najnoviji NVIDIA drajver. RTX 50xx traži CUDA 12.8 ili noviju, pa uzeti najnoviji `onnxruntime-gpu`.
2. `./install_server.sh`: napravi `.venv`, instalira `requirements.txt` i obični onnxruntime zamijeni GPU verzijom
   (isti modul, ne smiju oba; `rapidocr-onnxruntime` uvijek povuče obični, pa ga skripta skloni). CUDA i cuDNN dođu
   kao pip paketi. Na kraju provjeri da je `CUDAExecutionProvider` dostupan. Pokretati i poslije svake promjene paketa.
3. Pri pokretanju u logu mora pisati `YOLOX se izvršava na: CUDAExecutionProvider, ...`. Ako piše samo
   `CPUExecutionProvider`, CUDA nije učitana. Isto za `Model prepoznavanja` i `Čitanje etikete (Det/Cls/Rec)`.
   Provjera bez pokretanja kase: `python -c "import onnxruntime as o; o.preload_dlls(); print(o.get_available_providers())"`
   mora ispisati `CUDAExecutionProvider`.
4. `.env`: `CAM_GPU=0` vraća sve na procesor. `CAM_TENSORRT=1` uključuje TensorRT (još brže, FP16), ali traži
   instaliran TensorRT, a prvo pokretanje traje par minuta dok se modeli pripreme (spremaju se u `cameras/models/tensorrt`).
   Čitanje etikete ide uvijek bez TensorRT (slike su svaka druge veličine).
5. `sudo apt install ffmpeg`: snimci alarma se pretvaraju u H.264 (OpenCV na Linuxu ga nema), inače se na Macu vide zeleno.
6. `.env` se ne kopira sa Maca: tamo je `CAM_GPU=0`, a na serveru to mora biti izbrisano (ili `CAM_GPU=1`).

### Arhiva izgleda artikla

Server kamera za svaki prodani artikal čuva do 50 najboljih i najrazličitijih slika (sve strane, sve kamere) u
`data/samples/archive` (`archive.db` + folder po šifri artikla). To su podaci za kasnije dotreniranje modela
prepoznavanja. `.env`: `CAM_ARCHIVE=ne` gasi, `CAM_ARCHIVE_PER_ARTICLE` (zadano 50), `CAM_ARCHIVE_GB` (zadano 50).

## Fiskalni printer (Tring)

`python check_fiscal.py` provjerava odgovara li servis (`localhost:8085`) i ispisuje XML koji bi se poslao.
`python check_fiscal.py --print` šalje pravi fiskalni račun od 0.10 KM. Radi samo na računaru na kojem je printer.
Zahtjev ide na `/stampatifiskalniracun`, a oblik prati Tring primjer (vidi `fiscal.py`, `build_request`).

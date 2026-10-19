# Kamere – samouslužna kasa

## Postavljanje (jednom)

Koristi isti `.venv` kao kasa:

```
source .venv/bin/activate
pip install -r requirements.txt
```

## Postavke u .env (nikad u kodu)

```
CAM_USER=korisnik_za_gledanje
CAM_PASSWORD=lozinka
CAM_A_HOST=10.20.99.90
CAM_B_HOST=10.20.99.87
CAM_CHANNEL=102
CAM_MODEL=dinov2
```

- Kamera A gleda zonu A (korpa ili artikli), kamera B zonu B (odlaganje).
- `CAM_COUNTER=yolox` broji artikle modelom YOLOX-s (Apache 2.0, preuzme se sam u cameras/models) na kamerama iz `CAM_COUNT_CAMERAS` (zadano A2,B2, kamere sa strane). `CAM_COUNTER=off` ga isključuje.
- `102` = pomoćni tok, laganiji. `CAM_MODEL` = `dinov2`, `dinov2-base`, `clip` ili `mobilenet` (veći modeli se sami preuzmu pri prvom pokretanju; uporedi ih s `python cameras/benchmark_models.py`).

## Pokretanje

```
cd cameras
python zone_setup.py A
python zone_setup.py B
python monitor.py
```

Pri pokretanju monitora zona A mora biti prazna. Izlaz: ESC.

## Fajlovi

- `config.py` – postavke kamera iz .env
- `reader.py` – čitanje kamere u posebnoj niti
- `zones.py`, `zone_setup.py` – zone A i B
- `watcher.py` – otkrivanje uzimanja (A) i odlaganja (B)
- `hands.py` – prepoznavanje ruku (MediaPipe)
- `embedder.py`, `similarity.py` – AI poređenje artikala
- `samples.py` – spremanje slika i referenci (data/samples)
- `monitor.py` – testna aplikacija koja sve spaja

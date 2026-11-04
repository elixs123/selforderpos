import base64
import html
from datetime import date, datetime, timedelta

# Ishodi po artiklu (kind:verdict iz CheckoutGuard._finish, i "mismatch").
ZONE_A = {
    "rejected:not_taken": "kamera nije vidjela da je uzet iz zone A",
    "rejected:multiple_taken": "uzeto više artikala iz zone A",
}
ZONE_B = {
    "mismatch": "odbijen u zoni B (ne liči na skenirani)",
    "accepted:staff": "osoblje ga moralo odobriti",
    "timeout:timeout": "nije odložen u zonu B na vrijeme",
}
GOOD = ("accepted:ok", "accepted:learned", "accepted:verified")
# Ispod ovoliko slika u arhivi artikal treba uslikati sa svih strana (Postavke > Snimanje artikla).
FEW_ARCHIVE_IMAGES = 10


def problem_articles(store, archive, days: int = 7, today: date | None = None) -> list[dict]:
    """Artikli sa bar jednim problemom u zadnjih days dana, najgori prvi."""
    since = ((today or date.today()) - timedelta(days=days - 1)).isoformat()
    counts = {item["code"]: item["count"] for item in archive.products()} if archive is not None else {}
    rows = []
    for entry in store.product_events_since(since).values():
        kinds = entry["kinds"]
        zone_a = {name: kinds[key] for key, name in ZONE_A.items() if kinds.get(key)}
        zone_b = {name: kinds[key] for key, name in ZONE_B.items() if kinds.get(key)}
        problems = sum(zone_a.values()) + sum(zone_b.values())
        if not problems:
            continue
        good = sum(kinds.get(key, 0) for key in GOOD)
        rows.append({**entry, "zone_a": zone_a, "zone_b": zone_b, "problems": problems, "good": good,
                     "share": problems / (problems + good), "archive": counts.get(entry["code"], 0)})
    return sorted(rows, key=lambda row: (row["problems"], row["share"]), reverse=True)


def advice(row: dict) -> str:
    tips = []
    if row["archive"] < FEW_ARCHIVE_IMAGES:
        tips.append(f"uslikati sa svih strana (u arhivi {row['archive']} slika)")
    if row["zone_b"]:
        tips.append("provjeriti slike za prepoznavanje (pogrešne obrisati)")
    if row["zone_a"] and not row["zone_b"]:
        tips.append("provjeriti kameru zone A (artikal se slabo vidi kad se uzima)")
    return "; ".join(tips)


def _picture(store, archive, code: str) -> str:
    data = archive.best_image(code) if archive is not None else None
    if data is None:
        for path in store.reference_paths(code, limit=1):
            try:
                data = (store.folder / path).read_bytes()
            except OSError:
                data = None
    if data is None:
        return '<div class="none">nema slike</div>'
    return f'<img src="data:image/jpeg;base64,{base64.b64encode(data).decode("ascii")}">'


def _reasons(reasons: dict[str, int]) -> str:
    return "<br>".join(f"{count}× {html.escape(name)}" for name, count in reasons.items()) or "–"


def report_html(store, archive, days: int = 7, today: date | None = None) -> str:
    today = today or date.today()
    rows = problem_articles(store, archive, days, today)
    first = today - timedelta(days=days - 1)
    body = "".join(
        f"<tr><td>{_picture(store, archive, row['code'])}</td>"
        f"<td><b>{html.escape(row['name'])}</b><br>šifra {html.escape(row['code'])}"
        f"{'<br>barkod ' + html.escape(row['barcode']) if row['barcode'] else ''}</td>"
        f"<td>{_reasons(row['zone_a'])}</td><td>{_reasons(row['zone_b'])}</td>"
        f"<td>{row['good']}</td><td><b>{row['share']:.0%}</b></td><td>{html.escape(advice(row))}</td></tr>"
        for row in rows
    )
    if not rows:
        body = '<tr><td colspan="7">U ovom periodu nema artikala sa problemima.</td></tr>'
    return f"""<!doctype html>
<html lang="bs"><head><meta charset="utf-8"><title>Problematični artikli {first:%d.%m.}–{today:%d.%m.%Y.}</title>
<style>
body {{ font-family: -apple-system, "Segoe UI", Arial, sans-serif; margin: 24px; color: #222; }}
h1 {{ margin: 0 0 4px; }} p {{ color: #666; margin: 0 0 16px; }}
table {{ border-collapse: collapse; width: 100%; }}
th, td {{ border-bottom: 1px solid #ddd; padding: 8px; text-align: left; vertical-align: top; font-size: 14px; }}
th {{ background: #f3f3f3; }}
img {{ max-width: 140px; max-height: 140px; border-radius: 6px; }}
.none {{ width: 140px; color: #999; }}
tr {{ page-break-inside: avoid; }}
</style></head><body>
<h1>Problematični artikli</h1>
<p>Samouslužna kasa, {first:%d.%m.}–{today:%d.%m.%Y.} ({days} dana). Artikli koje kamere teško prepoznaju, najgori prvi.
Te artikle uslikati na kasi: Postavke &gt; Snimanje artikla. Napravljeno {datetime.now():%d.%m.%Y. %H:%M}.</p>
<table><tr><th>Slika</th><th>Artikal</th><th>Zona A</th><th>Zona B</th><th>Prošao dobro</th><th>Problemi</th><th>Šta uraditi</th></tr>
{body}
</table></body></html>"""

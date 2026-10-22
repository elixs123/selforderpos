"""Provjera fiskalnog printera (Tring) bez aplikacije.

python check_fiscal.py            provjera da servis odgovara + prikaz XML-a koji bi se poslao
python check_fiscal.py --print    šalje PRAVI fiskalni račun (1 artikal, 0.10 KM), pita za potvrdu
Opcije: --url http://localhost:8085  --payment card|qr  --tax E  --unit ko  --yes
"""
import argparse
import sys
import urllib.error
import urllib.request

from fiscal import PRINT_PATH, FiscalOptions, FiscalPrinter, build_request

CART = {"items": [{"code": "TEST", "name": "Test artikal", "price": 0.10, "quantity": 1}], "total": 0.10}


def raw_post(url: str, body: bytes) -> None:
    """Isti zahtjev kao aplikacija, ali ispiše sve što printer vrati (status, zaglavlja, tijelo)."""
    request = urllib.request.Request(url + PRINT_PATH, data=body, method="POST")
    request.add_header("Content-Type", "application/xml; charset=utf-8")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            print(f"Status: {response.status}")
            print(f"Zaglavlja: {dict(response.headers)}")
            print("Odgovor:\n" + response.read().decode(errors="replace"))
    except urllib.error.HTTPError as error:
        print(f"HTTP greška {error.code}:\n" + error.read().decode(errors="replace"))
    except Exception as error:
        print(f"Zahtjev nije uspio: {error!r}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Provjera fiskalnog printera")
    parser.add_argument("--url", default="http://localhost:8085")
    parser.add_argument("--payment", choices=("card", "qr"), default="card")
    parser.add_argument("--tax", default="E")
    parser.add_argument("--unit", default="ko")
    parser.add_argument("--print", action="store_true", dest="send")
    parser.add_argument("--yes", action="store_true")
    args = parser.parse_args()

    options = FiscalOptions(unit=args.unit, tax_label=args.tax)
    printer = FiscalPrinter(args.url, options)

    print(f"1) Provjera servisa na {args.url}")
    reach = printer.reachable()
    print(("OK: " if reach.ok else "NE RADI: ") + reach.message)

    body = build_request(999999, CART, args.payment, options)
    print("\n2) XML koji se šalje na " + args.url + PRINT_PATH)
    print(body.decode("utf-8"))

    if not args.send:
        print("\nNije poslano. Za slanje pravog računa: python check_fiscal.py --print")
        return 0 if reach.ok else 1
    if not args.yes and input("\nOvo štampa PRAVI fiskalni račun od 0.10 KM. Nastaviti? [d/N] ").strip().lower() not in ("d", "da", "y"):
        print("Prekinuto.")
        return 1

    print("\n3) Slanje (isto kao aplikacija)")
    result = printer.print_receipt(999999, CART, args.payment)
    print(("ŠTAMPANO" if result.ok else "NIJE ŠTAMPANO") + f", broj fiskalnog računa: {result.fiscal_number or '-'}")
    print(result.message)
    if not result.ok:
        print("\n4) Sirovi odgovor printera")
        raw_post(args.url, body)
    return 0 if result.ok else 1


if __name__ == "__main__":
    sys.exit(main())

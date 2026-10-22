import getpass
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

from locations import env_file

load_dotenv(env_file())

OVERLAYS_PATH = "/ISAPI/System/Video/inputs/channels/1/overlays"


def opener(host: str, user: str, password: str) -> urllib.request.OpenerDirector:
    manager = urllib.request.HTTPPasswordMgrWithDefaultRealm()
    manager.add_password(None, f"http://{host}", user, password)
    return urllib.request.build_opener(
        urllib.request.HTTPDigestAuthHandler(manager),
        urllib.request.HTTPBasicAuthHandler(manager),
    )


def disable(xml: str) -> str:
    for block in ("DateTimeOverlay", "channelNameOverlay"):
        xml = re.sub(
            rf"(<{block}[^>]*>.*?<enabled>)\s*true\s*(</enabled>)",
            r"\1false\2",
            xml,
            flags=re.S | re.I,
        )
    return xml


def process(host: str, user: str, password: str) -> None:
    client = opener(host, user, password)
    url = f"http://{host}{OVERLAYS_PATH}"
    try:
        current = client.open(url, timeout=10).read().decode()
    except urllib.error.HTTPError as error:
        print(f"{host}: kamera je odbila čitanje ({error.code}). Treba admin korisnik.")
        return
    except OSError as error:
        print(f"{host}: kamera nije dostupna ({error}).")
        return
    changed = disable(current)
    if changed == current:
        print(f"{host}: sat i naziv su već isključeni.")
        return
    request = urllib.request.Request(url, data=changed.encode(), method="PUT")
    request.add_header("Content-Type", "application/xml")
    try:
        answer = client.open(request, timeout=10).read().decode()
    except urllib.error.HTTPError as error:
        print(f"{host}: kamera je odbila promjenu ({error.code}): {error.read().decode(errors='replace')[:200]}")
        return
    ok = "<statusCode>1</statusCode>" in answer or "OK" in answer
    print(f"{host}: {'sat i naziv isključeni' if ok else 'odgovor: ' + answer[:200]}")


def main() -> None:
    hosts = [os.environ.get(f"CAM_{name}_HOST", "") for name in ("A", "A2", "B", "B2", "C", "C2")]
    hosts = [host for host in hosts if host]
    if not hosts:
        print("Upiši CAM_A_HOST i CAM_B_HOST u .env.")
        return
    user = input("Admin korisnik kamere [admin]: ").strip() or "admin"
    password = getpass.getpass("Lozinka (ne prikazuje se): ")
    for host in hosts:
        process(host, user, password)


if __name__ == "__main__":
    main()

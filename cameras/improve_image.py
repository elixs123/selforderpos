import getpass
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from disable_osd import opener

# Puna rezolucija: izrez artikla mora biti veći od 224 px koliko gledaju CLIP/DINO (na 1280 px bio bi ~100 px).
MIN_FRAME_RATE = 2500
BITRATE = "8192"


class CameraError(Exception):
    pass


def call(client, url: str, data: str | None = None) -> str:
    request = urllib.request.Request(url, data=data.encode() if data else None, method="PUT" if data else "GET")
    if data:
        request.add_header("Content-Type", "application/xml")
    try:
        return client.open(request, timeout=10).read().decode(errors="replace")
    except urllib.error.HTTPError as error:
        raise CameraError(f"{error.code} {error.read().decode(errors='replace')[:150]}") from error
    except OSError as error:
        raise CameraError(f"nije dostupna ({error})") from error


def tag(xml: str, name: str) -> str | None:
    found = re.search(rf"<{name}[^>]*>([^<]*)</{name}>", xml)
    return found.group(1).strip() if found else None


def set_tag(xml: str, name: str, value: str) -> str:
    return re.sub(rf"(<{name}[^>]*>)[^<]*(</{name}>)", rf"\g<1>{value}\g<2>", xml, count=1)


def options(xml: str, name: str) -> list[int]:
    found = re.search(rf'<{name}[^>]*opt="([^"]+)"', xml)
    return [int(value) for value in found.group(1).split(",") if value.strip().isdigit()] if found else []


def best_resolution(capabilities: str) -> tuple[int, int] | None:
    widths, heights = options(capabilities, "videoResolutionWidth"), options(capabilities, "videoResolutionHeight")
    pairs = list(zip(widths, heights))
    return max(pairs, key=lambda pair: pair[0] * pair[1]) if pairs else None


def describe(xml: str) -> str:
    return (f"{tag(xml, 'videoResolutionWidth')}x{tag(xml, 'videoResolutionHeight')}, "
            f"{int(tag(xml, 'maxFrameRate') or 0) // 100} FPS, {tag(xml, 'videoCodecType')}, "
            f"{tag(xml, 'vbrUpperCap') or tag(xml, 'constantBitRate')} Kbps")


def improve_stream(client, host: str, channel: str) -> None:
    url = f"http://{host}/ISAPI/Streaming/channels/{channel}"
    current = call(client, url)
    print(f"  Tok slike {channel} prije: {describe(current)}")
    try:
        resolution = best_resolution(call(client, f"{url}/capabilities"))
    except CameraError:
        resolution = None
    changed = current
    if resolution:
        changed = set_tag(changed, "videoResolutionWidth", str(resolution[0]))
        changed = set_tag(changed, "videoResolutionHeight", str(resolution[1]))
    else:
        print("  Kamera ne javlja moguće rezolucije, rezolucija ostaje ista.")
    if int(tag(changed, "maxFrameRate") or 0) < MIN_FRAME_RATE:
        changed = set_tag(changed, "maxFrameRate", str(MIN_FRAME_RATE))
    for name, value in (("videoCodecType", "H.264"), ("videoQualityControlType", "VBR"),
                        ("vbrUpperCap", BITRATE), ("constantBitRate", BITRATE)):
        changed = set_tag(changed, name, value)
    if changed == current:
        print("  Tok slike je već podešen.")
        return
    call(client, url, changed)
    print(f"  Tok slike {channel} poslije: {describe(call(client, url))}")


def turn_off(client, host: str, path: str, name: str, field: str, value: str) -> None:
    url = f"http://{host}{path}"
    try:
        current = call(client, url)
    except CameraError:
        print(f"  {name}: kamera ovo nema.")
        return
    if tag(current, field) is None:
        print(f"  {name}: kamera ovo nema.")
        return
    if tag(current, field) == value:
        print(f"  {name}: već isključeno.")
        return
    try:
        call(client, url, set_tag(current, field, value))
        print(f"  {name}: isključeno.")
    except CameraError as error:
        print(f"  {name}: kamera je odbila ({error}).")


def process(host: str, user: str, password: str, channel: str) -> None:
    print(f"\n{host}")
    client = opener(host, user, password)
    try:
        improve_stream(client, host, channel)
    except CameraError as error:
        print(f"  Tok slike: greška {error}")
        if str(error).startswith("401"):
            return
    turn_off(client, host, "/ISAPI/Image/channels/1/WDR", "WDR (wide dynamic range / široki dinamički raspon)", "mode", "close")
    turn_off(client, host, "/ISAPI/Image/channels/1/BLC", "BLC (backlight compensation / kompenzacija pozadinskog svjetla)", "enabled", "false")


def main() -> None:
    hosts = [os.environ.get(f"CAM_{name}_HOST", "") for name in ("A", "A2", "A3", "B", "B2", "B3")]
    hosts = [host for host in hosts if host]
    if not hosts:
        print("Upiši CAM_A_HOST i CAM_B_HOST u .env.")
        return
    channel = os.environ.get("CAM_CHANNEL", "102")
    print(f"Kamere: {', '.join(hosts)}   tok slike: {channel}")
    user = input("Admin korisnik kamere [admin]: ").strip() or "admin"
    password = getpass.getpass("Lozinka (ne prikazuje se): ")
    for host in hosts:
        process(host, user, password, channel)
    print("\nGotovo. Restartuj kasu da preuzme novu sliku.")


if __name__ == "__main__":
    main()

from datetime import datetime

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter
from PySide6.QtPrintSupport import QPrinter, QPrinterInfo

SLIP_WIDTH = 576
QR_SIZE = 400
QUIET_MODULES = 4
MARGIN = 24


def build_payload(ibfm: str, fiscal_number: str, when: datetime, total: float) -> str:
    """Isti sadržaj kao QR na originalnom fiskalnom računu; qrgate na vratima čita IBFM i BF."""
    number = fiscal_number.strip()
    if number.isdigit():
        number = number.zfill(6)
    amount = f"{total:.2f}".replace(".", ",")
    return f"IBFM:{ibfm}\nBF:{number}\nDatum:{when:%d.%m.%Y %H:%M}\nTotal:{amount}"


def render_slip(payload: str, lines: list[str]) -> QImage:
    import segno

    matrix = segno.make(payload, error="m").matrix
    modules = len(matrix) + 2 * QUIET_MODULES
    scale = max(2, QR_SIZE // modules)
    qr_side = modules * scale
    line_height = 40
    height = MARGIN * 2 + 50 + qr_side + 20 + line_height * len(lines)

    image = QImage(SLIP_WIDTH, height, QImage.Format.Format_RGB32)
    image.fill(QColor("white"))
    painter = QPainter(image)
    painter.setPen(QColor("black"))
    font = QFont("Arial")
    font.setPixelSize(30)
    font.setBold(True)
    painter.setFont(font)
    painter.drawText(QRect(0, MARGIN, SLIP_WIDTH, 50), Qt.AlignmentFlag.AlignCenter, "QR ZA VRATA")

    left = (SLIP_WIDTH - qr_side) // 2
    top = MARGIN + 50
    for row, cells in enumerate(matrix):
        for column, dark in enumerate(cells):
            if dark:
                painter.fillRect((QUIET_MODULES + column) * scale + left, (QUIET_MODULES + row) * scale + top, scale, scale, QColor("black"))

    font.setBold(False)
    font.setPixelSize(26)
    painter.setFont(font)
    y = top + qr_side + 20
    for line in lines:
        painter.drawText(QRect(0, y, SLIP_WIDTH, line_height), Qt.AlignmentFlag.AlignCenter, line)
        y += line_height
    painter.end()
    return image


def print_image(image: QImage, printer_name: str = "") -> None:
    """Štampa na printer s tim imenom ili na zadani Windows printer (ime prazno)."""
    if printer_name and printer_name not in QPrinterInfo.availablePrinterNames():
        raise RuntimeError(f"Printer '{printer_name}' nije pronađen. Dostupni: {', '.join(QPrinterInfo.availablePrinterNames()) or '-'}")
    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    if printer_name:
        printer.setPrinterName(printer_name)
    elif not QPrinterInfo.defaultPrinterName():
        raise RuntimeError("Nema zadanog printera. Upiši ime printera u Postavkama.")
    printer.setFullPage(True)
    painter = QPainter()
    if not painter.begin(printer):
        raise RuntimeError("Printer nije prihvatio posao.")
    page = painter.viewport()
    height = round(page.width() * image.height() / image.width())
    painter.drawImage(QRect(0, 0, page.width(), height), image)
    painter.end()


def print_gate_slip(ibfm: str, fiscal_number: str, total: float, printer_name: str = "", when: datetime | None = None) -> None:
    when = when or datetime.now()
    payload = build_payload(ibfm, fiscal_number, when, total)
    lines = [f"BF {fiscal_number}", f"{when:%d.%m.%Y %H:%M}", f"Ukupno {total:.2f} KM", "Skeniraj na vratima"]
    print_image(render_slip(payload, lines), printer_name)

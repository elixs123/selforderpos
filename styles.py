import os
from pathlib import Path

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPalette, QPixmap
from PySide6.QtWidgets import QApplication
from PySide6.QtSvg import QSvgRenderer

SCALE = float(os.environ.get("KASA_SCALE", "0.6"))
ASSETS = Path(__file__).parent / "assets"

RED = "#D5182A"
GREEN = "#3C7A1E"
DARK_GREEN = "#2C5C14"
LIGHT_GREEN = "#E7F3DD"
BACKGROUND = "#F3F5F0"
TEXT = "#16211A"
MUTED_TEXT = "#55625A"
BORDER = "#C3CBC0"
LINE = "#DDE3DA"
DARK_RED = "#B8101F"
LIGHT_RED = "#FDE8EA"
WARNING_BACKGROUND = "#FFF3D6"
WARNING_TEXT = "#8A4B00"

FONT = '"Plus Jakarta Sans", "Helvetica Neue", Arial, sans-serif'


def apply_light_theme(application: QApplication) -> None:
    application.setStyle("Fusion")
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(BACKGROUND))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(TEXT))
    palette.setColor(QPalette.ColorRole.Base, QColor("#FFFFFF"))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(BACKGROUND))
    palette.setColor(QPalette.ColorRole.Text, QColor(TEXT))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(MUTED_TEXT))
    palette.setColor(QPalette.ColorRole.Button, QColor("#FFFFFF"))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(TEXT))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(GREEN))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#FFFFFF"))
    application.setPalette(palette)


def px(value: float) -> int:
    return max(1, round(value * SCALE))


def rounded_logo(size: int, radius: int) -> QPixmap:
    source = QPixmap(str(ASSETS / "logo.png")).scaled(
        size,
        size,
        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
        Qt.TransformationMode.SmoothTransformation,
    )
    result = QPixmap(size, size)
    result.fill(Qt.GlobalColor.transparent)
    painter = QPainter(result)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(0, 0, size, size, radius, radius)
    painter.setClipPath(path)
    painter.drawPixmap(0, 0, source)
    painter.end()
    return result


def icon(shape: str, size: int, color: str = DARK_GREEN, stroke_width: float = 1.8) -> QPixmap:
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        f'stroke="{color}" stroke-width="{stroke_width}" stroke-linecap="round" '
        f'stroke-linejoin="round">{shape}</svg>'
    )
    image = QPixmap(size, size)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    QSvgRenderer(QByteArray(svg.encode())).render(painter)
    painter.end()
    return image


ICON_SCANNER = '<path d="M4 7V5a1 1 0 0 1 1-1h2M17 4h2a1 1 0 0 1 1 1v2M20 17v2a1 1 0 0 1-1 1h-2M7 20H5a1 1 0 0 1-1-1v-2M8 9v6M12 9v6M16 9v6"/>'
ICON_BOX = '<path d="M3 8l9-5 9 5v8l-9 5-9-5z"/><path d="M3 8l9 5 9-5M12 13v8"/>'
ICON_CARD = '<rect x="2" y="5" width="20" height="14" rx="3"/><path d="M2 10h20"/>'
ICON_ARROW = '<path d="M5 12h14M13 6l6 6-6 6"/>'
ICON_HEADSET = '<path d="M4 14v-2a8 8 0 0 1 16 0v2"/><rect x="2.5" y="14" width="5" height="6" rx="2"/><rect x="16.5" y="14" width="5" height="6" rx="2"/>'
ICON_CHECK = '<path d="M5 12.5l4.5 4.5L19 7.5"/>'
ICON_MINUS = '<path d="M5 12h14"/>'
ICON_PLUS = '<path d="M12 5v14M5 12h14"/>'
ICON_ALERT = '<path d="M12 6v8M12 18v.01"/>'
ICON_QR = '<rect x="3" y="3" width="7" height="7" rx="1.2"/><rect x="14" y="3" width="7" height="7" rx="1.2"/><rect x="3" y="14" width="7" height="7" rx="1.2"/><path d="M14 14h3v3M21 14v.01M14 21h3M21 17v4"/>'
ICON_CHEVRON = '<path d="M9 5l7 7-7 7"/>'
ICON_BACK = '<path d="M19 12H5M11 6l-6 6 6 6"/>'
ICON_PRINTER = '<path d="M7 8V3h10v5M7 17H4a1 1 0 0 1-1-1v-6a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v6a1 1 0 0 1-1 1h-3"/><rect x="7" y="14" width="10" height="7" rx="1"/>'
ICON_TRASH = '<path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3"/>'
ICON_DOWN = '<path d="M12 4v16M6 14l6 6 6-6"/>'
ICON_HAND = '<path d="M7 11V6a1.5 1.5 0 0 1 3 0v4M10 10V4.5a1.5 1.5 0 0 1 3 0V10M13 10V5.5a1.5 1.5 0 0 1 3 0V11M16 11V8.5a1.5 1.5 0 0 1 3 0V14a7 7 0 0 1-7 7h-1a6 6 0 0 1-5-2.7L3.5 15a1.5 1.5 0 0 1 2.4-1.8L7 14.5"/>'

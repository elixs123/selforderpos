import threading

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from styles import BACKGROUND, BORDER, DARK_RED, MUTED_TEXT, TEXT, px

COLUMNS = 3
VERDICT_NAMES = {"verified": "osoblje", "learned": "naučeno", "ok": "prihvaćeno", "staff": "osoblje odobrilo"}


class Source:
    def __init__(self, title: str, products: str, images: str, crop: str, delete: str, hint: str, empty: str, detail: str) -> None:
        self.title, self.products, self.images, self.crop, self.delete = title, products, images, crop, delete
        self.hint, self.empty, self.detail = hint, empty, detail


# Slike za prepoznavanje i arhiva su odvojene: brisanje u arhivi ne dira slike po kojima kasa prepoznaje.
SOURCES = {
    "references": Source(
        "Slike artikala", "reference_products", "reference_images", "reference_crop", "delete_reference",
        "Dodirnite artikal da vidite njegove slike i obrišete pogrešne.", "Kasa još nije naučila nijedan artikal.",
        "Obrišite sliku na kojoj nije ovaj artikal (ruka, glava, drugi artikal); brisanje traži dva dodira."),
    "archive": Source(
        "Arhiva izgleda artikla", "archive_products", "archive_images", "archive_crop", "delete_archive_image",
        "Najbolje slike svakog artikla sa svih strana, za kasniji model prepoznavanja.", "Arhiva je još prazna.",
        "Obrišite sliku na kojoj nije ovaj artikal ili koja je loša; brisanje traži dva dodira. "
        "Slike za prepoznavanje ostaju."),
}


def image_count_text(count: int) -> str:
    if count % 10 == 1 and count % 100 != 11:
        return f"{count} slika"
    if count % 10 in (2, 3, 4) and count % 100 not in (12, 13, 14):
        return f"{count} slike"
    return f"{count} slika"


class ReferencesView(QWidget):
    """Slike po kojima kamere prepoznaju artikle; osoblje briše pogrešne (ruka, glava, drugi artikal)."""

    closed = Signal()
    loaded = Signal(object)

    def __init__(self, guard_provider=None) -> None:
        super().__init__()
        self.guard_provider = guard_provider or (lambda: None)
        self.product: dict | None = None
        self.source = SOURCES["references"]
        self._armed: int | None = None
        self.loaded.connect(self._show_loaded)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.pages = QStackedWidget()
        self.list_page, self.rows, self.info, self.list_title = self._page("Slike artikala", self.closed.emit, "Zatvori")
        self.switch = self._button("")
        self.switch.clicked.connect(self._switch_source)
        self.list_page.layout().insertWidget(2, self.switch)
        self.detail_page, self.grid_holder, self.detail_info, self.detail_title = self._page("", self._show_list, "Nazad na listu")
        self.pages.addWidget(self.list_page)
        self.pages.addWidget(self.detail_page)
        layout.addWidget(self.pages)

    def begin(self) -> None:
        self.source = SOURCES["references"]
        self._show_list()

    def _switch_source(self) -> None:
        self.source = SOURCES["archive" if self.source is SOURCES["references"] else "references"]
        self._show_list()

    def _show_list(self) -> None:
        source = self.source
        self.list_title.setText(source.title)
        self.switch.setText("Prikaži slike za prepoznavanje" if source is SOURCES["archive"] else "Prikaži arhivu (najbolje slike)")
        self.pages.setCurrentWidget(self.list_page)
        self.info.setText("Učitavam…")
        self._clear(self.rows)
        self._load(lambda guard: ("list", getattr(guard, source.products)()))

    def _page(self, title_text: str, on_close, close_text: str) -> tuple[QWidget, QVBoxLayout, QLabel, QLabel]:
        page = QWidget()
        column = QVBoxLayout(page)
        column.setContentsMargins(px(40), px(10), px(40), px(30))
        column.setSpacing(px(14))
        title = QLabel(title_text)
        title.setWordWrap(True)
        title.setStyleSheet(f"font-size: {px(48)}px; font-weight: 800;")
        column.addWidget(title)
        info = QLabel()
        info.setWordWrap(True)
        info.setStyleSheet(f"font-size: {px(24)}px; font-weight: 600; color: {MUTED_TEXT};")
        column.addWidget(info)
        rows = QVBoxLayout()
        rows.setContentsMargins(0, 0, 0, 0)
        rows.setSpacing(px(10))
        rows.addStretch()
        content = QWidget()
        content.setLayout(rows)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; } QScrollArea > QWidget > QWidget { background: transparent; }")
        scroll.setWidget(content)
        column.addWidget(scroll, stretch=1)
        close = self._button(close_text)
        close.clicked.connect(on_close)
        column.addWidget(close)
        return page, rows, info, title

    def _button(self, text: str, danger: bool = False) -> QPushButton:
        button = QPushButton(text)
        button.setFixedHeight(px(76))
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        color = DARK_RED if danger else TEXT
        button.setStyleSheet(
            f"QPushButton {{ background: white; color: {color}; border: {px(3)}px solid {BORDER};"
            f" border-radius: {px(38)}px; font-size: {px(24)}px; font-weight: 800; padding: 0 {px(20)}px; }}"
            f"QPushButton:pressed {{ background: {BACKGROUND}; }}"
        )
        return button

    def _clear(self, rows: QVBoxLayout) -> None:
        while rows.count() > 1:
            item = rows.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()

    def _load(self, job) -> None:
        """Slike su na serveru kamera (ili lokalno); učitavaju se u pozadini da ekran ne zastane."""
        guard = self.guard_provider()
        if guard is None or not hasattr(guard, self.source.products):
            self.loaded.emit(("error", "Kamere nisu pokrenute."))
            return

        def work() -> None:
            try:
                self.loaded.emit(job(guard))
            except Exception as error:
                self.loaded.emit(("error", f"Server kamera ne odgovara ({error})."))

        threading.Thread(target=work, daemon=True).start()

    def _show_loaded(self, result) -> None:
        kind, data = result
        if kind == "error":
            (self.detail_info if self.pages.currentWidget() is self.detail_page else self.info).setText(data)
        elif kind == "list":
            self._show_products(data)
        elif kind == "images":
            self._show_images(data)

    def _show_products(self, products: list[dict]) -> None:
        self._clear(self.rows)
        self.info.setText(self.source.hint if products else self.source.empty)
        for position, product in enumerate(products):
            row = QPushButton(f"{product['name']}\n{product['code']} · {image_count_text(product['count'])}")
            row.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
            row.setFixedHeight(px(100))
            row.setCursor(Qt.CursorShape.PointingHandCursor)
            row.setStyleSheet(
                f"QPushButton {{ background: white; color: {TEXT}; border: none; border-radius: {px(30)}px;"
                f" font-size: {px(24)}px; font-weight: 700; text-align: left; padding: 0 {px(24)}px; }}"
                f"QPushButton:pressed {{ background: {BORDER}; }}"
            )
            row.clicked.connect(lambda _checked=False, item=product: self.show_product(item))
            self.rows.insertWidget(position, row)

    def show_product(self, product: dict) -> None:
        self.product, self._armed = product, None
        self.detail_title.setText(product["name"])
        self.detail_info.setText("Učitavam slike…")
        self._clear(self.grid_holder)
        self.pages.setCurrentWidget(self.detail_page)
        self._load(lambda guard: self._images(guard, product["code"]))

    def _images(self, guard, code: str) -> tuple[str, list]:
        crop = getattr(guard, self.source.crop)
        return "images", [(image, crop(image["id"])) for image in getattr(guard, self.source.images)(code)]

    def _show_images(self, images: list) -> None:
        self._clear(self.grid_holder)
        self.detail_info.setText(
            f"{image_count_text(len(images))}. {self.source.detail}" if images else "Nema slika za ovaj artikal.")
        grid_widget = QWidget()
        grid = QGridLayout(grid_widget)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(px(14))
        for index, (image, data) in enumerate(images):
            grid.addWidget(self._image_card(image, data), index // COLUMNS, index % COLUMNS)
        self.grid_holder.insertWidget(0, grid_widget)

    def _image_card(self, image: dict, data: bytes | None) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        card.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        card.setStyleSheet(f"#card {{ background: white; border-radius: {px(24)}px; }}")
        column = QVBoxLayout(card)
        column.setContentsMargins(px(12), px(12), px(12), px(12))
        column.setSpacing(px(8))
        picture = QLabel()
        picture.setAlignment(Qt.AlignmentFlag.AlignCenter)
        picture.setFixedHeight(px(220))
        picture.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        pixmap = QPixmap.fromImage(QImage.fromData(data)) if data else QPixmap()
        if pixmap.isNull():
            picture.setText("nema slike")
        else:
            picture.setPixmap(pixmap.scaled(px(220), px(220), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        column.addWidget(picture)
        quality = image.get("quality")
        details = [image["camera"], VERDICT_NAMES.get(image["verdict"], image["verdict"] or "")]
        if quality is not None:
            details.append(f"{quality:.0%}")
        text = QLabel(" · ".join(details) + f"\n{image['created_at'][:16].replace('T', ' ')}")
        text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        text.setWordWrap(True)
        text.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        text.setStyleSheet(f"font-size: {px(18)}px; color: {MUTED_TEXT};")
        column.addWidget(text)
        delete = self._button("Obriši", danger=True)
        delete.setFixedHeight(px(60))
        delete.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        delete.clicked.connect(lambda _checked=False: self._delete(image["id"], delete))
        column.addWidget(delete)
        return card

    def _delete(self, sample_id: int, button: QPushButton) -> None:
        if self._armed != sample_id:
            self._armed = sample_id
            button.setText("Sigurno obriši?")
            return
        self._armed = None
        code = self.product["code"] if self.product else ""
        self.detail_info.setText("Brišem sliku…")

        def delete_then_reload(guard) -> tuple[str, list]:
            getattr(guard, self.source.delete)(sample_id)
            return self._images(guard, code)

        self._load(delete_then_reload)

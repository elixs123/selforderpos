import threading
from datetime import date, timedelta
from pathlib import Path

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from formatting import format_amount, receipt_count_text
from styles import BACKGROUND, BORDER, MUTED_TEXT, TEXT, px

# Redoslijed i nazivi u izvještaju; ostali događaji se prikažu pod svojim imenom.
EVENT_NAMES = [
    ("accepted:ok", "Artikal prihvaćen"),
    ("accepted:learned", "Novi artikal naučen"),
    ("mismatch", "Artikal odbijen u zoni B"),
    ("timeout:timeout", "Artikal nije odložen"),
    ("rejected:multiple_taken", "Sken odbijen: uzeto više artikala"),
    ("rejected:not_taken", "Sken odbijen: kamera nije vidjela uzimanje"),
    ("accepted:staff", "Osoblje odobrilo artikal"),
    ("accepted:verified", "Osoblje naučilo artikal"),
    ("forgive", "Osoblje poništilo neskenirano"),
    ("staff_call", "Kupac pozvao osoblje"),
    ("unpaid", "Niste sve platili (vrata blokirana)"),
    ("alarm", "Alarmi (snimci)"),
]
# Udio odbijenih artikala iznad kojeg treba pogledati kamere ili prag sličnosti.
HIGH_REJECT_SHARE = 0.2
PROBLEM_REPORT_DAYS = 7


def report_lines(events: dict[str, int]) -> list[str]:
    names = dict(EVENT_NAMES)
    lines = [f"{name}: {events[key]}" for key, name in EVENT_NAMES if events.get(key)]
    lines += [f"{key}: {count}" for key, count in sorted(events.items()) if key not in names and count]
    return lines


def report_advice(events: dict[str, int]) -> str:
    accepted = sum(count for key, count in events.items() if key.startswith("accepted:"))
    rejected = events.get("mismatch", 0)
    if accepted + rejected == 0:
        return ""
    share = rejected / (accepted + rejected)
    text = f"Odbijeno {share:.0%} odlaganja u zoni B."
    if share > HIGH_REJECT_SHARE:
        text += " To je mnogo: provjerite kamere zone B (oštrina, položaj) ili spustite prag sličnosti u postavkama."
    return text


class ReportView(QWidget):
    """Dnevni izvještaj: računi sa kase i događaji kamera (prihvaćeno, odbijeno, alarmi, pozivi osoblja)."""

    closed = Signal()
    loaded = Signal(object)
    problems_ready = Signal(str)

    def __init__(self, store=None, guard_provider=None) -> None:
        super().__init__()
        self.store = store
        self.guard_provider = guard_provider or (lambda: None)
        self.day = date.today()
        self.loaded.connect(self._show_events)
        self.problems_ready.connect(self._problems_saved)
        column = QVBoxLayout(self)
        column.setContentsMargins(px(40), px(10), px(40), px(30))
        column.setSpacing(px(14))
        title = QLabel("Izvještaj za dan")
        title.setStyleSheet(f"font-size: {px(56)}px; font-weight: 800;")
        column.addWidget(title)

        days = QHBoxLayout()
        days.setSpacing(px(14))
        previous = self._button("‹ Prethodni dan")
        previous.clicked.connect(lambda: self._move(-1))
        days.addWidget(previous)
        self.day_label = QLabel()
        self.day_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.day_label.setStyleSheet(f"font-size: {px(30)}px; font-weight: 800;")
        days.addWidget(self.day_label, stretch=1)
        self.next_button = self._button("Sljedeći dan ›")
        self.next_button.clicked.connect(lambda: self._move(1))
        days.addWidget(self.next_button)
        column.addLayout(days)

        self.receipts = QLabel()
        self.receipts.setWordWrap(True)
        self.receipts.setStyleSheet(f"font-size: {px(28)}px; font-weight: 700;")
        column.addWidget(self.receipts)
        self.events = QLabel()
        self.events.setWordWrap(True)
        self.events.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.events.setStyleSheet(f"font-size: {px(26)}px; background: white; border-radius: {px(26)}px; padding: {px(20)}px;")
        column.addWidget(self.events, stretch=1)
        self.advice = QLabel()
        self.advice.setWordWrap(True)
        self.advice.setStyleSheet(f"font-size: {px(24)}px; font-weight: 600; color: {MUTED_TEXT};")
        column.addWidget(self.advice)
        self.problems_button = self._button(f"Problematični artikli ({PROBLEM_REPORT_DAYS} dana), za kolege")
        self.problems_button.clicked.connect(self.save_problem_report)
        column.addWidget(self.problems_button)
        close = self._button("Zatvori")
        close.clicked.connect(self.closed.emit)
        column.addWidget(close)

    def begin(self) -> None:
        self.day = date.today()
        self._load()

    def _button(self, text: str) -> QPushButton:
        button = QPushButton(text)
        button.setFixedHeight(px(76))
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setStyleSheet(
            f"QPushButton {{ background: white; color: {TEXT}; border: {px(3)}px solid {BORDER};"
            f" border-radius: {px(38)}px; font-size: {px(24)}px; font-weight: 800; padding: 0 {px(20)}px; }}"
            f"QPushButton:pressed {{ background: {BACKGROUND}; }}"
            f"QPushButton:disabled {{ color: {BORDER}; }}"
        )
        return button

    def _move(self, days: int) -> None:
        self.day = min(date.today(), self.day + timedelta(days=days))
        self._load()

    def _load(self) -> None:
        self.day_label.setText("Danas" if self.day == date.today() else f"{self.day:%d.%m.%Y.}")
        self.next_button.setEnabled(self.day < date.today())
        receipts = self.store.receipts_on(self.day) if self.store is not None else []
        total = sum(receipt["total"] for receipt in receipts)
        self.receipts.setText(f"Kasa: {receipt_count_text(len(receipts))}, ukupno {format_amount(total)} KM")
        self.events.setText("Učitavam događaje kamera…")
        self.advice.setText("")
        guard, day = self.guard_provider(), f"{self.day:%Y-%m-%d}"
        if guard is None or not hasattr(guard, "report"):
            self.loaded.emit((day, None, "Kamere nisu pokrenute."))
            return

        def work() -> None:
            try:
                self.loaded.emit((day, guard.report(day), ""))
            except Exception as error:
                self.loaded.emit((day, None, f"Server kamera ne odgovara ({error})."))

        threading.Thread(target=work, daemon=True).start()

    def _show_events(self, result) -> None:
        day, events, error = result
        if day != f"{self.day:%Y-%m-%d}":
            return
        if events is None:
            self.events.setText(error)
            return
        lines = report_lines(events)
        self.events.setText("\n".join(lines) if lines else "Nema događaja kamera za ovaj dan.")
        self.advice.setText(report_advice(events))

    def report_folder(self) -> Path:
        base = Path(self.store.path).parent if self.store is not None and hasattr(self.store, "path") else Path.cwd()
        return base / "izvjestaji"

    def save_problem_report(self) -> None:
        """Izvještaj sa slikama artikala koje kamere teško prepoznaju; sprema se kao HTML (štampa / PDF iz preglednika)."""
        guard = self.guard_provider()
        if guard is None or not hasattr(guard, "problem_report"):
            self.advice.setText("Kamere nisu pokrenute.")
            return
        self.problems_button.setEnabled(False)
        self.advice.setText("Pravim izvještaj o problematičnim artiklima…")
        folder = self.report_folder()

        def work() -> None:
            try:
                html_text = guard.problem_report(PROBLEM_REPORT_DAYS)
                folder.mkdir(parents=True, exist_ok=True)
                path = folder / f"problematicni-artikli-{date.today():%Y-%m-%d}.html"
                path.write_text(html_text, encoding="utf-8")
                self.problems_ready.emit(str(path))
            except Exception as error:
                self.problems_ready.emit(f"!Izvještaj nije napravljen ({error}).")

        threading.Thread(target=work, daemon=True).start()

    def _problems_saved(self, result: str) -> None:
        self.problems_button.setEnabled(True)
        if result.startswith("!"):
            self.advice.setText(result[1:])
            return
        self.advice.setText(f"Izvještaj je sačuvan: {result}. Otvara se u pregledniku (odatle štampa ili PDF).")
        QDesktopServices.openUrl(QUrl.fromLocalFile(result))

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from styles import FONT, px


class AgeState(QObject):
    """Da li je upozorenje 18+ uključeno; gornje trake svih ekrana kupovine ga prate."""

    changed = Signal(bool)

    def __init__(self) -> None:
        super().__init__()
        self.visible = False

    def set(self, visible: bool) -> None:
        if visible != self.visible:
            self.visible = visible
            self.changed.emit(visible)


_state: AgeState | None = None


def age_state() -> AgeState:
    # QObject se pravi tek kad postoji QApplication.
    global _state
    if _state is None:
        _state = AgeState()
    return _state


class AgeWarning(QFrame):
    """Upozorenje 18+ u gornjoj traci, pored Snimate se. Samo se prikazuje: klikovi prolaze i ne uzima fokus skeneru."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setObjectName("ageWarning")
        self.setFixedHeight(px(96))
        self.setStyleSheet(
            f"#ageWarning {{ background: #FFF4D6; border: {px(2)}px solid #E0A100;"
            f" border-radius: {px(26)}px; font-family: {FONT}; }}"
        )
        row = QHBoxLayout(self)
        row.setContentsMargins(px(10), px(8), px(24), px(8))
        row.setSpacing(px(14))
        badge = QLabel("18+")
        badge.setFixedSize(px(76), px(76))
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setStyleSheet(f"background: #B8101F; color: white; border-radius: {px(38)}px; font-size: {px(28)}px; font-weight: 800;")
        row.addWidget(badge)
        column = QVBoxLayout()
        column.setSpacing(0)
        title = QLabel("Alkoholni artikli")
        title.setStyleSheet(f"font-size: {px(26)}px; font-weight: 800; color: #5C4300;")
        column.addWidget(title)
        detail = QLabel("Morate imati 18+ godina")
        detail.setStyleSheet(f"font-size: {px(20)}px; color: #5C4300;")
        column.addWidget(detail)
        row.addLayout(column)
        state = age_state()
        self.setVisible(state.visible)
        state.changed.connect(self.setVisible)

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from styles import FONT, px

# Stoji u gornjoj traci između loga i dugmeta 'Pozovi osoblje' (preko natpisa), da ne pokriva sadržaj ekrana.
TOP_BAR = 112
LOGO = 118
STAFF_BUTTON = 312


class AgeWarning(QFrame):
    """Upozorenje 18+ u gornjoj traci. Samo se prikazuje: klikovi prolaze kroz njega i ne uzima fokus skeneru."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setObjectName("ageWarning")
        self.setStyleSheet(
            f"#ageWarning {{ background: #FFF4D6; border: {px(3)}px solid #E0A100;"
            f" border-radius: {px(24)}px; font-family: {FONT}; }}"
        )
        row = QHBoxLayout(self)
        row.setContentsMargins(px(14), px(12), px(22), px(12))
        row.setSpacing(px(14))
        badge = QLabel("18+")
        badge.setFixedSize(px(68), px(68))
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setStyleSheet(f"background: #B8101F; color: white; border-radius: {px(34)}px; font-size: {px(26)}px; font-weight: 800;")
        row.addWidget(badge)
        column = QVBoxLayout()
        column.setSpacing(0)
        title = QLabel("Alkoholni artikli")
        title.setStyleSheet(f"font-size: {px(24)}px; font-weight: 800; color: #5C4300;")
        column.addWidget(title)
        detail = QLabel("Morate imati 18+ godina")
        detail.setStyleSheet(f"font-size: {px(20)}px; font-weight: 600; color: #5C4300;")
        column.addWidget(detail)
        row.addLayout(column)
        row.addStretch()
        self.hide()

    def set_visible_on_top(self, visible: bool) -> None:
        if not visible:
            self.hide()
            return
        self.adjustSize()
        self.setFixedWidth(self.parentWidget().width() - px(LOGO) - px(STAFF_BUTTON))
        self.move(px(LOGO), (px(TOP_BAR) - self.height()) // 2)
        if self.isHidden():
            self.show()
            self.raise_()

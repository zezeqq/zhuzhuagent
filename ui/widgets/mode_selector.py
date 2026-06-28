from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QPushButton


MODES = [
    ("ask", "问一问"),
    ("craft", "做一做"),
    ("plan", "想一想"),
]


class ModeSelector(QFrame):
    mode_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ModeSelector")
        self._current = "craft"
        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(0)
        self._buttons: dict[str, QPushButton] = {}
        for key, label in MODES:
            btn = QPushButton(label)
            btn.setObjectName("ModeButton")
            btn.setCursor(Qt.PointingHandCursor)
            btn.setCheckable(True)
            btn.setChecked(key == self._current)
            btn.clicked.connect(lambda _, k=key: self._select(k))
            self._buttons[key] = btn
            layout.addWidget(btn)

    def _select(self, key: str) -> None:
        if key == self._current:
            return
        self._current = key
        for k, btn in self._buttons.items():
            btn.setChecked(k == key)
        self.mode_changed.emit(key)

    def retranslate_ui(self) -> None:
        from ui.i18n import t

        for key, label_key in (("ask", "mode_ask"), ("craft", "mode_craft"), ("plan", "mode_plan")):
            btn = self._buttons.get(key)
            if btn:
                btn.setText(t(label_key))

    def current_mode(self) -> str:
        return self._current

    def set_mode(self, key: str) -> None:
        if key not in self._buttons:
            return
        self._current = key
        for k, btn in self._buttons.items():
            btn.setChecked(k == key)

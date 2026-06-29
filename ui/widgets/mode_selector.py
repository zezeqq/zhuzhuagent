from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QComboBox


# Display labels are always English. Internal keys unchanged for DB / agent.py.
MODE_OPTIONS: list[tuple[str, str, str]] = [
    ("ask", "Ask", "Chat only — no tools"),
    ("plan", "Plan", "Draft a plan first; confirm before running tools"),
    ("craft", "Craft", "Generate docs & search library — file automation first"),
]

_MODE_KEYS = {key for key, _, _ in MODE_OPTIONS}


class ModeSelector(QComboBox):
    """Compact mode dropdown: Ask / Plan / Craft."""

    mode_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ModeCombo")
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumWidth(108)
        self.setMaximumWidth(140)
        self._current = "craft"
        self._building = True
        for key, label, tip in MODE_OPTIONS:
            self.addItem(label, key)
            idx = self.count() - 1
            self.setItemData(idx, tip, Qt.ToolTipRole)
        self._building = False
        self.set_mode("craft")
        self.currentIndexChanged.connect(self._on_index_changed)

    def _on_index_changed(self, index: int) -> None:
        if self._building or index < 0:
            return
        key = self.itemData(index)
        if not key or key == self._current:
            return
        self._current = key
        self.mode_changed.emit(key)

    def retranslate_ui(self) -> None:
        """Mode labels stay English regardless of app locale."""

    def current_mode(self) -> str:
        return self._current

    def set_mode(self, key: str) -> None:
        if key not in _MODE_KEYS:
            key = "craft"
        self._current = key
        self._building = True
        for i in range(self.count()):
            if self.itemData(i) == key:
                self.setCurrentIndex(i)
                break
        self._building = False

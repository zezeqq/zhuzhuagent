from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QWidget


class ReferenceStrip(QWidget):
    """Horizontal strip for @ referenced library / artifact files."""

    reference_removed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ReferenceStrip")
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(6)
        self._layout.addStretch()
        self.setVisible(False)

    def add_reference(self, path: str, *, icon: str = "📎", category: str = "") -> None:
        if path in self.file_paths():
            return
        name = Path(path).name
        card = QFrame()
        card.setObjectName("ReferenceCard")
        card.setProperty("file_path", path)
        card.setToolTip(path)
        cl = QHBoxLayout(card)
        cl.setContentsMargins(8, 4, 4, 4)
        cl.setSpacing(4)

        icon_lbl = QLabel(icon)
        icon_lbl.setStyleSheet("background: transparent;")
        cl.addWidget(icon_lbl)

        name_lbl = QLabel(name[:28] + ("…" if len(name) > 28 else ""))
        name_lbl.setObjectName("ReferenceCardName")
        if category:
            name_lbl.setToolTip(f"{category} · {path}")
        cl.addWidget(name_lbl)

        remove_btn = QPushButton("×")
        remove_btn.setObjectName("ReferenceRemoveBtn")
        remove_btn.setFixedSize(18, 18)
        remove_btn.setCursor(Qt.PointingHandCursor)
        remove_btn.clicked.connect(lambda _, p=path: self._remove(p))
        cl.addWidget(remove_btn)

        idx = self._layout.count() - 1
        self._layout.insertWidget(idx, card)
        self.setVisible(True)

    def _remove(self, path: str) -> None:
        for i in range(self._layout.count()):
            item = self._layout.itemAt(i)
            w = item.widget() if item else None
            if w and w.property("file_path") == path:
                self._layout.removeWidget(w)
                w.deleteLater()
                break
        self.reference_removed.emit(path)
        if self._layout.count() <= 1:
            self.setVisible(False)

    def clear_all(self) -> None:
        while self._layout.count() > 1:
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.setVisible(False)

    def file_paths(self) -> list[str]:
        paths: list[str] = []
        for i in range(self._layout.count()):
            item = self._layout.itemAt(i)
            w = item.widget() if item else None
            if w and w.property("file_path"):
                paths.append(w.property("file_path"))
        return paths

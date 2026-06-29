from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QLabel, QListWidget, QListWidgetItem, QVBoxLayout, QWidget

from core.file_references import filter_reference_candidates, current_project_id


class FileReferencePopup(QFrame):
    """Popup menu for @ file references."""

    item_chosen = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent, Qt.Popup | Qt.FramelessWindowHint)
        self.setObjectName("ReferencePopup")
        self.setMinimumWidth(320)
        self.setMaximumWidth(420)
        self.setMaximumHeight(320)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        self._hint = QLabel("选择要 @ 引用的文件")
        self._hint.setObjectName("MutedLabel")
        layout.addWidget(self._hint)

        self._list = QListWidget()
        self._list.setObjectName("ReferencePopupList")
        self._list.itemActivated.connect(self._emit_current)
        layout.addWidget(self._list, 1)

    def set_query(self, query: str) -> None:
        items = filter_reference_candidates(query, current_project_id())
        self._list.clear()
        if not items:
            empty = QListWidgetItem("没有匹配的文件")
            empty.setFlags(Qt.NoItemFlags)
            self._list.addItem(empty)
            return
        for item in items:
            label = f"{item['icon']}  {item['name']}"
            sub = item.get("subtitle", "")
            if sub:
                label += f"  ·  {sub}"
            row = QListWidgetItem(label)
            row.setData(Qt.UserRole, item)
            row.setToolTip(item.get("path", ""))
            self._list.addItem(row)
        self._list.setCurrentRow(0)

    def select_next(self) -> None:
        if self._list.count() <= 0:
            return
        row = self._list.currentRow()
        self._list.setCurrentRow(min(row + 1, self._list.count() - 1))

    def select_prev(self) -> None:
        if self._list.count() <= 0:
            return
        row = self._list.currentRow()
        self._list.setCurrentRow(max(row - 1, 0))

    def accept_current(self) -> bool:
        item = self._list.currentItem()
        if not item or not (item.flags() & Qt.ItemIsSelectable):
            return False
        data = item.data(Qt.UserRole)
        if isinstance(data, dict):
            self.item_chosen.emit(data)
            return True
        return False

    def _emit_current(self, item: QListWidgetItem) -> None:
        data = item.data(Qt.UserRole)
        if isinstance(data, dict):
            self.item_chosen.emit(data)

"""列表多选时的批量操作工具栏。"""

from __future__ import annotations

from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton


class BatchActionBar(QFrame):
    select_all_clicked = Signal()
    clear_clicked = Signal()
    open_clicked = Signal()
    delete_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("BatchActionBar")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(6)

        self._count_label = QLabel("已选 0 项")
        self._count_label.setObjectName("BatchActionCount")
        layout.addWidget(self._count_label)
        layout.addStretch()

        for text, slot in [
            ("全选", self.select_all_clicked.emit),
            ("取消", self.clear_clicked.emit),
            ("打开", self.open_clicked.emit),
            ("删除", self.delete_clicked.emit),
        ]:
            btn = QPushButton(text)
            btn.setObjectName("BatchActionButton")
            btn.setProperty("variant", "secondary")
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(slot)
            layout.addWidget(btn)
            if text == "打开":
                self._open_btn = btn
            elif text == "删除":
                self._delete_btn = btn

        self.set_count(0)

    def set_count(self, count: int) -> None:
        self._count_label.setText(f"已选 {count} 项")
        enabled = count > 0
        self._open_btn.setEnabled(enabled)
        self._delete_btn.setEnabled(enabled)

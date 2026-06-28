from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout


STATUS_ICONS = {
    "pending": "○",
    "running": "◉",
    "completed": "●",
    "failed": "✕",
    "cancelled": "◌",
}


class StepItem(QFrame):
    def __init__(self, index: int, name: str, tool: str = "", status: str = "pending", parent=None):
        super().__init__(parent)
        self.setObjectName("StepItem")
        self.index = index
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(8)
        self._icon = QLabel(STATUS_ICONS.get(status, "○"))
        self._icon.setObjectName("StepIcon")
        self._icon.setFixedWidth(18)
        self._icon.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._icon)
        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        self._name = QLabel(f"{index}. {name}")
        self._name.setObjectName("StepName")
        text_col.addWidget(self._name)
        if tool:
            tool_label = QLabel(tool)
            tool_label.setObjectName("StepTool")
            text_col.addWidget(tool_label)
        layout.addLayout(text_col, 1)
        self._status_label = QLabel(status)
        self._status_label.setObjectName("StepStatus")
        self._status_label.setProperty("step_status", status)
        layout.addWidget(self._status_label)
        self.set_status(status)

    def set_status(self, status: str) -> None:
        self._icon.setText(STATUS_ICONS.get(status, "○"))
        self._status_label.setText({"pending": "等待", "running": "执行中", "completed": "完成", "failed": "失败", "cancelled": "取消"}.get(status, status))
        self._status_label.setProperty("step_status", status)
        self._status_label.style().unpolish(self._status_label)
        self._status_label.style().polish(self._status_label)

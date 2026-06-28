from __future__ import annotations

from typing import Iterable

from core.app_identity import APP_NAME
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QScrollArea, QTableWidget, QVBoxLayout, QWidget,
)


def clear_layout(layout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        child_layout = item.layout()
        if widget:
            widget.deleteLater()
        if child_layout:
            clear_layout(child_layout)


class Card(QFrame):
    def __init__(self, parent=None, object_name: str = "Card"):
        super().__init__(parent)
        self.setObjectName(object_name)
        self.setFrameShape(QFrame.NoFrame)


class ModernButton(QPushButton):
    def __init__(self, text: str, variant: str = "primary", parent=None):
        super().__init__(text, parent)
        self.setProperty("variant", variant)
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(34)


class SearchBox(QLineEdit):
    def __init__(self, placeholder: str = "搜索...", parent=None):
        super().__init__(parent)
        self.setPlaceholderText(placeholder)
        self.setObjectName("SearchBox")
        self.setMinimumHeight(36)


class EmptyState(Card):
    def __init__(self, title: str, subtitle: str = "", action: QWidget | None = None, parent=None):
        super().__init__(parent, "EmptyState")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(10)
        icon = QLabel("◇")
        icon.setObjectName("EmptyIcon")
        icon.setAlignment(Qt.AlignCenter)
        title_label = QLabel(title)
        title_label.setObjectName("EmptyTitle")
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(icon)
        layout.addWidget(title_label)
        if subtitle:
            sub = QLabel(subtitle)
            sub.setObjectName("MutedLabel")
            sub.setAlignment(Qt.AlignCenter)
            sub.setWordWrap(True)
            layout.addWidget(sub)
        if action:
            row = QHBoxLayout()
            row.addStretch()
            row.addWidget(action)
            row.addStretch()
            layout.addLayout(row)


class ActionCard(Card):
    clicked = Signal()

    def __init__(self, title: str, subtitle: str, parent=None):
        super().__init__(parent, "ActionCard")
        self.setCursor(Qt.PointingHandCursor)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(6)
        title_label = QLabel(title)
        title_label.setObjectName("CardTitle")
        subtitle_label = QLabel(subtitle)
        subtitle_label.setObjectName("MutedLabel")
        subtitle_label.setWordWrap(True)
        layout.addWidget(title_label)
        layout.addWidget(subtitle_label)
        layout.addStretch()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)


class StatusBadge(QLabel):
    def __init__(self, text: str, tone: str = "neutral", parent=None):
        super().__init__(text, parent)
        self.setObjectName("StatusBadge")
        self.setProperty("tone", tone)
        self.setAlignment(Qt.AlignCenter)


class ModernTable(QTableWidget):
    def __init__(self, columns: list[str], parent=None):
        super().__init__(0, len(columns), parent)
        self.setObjectName("ModernTable")
        self.setHorizontalHeaderLabels(columns)
        self.setAlternatingRowColors(True)
        self.setSelectionBehavior(QTableWidget.SelectRows)
        self.setEditTriggers(QTableWidget.NoEditTriggers)
        self.verticalHeader().setVisible(False)
        self.horizontalHeader().setStretchLastSection(True)


class MessageBubble(Card):
    def __init__(self, role: str, content: str, parent=None):
        super().__init__(parent, "MessageBubble")
        self.setProperty("role", role)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(6)
        title = QLabel("我" if role == "user" else APP_NAME)
        title.setObjectName("BubbleRole")
        text = QLabel(content)
        text.setObjectName("BubbleText")
        text.setWordWrap(True)
        text.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(title)
        layout.addWidget(text)


def flow_grid(items: list[QWidget], columns: int = 3) -> QWidget:
    holder = QWidget()
    grid = QGridLayout(holder)
    grid.setContentsMargins(0, 0, 0, 0)
    grid.setSpacing(12)
    for idx, item in enumerate(items):
        grid.addWidget(item, idx // columns, idx % columns)
    for col in range(columns):
        grid.setColumnStretch(col, 1)
    return holder

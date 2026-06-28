"""Buddy 风格消息框 — 替代原生 QMessageBox。"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

_KIND_META = {
    "info": ("ℹ", "#3b82f6", "信息"),
    "success": ("✓", "#22c55e", "成功"),
    "warning": ("!", "#f59e0b", "注意"),
    "error": ("✕", "#ef4444", "错误"),
    "question": ("?", "#8b5cf6", "请确认"),
}


class BuddyMessageDialog(QDialog):
    def __init__(
        self,
        parent: QWidget | None,
        *,
        kind: str = "info",
        title: str = "",
        message: str = "",
        detail: str = "",
        primary_text: str = "知道了",
        secondary_text: str = "",
    ):
        super().__init__(parent)
        self.setObjectName("BuddyMessageDialog")
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setModal(True)
        self.setMinimumWidth(400)
        self.setMaximumWidth(480)
        self._confirmed = False

        icon_char, accent, default_title = _KIND_META.get(kind, _KIND_META["info"])
        title = title or default_title

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        card = QFrame()
        card.setObjectName("BuddyMessageCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(14)

        head = QHBoxLayout()
        head.setSpacing(14)
        icon = QLabel(icon_char)
        icon.setFixedSize(44, 44)
        icon.setAlignment(Qt.AlignCenter)
        icon.setStyleSheet(
            f"font-size:20px; font-weight:700; color:white;"
            f"background:{accent}; border-radius:22px;"
        )
        head.addWidget(icon, 0, Qt.AlignTop)

        text_col = QVBoxLayout()
        text_col.setSpacing(6)
        t = QLabel(title)
        t.setObjectName("BuddyMessageTitle")
        t.setWordWrap(True)
        text_col.addWidget(t)
        body = QLabel(message.replace("\n", "<br>"))
        body.setObjectName("BuddyMessageBody")
        body.setWordWrap(True)
        body.setTextFormat(Qt.RichText)
        body.setOpenExternalLinks(False)
        text_col.addWidget(body)
        head.addLayout(text_col, 1)
        layout.addLayout(head)

        if detail.strip():
            box = QFrame()
            box.setObjectName("BuddyMessageDetail")
            bl = QVBoxLayout(box)
            bl.setContentsMargins(12, 10, 12, 10)
            dl = QLabel(detail)
            dl.setWordWrap(True)
            dl.setObjectName("MutedLabel")
            bl.addWidget(dl)
            layout.addWidget(box)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        if secondary_text:
            sec = QPushButton(secondary_text)
            sec.setProperty("variant", "ghost")
            sec.setCursor(Qt.PointingHandCursor)
            sec.clicked.connect(self.reject)
            btn_row.addWidget(sec)
        primary = QPushButton(primary_text)
        primary.setProperty("variant", "primary")
        primary.setCursor(Qt.PointingHandCursor)
        primary.setMinimumWidth(96)
        primary.clicked.connect(self._on_primary)
        btn_row.addWidget(primary)
        layout.addLayout(btn_row)

        root.addWidget(card)

    def _on_primary(self):
        self._confirmed = True
        self.accept()

    @staticmethod
    def run(
        parent: QWidget | None,
        *,
        kind: str = "info",
        title: str = "",
        message: str = "",
        detail: str = "",
        primary_text: str = "知道了",
        secondary_text: str = "",
    ) -> bool:
        dlg = BuddyMessageDialog(
            parent,
            kind=kind,
            title=title,
            message=message,
            detail=detail,
            primary_text=primary_text,
            secondary_text=secondary_text,
        )
        return dlg.exec() == QDialog.Accepted and dlg._confirmed


def show_info(parent, title: str, message: str, *, detail: str = "") -> None:
    BuddyMessageDialog.run(parent, kind="info", title=title, message=message, detail=detail)


def show_success(parent, title: str, message: str, *, detail: str = "") -> None:
    BuddyMessageDialog.run(parent, kind="success", title=title, message=message, detail=detail)


def show_warning(parent, title: str, message: str, *, detail: str = "") -> None:
    BuddyMessageDialog.run(parent, kind="warning", title=title, message=message, detail=detail)


def show_error(parent, title: str, message: str, *, detail: str = "") -> None:
    BuddyMessageDialog.run(parent, kind="error", title=title, message=message, detail=detail)


def ask_confirm(
    parent,
    title: str,
    message: str,
    *,
    detail: str = "",
    yes_text: str = "确定",
    no_text: str = "取消",
) -> bool:
    return BuddyMessageDialog.run(
        parent,
        kind="question",
        title=title,
        message=message,
        detail=detail,
        primary_text=yes_text,
        secondary_text=no_text,
    )

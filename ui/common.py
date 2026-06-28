from __future__ import annotations

from core.app_identity import APP_NAME
from PySide6.QtWidgets import QMessageBox


def info(parent, text: str):
    QMessageBox.information(parent, APP_NAME, text)


def warn(parent, text: str):
    QMessageBox.warning(parent, APP_NAME, text)


def confirm(parent, text: str) -> bool:
    return QMessageBox.question(parent, "请确认", text, QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes

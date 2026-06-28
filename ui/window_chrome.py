"""无边框窗口：自定义标题栏拖拽、Windows 暗色边框。"""

from __future__ import annotations

import ctypes
import sys

from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QFrame, QPushButton, QWidget


class TitleBarFrame(QFrame):
    """顶栏拖拽移动，双击最大化/还原；不拦截子控件点击。"""

    def __init__(self, window: QWidget):
        super().__init__()
        self._window = window
        self._drag_offset: QPoint | None = None

    def _is_interactive_child(self, pos) -> bool:
        child = self.childAt(pos)
        while child and child is not self:
            if isinstance(child, QPushButton):
                return True
            child = child.parentWidget()
        return False

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and not self._is_interactive_child(event.pos()):
            if self._window.isMaximized():
                ratio = event.position().x() / max(self.width(), 1)
                self._window.showNormal()
                new_x = int(event.globalPosition().x() - self._window.width() * ratio)
                self._window.move(new_x, int(event.globalPosition().y() - 16))
            self._drag_offset = (
                event.globalPosition().toPoint() - self._window.frameGeometry().topLeft()
            )
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_offset is not None and event.buttons() & Qt.LeftButton:
            self._window.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_offset = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton and not self._is_interactive_child(event.pos()):
            if self._window.isMaximized():
                self._window.showNormal()
            else:
                self._window.showMaximized()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)


def apply_window_effects(window: QWidget) -> None:
    """无边框窗口 DWM 边框色，随主题深浅变化。"""
    if sys.platform != "win32":
        return
    try:
        from core.settings_store import get_setting
        from ui.theme import apply_theme_palette

        theme = get_setting("theme", "深色")
        if theme == "跟随系统":
            from PySide6.QtGui import QGuiApplication
            hints = QGuiApplication.styleHints()
            if hasattr(hints, "colorScheme"):
                from PySide6.QtCore import Qt as QtCore
                theme = "浅色" if hints.colorScheme() == QtCore.ColorScheme.Light else "深色"
        apply_theme_palette("浅色" if theme == "浅色" else "深色")

        hwnd = int(window.winId())
        dwm = ctypes.windll.dwmapi
        dark = ctypes.c_int(1 if theme != "浅色" else 0)
        for attr in (20, 19):
            if dwm.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(dark), ctypes.sizeof(dark)) == 0:
                break
        # BGR
        border_color = ctypes.c_uint32(0x00E5E7EB if theme == "浅色" else 0x001A1A1A)
        dwm.DwmSetWindowAttribute(
            hwnd, 34, ctypes.byref(border_color), ctypes.sizeof(border_color)
        )
    except Exception:
        pass

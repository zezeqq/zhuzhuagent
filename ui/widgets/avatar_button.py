from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import QPushButton


class AvatarButton(QPushButton):
    """Circular avatar button with image clipping and a soft fallback."""

    clicked_avatar = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("SidebarAvatar")
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(36, 36)
        self._pixmap = QPixmap()
        self._fallback_text = "🐷"
        self.clicked.connect(lambda _checked=False: self.clicked_avatar.emit())

    def set_avatar(self, path: str, fallback_text: str = "🐷") -> None:
        self._fallback_text = fallback_text or "🐷"
        pix = QPixmap(path) if path and Path(path).is_file() else QPixmap()
        self._pixmap = pix
        self.setText("" if not pix.isNull() else self._fallback_text)
        self.update()

    def paintEvent(self, event) -> None:
        if self._pixmap.isNull():
            super().paintEvent(event)
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = self.rect().adjusted(1, 1, -1, -1)

        path = QPainterPath()
        path.addEllipse(rect)
        painter.setClipPath(path)

        pix = self._pixmap.scaled(
            rect.size(),
            Qt.KeepAspectRatioByExpanding,
            Qt.SmoothTransformation,
        )
        x = rect.x() + (rect.width() - pix.width()) // 2
        y = rect.y() + (rect.height() - pix.height()) // 2
        painter.drawPixmap(x, y, pix)

        painter.setClipping(False)
        painter.setPen(QColor(122, 162, 255, 85))
        painter.drawEllipse(rect)

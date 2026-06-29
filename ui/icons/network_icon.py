"""联网开关按钮图标（单色 SVG，随主题着色）。"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from ui.theme import Palette
from utils.path_utils import resource_path

_ICON_CACHE: dict[tuple[bool, int], QIcon] = {}


def network_toggle_icon(*, enabled: bool, size: int = 18) -> QIcon:
    key = (enabled, size)
    cached = _ICON_CACHE.get(key)
    if cached is not None:
        return cached

    svg_path = resource_path("ui", "icons", "network.svg")
    renderer = QSvgRenderer(str(svg_path))
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
    color = QColor(Palette.BLUE if enabled else Palette.WEAK)
    painter.fillRect(pixmap.rect(), color)
    painter.end()

    icon = QIcon(pixmap)
    _ICON_CACHE[key] = icon
    return icon


def network_toggle_icon_size() -> QSize:
    return QSize(18, 18)

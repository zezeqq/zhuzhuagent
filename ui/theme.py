from __future__ import annotations

import re

from pathlib import Path


class DarkPalette:
    BG = "#0F1117"
    SIDEBAR = "#0A0C10"
    CARD = "#161921"
    CARD_HOVER = "#1C2029"
    BORDER = "#252A35"
    BORDER_LIGHT = "#2E3440"
    TEXT = "#F0F2F5"
    MUTED = "#9CA3AF"
    WEAK = "#6B7280"
    BLUE = "#3B82F6"
    BLUE_HOVER = "#2563EB"
    BLUE_MUTED = "#1E3A5F"
    INDIGO = "#6366F1"
    SUCCESS = "#22C55E"
    WARNING = "#F59E0B"
    DANGER = "#EF4444"
    HOVER = "#1F2937"
    SELECTED = "#1D4ED8"
    INPUT = "#0D1017"
    TOOLBAR = "#111318"


class Palette(DarkPalette):
    """Active theme colors; updated by apply_theme_palette()."""
    pass


class LightPalette:
    BG = "#F3F4F6"
    SIDEBAR = "#FFFFFF"
    CARD = "#FFFFFF"
    CARD_HOVER = "#F9FAFB"
    BORDER = "#E5E7EB"
    BORDER_LIGHT = "#D1D5DB"
    TEXT = "#111827"
    MUTED = "#6B7280"
    WEAK = "#9CA3AF"
    BLUE = "#2563EB"
    BLUE_HOVER = "#1D4ED8"
    BLUE_MUTED = "#DBEAFE"
    INDIGO = "#4F46E5"
    SUCCESS = "#16A34A"
    WARNING = "#D97706"
    DANGER = "#DC2626"
    HOVER = "#F3F4F6"
    SELECTED = "#2563EB"
    INPUT = "#FFFFFF"
    TOOLBAR = "#FFFFFF"


def apply_theme_palette(theme_name: str) -> None:
    source = LightPalette if theme_name == "浅色" else DarkPalette
    for attr in dir(source):
        if not attr.startswith("_") and not callable(getattr(source, attr)):
            setattr(Palette, attr, getattr(source, attr))


class Radius:
    CARD = 10
    CONTROL = 8
    PILL = 20
    FULL = 999


from core.app_identity import APP_NAME, APP_VERSION  # noqa: F401 — 统一品牌常量

FONT_FAMILY = '"Microsoft YaHei UI", "Segoe UI", "PingFang SC", sans-serif'

_FONT_PX = {"小": "12px", "默认": "13px", "大": "15px"}
_FONT_SCALE = {"小": 0.88, "默认": 1.0, "大": 1.18}
_COMPACT_SPACING = {"normal": "8px", "compact": "4px"}
_COMPACT_PADDING = {"normal": "12px", "compact": "6px"}


def _scale_font_sizes(qss: str, scale: float) -> str:
    if abs(scale - 1.0) < 0.01:
        return qss

    def _repl(match: re.Match) -> str:
        px = int(match.group(1))
        return f"font-size: {max(9, round(px * scale))}px"

    return re.sub(r"font-size:\s*(\d+)px", _repl, qss)


def preview_font_size_px() -> str:
    from core.settings_store import get_setting
    return _FONT_PX.get(get_setting("font_size_level", "默认"), "13px")


def load_stylesheet() -> str:
    from core.settings_store import get_bool, get_setting

    qss = style_path().read_text(encoding="utf-8")
    for attr in dir(Palette):
        if not attr.startswith("_") and not callable(getattr(Palette, attr)):
            qss = qss.replace(f"@{attr}", getattr(Palette, attr))

    font_level = get_setting("font_size_level", "默认")
    qss = qss.replace("@BASE_FONT", _FONT_PX.get(font_level, "13px"))
    qss = _scale_font_sizes(qss, _FONT_SCALE.get(font_level, 1.0))

    compact = get_bool("compact_mode", False)
    qss = qss.replace("@LAYOUT_SPACING", _COMPACT_SPACING["compact" if compact else "normal"])
    qss = qss.replace("@CARD_PADDING", _COMPACT_PADDING["compact" if compact else "normal"])
    return qss


from utils.path_utils import resource_path


def style_path() -> Path:
    return resource_path("ui", "styles.qss")

from __future__ import annotations

import re

from pathlib import Path


class DarkPalette:
    """Premium agent dark — warm charcoal, soft contrast, Cursor/Linear-inspired."""
    BG = "#131316"
    SIDEBAR = "#0E0E11"
    SURFACE = "#18181D"
    CARD = "#1D1D24"
    CARD_HOVER = "#26262F"
    BORDER = "#2C2C38"
    BORDER_LIGHT = "#3A3A48"
    TEXT = "#EDEDF2"
    MUTED = "#9B9BA8"
    WEAK = "#6B6B78"
    BLUE = "#6B93FF"
    BLUE_HOVER = "#5684FF"
    BLUE_MUTED = "#1E2A4A"
    INDIGO = "#8B7CF6"
    ACCENT = "#6B93FF"
    ACCENT_SOFT = "#252540"
    SUCCESS = "#34D399"
    WARNING = "#FBBF24"
    DANGER = "#F87171"
    HOVER = "#22222A"
    SELECTED = "#3D5AFE"
    INPUT = "#16161A"
    TOOLBAR = "#141418"
    GLOW = "rgba(107, 147, 255, 0.35)"


class Palette(DarkPalette):
    """Active theme colors; updated by apply_theme_palette()."""
    pass


class LightPalette:
    """Warm light — editorial cream tones."""
    BG = "#F4F3EF"
    SIDEBAR = "#FAFAF8"
    SURFACE = "#FFFFFF"
    CARD = "#FFFFFF"
    CARD_HOVER = "#F5F4F0"
    BORDER = "#E4E3DE"
    BORDER_LIGHT = "#D5D4CF"
    TEXT = "#1C1B18"
    MUTED = "#6B6960"
    WEAK = "#9C9890"
    BLUE = "#4F7DF5"
    BLUE_HOVER = "#3D6FE8"
    BLUE_MUTED = "#E8EEFC"
    INDIGO = "#6D5CE7"
    ACCENT = "#4F7DF5"
    ACCENT_SOFT = "#EDE9FE"
    SUCCESS = "#059669"
    WARNING = "#D97706"
    DANGER = "#DC2626"
    HOVER = "#EEEDEA"
    SELECTED = "#4F7DF5"
    INPUT = "#FFFFFF"
    TOOLBAR = "#FAFAF8"
    GLOW = "rgba(79, 125, 245, 0.25)"


def apply_theme_palette(theme_name: str) -> None:
    source = LightPalette if theme_name == "浅色" else DarkPalette
    for attr in dir(source):
        if not attr.startswith("_") and not callable(getattr(source, attr)):
            setattr(Palette, attr, getattr(source, attr))


class Radius:
    XS = 6
    SM = 10
    MD = 14
    LG = 18
    XL = 22
    PILL = 999


from core.app_identity import APP_NAME, APP_VERSION  # noqa: F401 — 统一品牌常量

FONT_FAMILY = '"Microsoft YaHei UI", "Segoe UI Variable", "Segoe UI", "PingFang SC", sans-serif'
FONT_MONO = '"Cascadia Code", "Cascadia Mono", "Consolas", monospace'

_FONT_PX = {"小": "13px", "默认": "14px", "大": "16px"}
_FONT_SCALE = {"小": 0.92, "默认": 1.0, "大": 1.12}
_COMPACT_SPACING = {"normal": "10px", "compact": "5px"}
_COMPACT_PADDING = {"normal": "14px", "compact": "8px"}


def _scale_font_sizes(qss: str, scale: float) -> str:
    if abs(scale - 1.0) < 0.01:
        return qss

    def _repl(match: re.Match) -> str:
        px = int(match.group(1))
        return f"font-size: {max(10, round(px * scale))}px"

    return re.sub(r"font-size:\s*(\d+)px", _repl, qss)


def preview_font_size_px() -> str:
    from core.settings_store import get_setting
    return _FONT_PX.get(get_setting("font_size_level", "默认"), "14px")


def load_stylesheet() -> str:
    from core.settings_store import get_bool, get_setting

    qss = style_path().read_text(encoding="utf-8")
    refresh_path = resource_path("ui", "styles_agent_refresh.qss")
    if refresh_path.is_file():
        qss = qss + "\n\n" + refresh_path.read_text(encoding="utf-8")

    for attr in dir(Palette):
        if not attr.startswith("_") and not callable(getattr(Palette, attr)):
            qss = qss.replace(f"@{attr}", getattr(Palette, attr))

    for attr in dir(Radius):
        if not attr.startswith("_"):
            qss = qss.replace(f"@RADIUS_{attr}", f"{getattr(Radius, attr)}px")

    qss = qss.replace("@FONT_FAMILY", FONT_FAMILY)
    qss = qss.replace("@FONT_MONO", FONT_MONO)

    font_level = get_setting("font_size_level", "默认")
    qss = qss.replace("@BASE_FONT", _FONT_PX.get(font_level, "14px"))
    qss = _scale_font_sizes(qss, _FONT_SCALE.get(font_level, 1.0))

    compact = get_bool("compact_mode", False)
    qss = qss.replace("@LAYOUT_SPACING", _COMPACT_SPACING["compact" if compact else "normal"])
    qss = qss.replace("@CARD_PADDING", _COMPACT_PADDING["compact" if compact else "normal"])
    return qss


from utils.path_utils import resource_path


def style_path() -> Path:
    return resource_path("ui", "styles.qss")

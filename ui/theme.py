from __future__ import annotations

import re

from pathlib import Path


class DarkPalette:
    """Soft premium dark — charcoal surfaces, crisp text, restrained agent accents."""
    BG = "#101114"
    SIDEBAR = "#0B0C0F"
    SURFACE = "#171920"
    CARD = "#1C1F27"
    CARD_HOVER = "#242833"
    BORDER = "#2A2E3A"
    BORDER_LIGHT = "#3A4050"
    TEXT = "#F7F8FB"
    MUTED = "#C2C8D4"
    WEAK = "#8790A3"
    BLUE = "#7AA2FF"
    BLUE_HOVER = "#93B5FF"
    BLUE_MUTED = "#213252"
    INDIGO = "#A18CFF"
    ACCENT = "#7AA2FF"
    ACCENT_SOFT = "#222B3F"
    SUCCESS = "#5EE0B7"
    WARNING = "#F6C76B"
    DANGER = "#FF7E8A"
    HOVER = "#222631"
    SELECTED = "#476FFF"
    INPUT = "#151821"
    TOOLBAR = "#12141A"
    GLOW = "rgba(122, 162, 255, 0.32)"


class Palette(DarkPalette):
    """Active theme colors; updated by apply_theme_palette()."""
    pass


class LightPalette:
    """Soft light — clean workstation surfaces without harsh white glare."""
    BG = "#F6F7F9"
    SIDEBAR = "#FFFFFF"
    SURFACE = "#FFFFFF"
    CARD = "#FFFFFF"
    CARD_HOVER = "#F1F4F8"
    BORDER = "#E0E5EE"
    BORDER_LIGHT = "#CBD3E1"
    TEXT = "#171A21"
    MUTED = "#5F6877"
    WEAK = "#8D96A6"
    BLUE = "#416FF4"
    BLUE_HOVER = "#2E5FEA"
    BLUE_MUTED = "#E8EEFF"
    INDIGO = "#7765E8"
    ACCENT = "#416FF4"
    ACCENT_SOFT = "#EEF3FF"
    SUCCESS = "#059669"
    WARNING = "#D97706"
    DANGER = "#DC2626"
    HOVER = "#EDF1F7"
    SELECTED = "#4F7DF5"
    INPUT = "#FFFFFF"
    TOOLBAR = "#FBFCFE"
    GLOW = "rgba(79, 125, 245, 0.25)"


def apply_theme_palette(theme_name: str) -> None:
    source = LightPalette if theme_name == "浅色" else DarkPalette
    for attr in dir(source):
        if not attr.startswith("_") and not callable(getattr(source, attr)):
            setattr(Palette, attr, getattr(source, attr))


class Radius:
    XS = 8
    SM = 12
    MD = 16
    LG = 20
    XL = 26
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

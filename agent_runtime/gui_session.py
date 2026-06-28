"""Track active GUI target window across tool calls and permission pauses."""

from __future__ import annotations

from agent_runtime.gui_hooks import focus_window_by_title

_active_window: str | None = None


def set_active_window(title_keyword: str) -> None:
    global _active_window
    title = (title_keyword or "").strip()
    if title:
        _active_window = title


def get_active_window() -> str | None:
    return _active_window


def clear_active_window() -> None:
    global _active_window
    _active_window = None


def resolve_window_title(explicit: str = "") -> str:
    explicit = (explicit or "").strip()
    if explicit:
        return explicit
    return _active_window or ""


def ensure_target_foreground(title_keyword: str = "") -> str | None:
    """Bring the target window to foreground before click/keyboard ops."""
    title = resolve_window_title(title_keyword)
    if not title:
        return None
    result = focus_window_by_title(title)
    if result.startswith("未找到"):
        return None
    set_active_window(title)
    return result

from __future__ import annotations

from core.app_identity import APP_NAME
from ui.dialogs.buddy_message import (
    ask_confirm as _ask_confirm,
    show_error,
    show_info as _show_info,
    show_success,
    show_warning as _show_warning,
)


def info(parent, text: str, *, title: str = APP_NAME, detail: str = "") -> None:
    _show_info(parent, title, text, detail=detail)


def warn(parent, text: str, *, title: str = "注意", detail: str = "") -> None:
    _show_warning(parent, title, text, detail=detail)


def confirm(parent, text: str, *, title: str = "请确认", detail: str = "") -> bool:
    return _ask_confirm(parent, title, text, detail=detail)


def success(parent, text: str, *, title: str = "成功", detail: str = "") -> None:
    show_success(parent, title, text, detail=detail)


def error(parent, text: str, *, title: str = "错误", detail: str = "") -> None:
    show_error(parent, title, text, detail=detail)

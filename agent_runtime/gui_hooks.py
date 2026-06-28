"""Thread-safe hooks for GUI automation (focus windows, optional prepare callbacks)."""

from __future__ import annotations

import ctypes
import time
from ctypes import wintypes
from typing import Callable

from agent_runtime.dialog_guard import dismiss_blocking_dialogs

_prepare_callbacks: list[Callable[[], None]] = []
_last_prepare_at: float = 0.0
_last_dismiss_at: float = 0.0


def register_prepare_callback(callback: Callable[[], None]) -> None:
    if callback not in _prepare_callbacks:
        _prepare_callbacks.append(callback)


def prepare_for_gui_automation(wait_seconds: float = 0.2) -> None:
    """Run registered UI hooks before screen/keyboard/mouse ops."""
    global _last_prepare_at, _last_dismiss_at
    # Clear blocking error dialogs before GUI ops (rate-limited).
    now = time.time()
    if now - _last_dismiss_at > 0.3:
        try:
            dismiss_blocking_dialogs()
        except Exception:
            pass
        _last_dismiss_at = now

    for cb in _prepare_callbacks:
        try:
            cb()
        except Exception:
            pass
    elapsed = time.time() - _last_prepare_at
    if elapsed < 0.8:
        time.sleep(0.05)
    elif wait_seconds > 0:
        time.sleep(wait_seconds)
    _last_prepare_at = time.time()


def focus_window_by_title(keyword: str) -> str:
    """Bring the first visible window whose title contains *keyword* to the foreground."""
    keyword = (keyword or "").strip()
    if not keyword:
        return "错误：请提供窗口标题关键词"

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    matches: list[tuple[int, str]] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def _enum_cb(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value.strip()
        if not title:
            return True
        if keyword.lower() in title.lower():
            matches.append((int(hwnd), title))
        return True

    user32.EnumWindows(_enum_cb, 0)
    if not matches:
        return f"未找到标题包含「{keyword}」的可见窗口。请尝试更短的关键词，如「酷狗」「微信」。"

    hwnd, title = matches[0]
    _force_foreground(hwnd, user32, kernel32)
    time.sleep(0.15)
    return f"已将窗口置于前台: {title}"


def _force_foreground(hwnd: int, user32, kernel32) -> None:
    SW_RESTORE = 9
    fg_hwnd = user32.GetForegroundWindow()
    fg_tid = user32.GetWindowThreadProcessId(fg_hwnd, None)
    target_tid = user32.GetWindowThreadProcessId(hwnd, None)
    cur_tid = kernel32.GetCurrentThreadId()

    user32.AttachThreadInput(cur_tid, target_tid, True)
    user32.AttachThreadInput(fg_tid, target_tid, True)
    user32.ShowWindow(hwnd, SW_RESTORE)
    user32.SetForegroundWindow(hwnd)
    user32.BringWindowToTop(hwnd)
    user32.AttachThreadInput(cur_tid, target_tid, False)
    user32.AttachThreadInput(fg_tid, target_tid, False)

"""Auto-dismiss blocking Windows error dialogs during agent runs."""

from __future__ import annotations

import os
import time

_STD_DIALOG_CLASS = "#32770"

_DISMISS_LABELS = frozenset({
    "确定", "ok", "关闭", "是", "yes",
})

_SKIP_TITLE_KEYWORDS = (
    "dna", "work agent", "用户账户控制", "user account control",
)

_ERROR_CUES = (
    "找不到", "错误", "error", "failed", "无法", "请检查",
    "warning", "警告", "不存在", "拒绝访问", "access denied",
    "not found", "异常", "失败",
)

_BLOCK_DIALOG_CUES = (
    "另存为", "保存", "save as", "打开", "browse", "浏览文件夹",
    "选择", "select", "打印", "print",
)

_own_pid = os.getpid()


def dismiss_blocking_dialogs(max_dialogs: int = 5) -> list[str]:
    """Click OK on modal system error dialogs. Returns log lines for each dismissed dialog."""
    try:
        import uiautomation as auto
    except ImportError:
        return []

    dismissed: list[str] = []
    for _ in range(max_dialogs):
        entry = _dismiss_one_dialog(auto)
        if not entry:
            break
        dismissed.append(entry)
        time.sleep(0.12)
    return dismissed


def format_dismiss_note(dismissed: list[str]) -> str:
    if not dismissed:
        return ""
    return " [系统弹窗已自动关闭: " + "; ".join(dismissed) + "]"


def _dismiss_one_dialog(auto) -> str | None:
    candidates: list = []
    for win in auto.GetRootControl().GetChildren():
        if not _is_candidate_dialog(win, auto):
            continue
        candidates.append(win)

    if not candidates:
        return None

    win = candidates[0]
    for candidate in candidates:
        if (candidate.ClassName or "") == _STD_DIALOG_CLASS:
            win = candidate
            break

    btn = _find_dismiss_button(win, auto)
    if not btn:
        return None

    title = (win.Name or "").strip() or "(系统对话框)"
    try:
        btn.Click(simulateMove=False)
    except Exception:
        try:
            btn.Invoke()
        except Exception:
            return None
    return title


def _is_candidate_dialog(win, auto) -> bool:
    try:
        if not win.Exists(0, 0):
            return False
    except Exception:
        return False

    if _should_skip_window(win):
        return False

    cls = win.ClassName or ""
    if cls != _STD_DIALOG_CLASS:
        return False

    if _find_dismiss_button(win, auto) is None:
        return False

    text_blob = _collect_text(win)
    lower = text_blob.lower()
    if any(cue in lower for cue in _BLOCK_DIALOG_CUES):
        return False
    if any(cue in lower for cue in (c.lower() for c in _ERROR_CUES)):
        return True

    # Explorer / system small dialogs: single OK, short title, no save/open cues
    try:
        rect = win.BoundingRectangle
        w = rect.right - rect.left
        h = rect.bottom - rect.top
        if 0 < w < 700 and 0 < h < 450:
            return True
    except Exception:
        pass
    return False


def _should_skip_window(win) -> bool:
    try:
        if win.ProcessId == _own_pid:
            return True
    except Exception:
        pass

    name = (win.Name or "").lower()
    return any(kw in name for kw in _SKIP_TITLE_KEYWORDS)


def _collect_text(ctrl, depth: int = 0, max_depth: int = 5) -> str:
    if depth > max_depth:
        return ""
    parts: list[str] = []
    try:
        name = ctrl.Name or ""
        if name:
            parts.append(name)
        for child in ctrl.GetChildren():
            parts.append(_collect_text(child, depth + 1, max_depth))
    except Exception:
        pass
    return " ".join(parts)


def _normalize_label(label: str) -> str:
    return label.replace("&", "").strip().lower()


def _find_dismiss_button(win, auto):
    buttons: list[tuple[str, object]] = []
    queue = [win]
    while queue:
        ctrl = queue.pop(0)
        try:
            if isinstance(ctrl, auto.ButtonControl):
                label = (ctrl.Name or "").strip()
                if _normalize_label(label) in _DISMISS_LABELS:
                    buttons.append((label, ctrl))
            queue.extend(ctrl.GetChildren())
        except Exception:
            continue

    if not buttons:
        return None

    for prefer in ("确定", "OK", "ok"):
        for label, btn in buttons:
            if _normalize_label(label) == prefer.lower():
                return btn
    return buttons[0][1]

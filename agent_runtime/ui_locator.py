"""Local UI element location: Windows UIA first, OCR fallback.

No LLM / vision API required — finds controls by accessibility tree or on-screen text.
WorkBuddy-style: local scripts locate, Agent orchestrates.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass
class LocateResult:
    x: int
    y: int
    method: str
    detail: str


def _rect_center(rect) -> tuple[int, int] | None:
    try:
        left, top, right, bottom = rect.left, rect.top, rect.right, rect.bottom
    except AttributeError:
        return None
    if right <= left or bottom <= top:
        return None
    return (left + right) // 2, (top + bottom) // 2


def _match_text(haystack: str, needle: str, exact: bool) -> bool:
    if not needle:
        return False
    hay = (haystack or "").strip()
    if exact:
        return hay == needle
    return needle.lower() in hay.lower()


def _is_search_like_target(target: str) -> bool:
    t = (target or "").lower()
    return any(k in target or k in t for k in ("搜索", "search", "查找", "query"))


def _resolve_window(window_title: str):
    try:
        import uiautomation as auto
    except ImportError:
        return None, None

    if window_title:
        for win in auto.GetRootControl().GetChildren():
            name = win.Name or ""
            if _match_text(name, window_title, exact=False):
                return win, auto
        return None, auto
    return auto.GetForegroundControl(), auto


def find_first_edit_in_window(window_title: str = "") -> LocateResult | None:
    """Find the first Edit control in a window (common for search boxes in sparse UIA trees)."""
    try:
        import uiautomation as auto
    except ImportError:
        return None

    window, _ = _resolve_window(window_title)
    if window is None:
        return None

    queue = [window]
    seen: set[int] = set()
    while queue:
        ctrl = queue.pop(0)
        cid = id(ctrl)
        if cid in seen:
            continue
        seen.add(cid)

        if isinstance(ctrl, auto.EditControl):
            rect = ctrl.BoundingRectangle
            center = _rect_center(rect)
            if center:
                name = ctrl.Name or ""
                return LocateResult(
                    x=center[0], y=center[1],
                    method="uia-edit",
                    detail=f"EditControl: {name or '(无标题)'}",
                )

        try:
            queue.extend(ctrl.GetChildren())
        except Exception:
            pass
    return None


def find_via_uia(
    target: str,
    window_title: str = "",
    control_type: str = "",
    exact: bool = False,
) -> LocateResult | None:
    """Find a control through Windows UI Automation (fast, best for native apps)."""
    try:
        import uiautomation as auto
    except ImportError:
        return None

    window, _ = _resolve_window(window_title)
    if window is None:
        return None

    type_map = {
        "edit": auto.EditControl,
        "button": auto.ButtonControl,
        "text": auto.TextControl,
        "menu": auto.MenuItemControl,
        "combo": auto.ComboBoxControl,
    }
    ControlCls = type_map.get(control_type.lower()) if control_type else None

    candidates: list = []
    queue = [window]
    seen: set[int] = set()
    while queue:
        ctrl = queue.pop(0)
        cid = id(ctrl)
        if cid in seen:
            continue
        seen.add(cid)

        if ControlCls and not isinstance(ctrl, ControlCls):
            pass
        else:
            name = ctrl.Name or ""
            aid = getattr(ctrl, "AutomationId", "") or ""
            if _match_text(name, target, exact) or _match_text(aid, target, exact):
                rect = ctrl.BoundingRectangle
                center = _rect_center(rect)
                if center:
                    return LocateResult(
                        x=center[0], y=center[1],
                        method="uia",
                        detail=f"{ctrl.ControlTypeName}: {name or aid}",
                    )
            if not control_type and _match_text(name, target, exact):
                rect = ctrl.BoundingRectangle
                center = _rect_center(rect)
                if center:
                    candidates.append((ctrl, center, name or aid))

        try:
            queue.extend(ctrl.GetChildren())
        except Exception:
            pass

    if candidates:
        ctrl, center, label = candidates[0]
        return LocateResult(
            x=center[0], y=center[1],
            method="uia",
            detail=f"{ctrl.ControlTypeName}: {label}",
        )
    return None


def find_via_ocr(
    target: str,
    window_title: str = "",
    exact: bool = False,
) -> LocateResult | None:
    """Find on-screen text with local OCR (for custom-drawn / Electron UIs)."""
    try:
        import numpy as np
        from PIL import ImageGrab
        from rapidocr_onnxruntime import RapidOCR
    except ImportError:
        return None

    region = None
    offset_x, offset_y = 0, 0
    if window_title:
        win_rect = _window_rect_by_title(window_title)
        if win_rect:
            region = win_rect
            offset_x, offset_y = win_rect[0], win_rect[1]

    img = ImageGrab.grab(bbox=region) if region else ImageGrab.grab()
    ocr = RapidOCR()
    result, _ = ocr(np.array(img))
    if not result:
        return None

    best = None
    best_score = -1.0
    for box, text, score in result:
        if not _match_text(text, target, exact):
            continue
        xs = [p[0] for p in box]
        ys = [p[1] for p in box]
        cx = int(sum(xs) / len(xs)) + offset_x
        cy = int(sum(ys) / len(ys)) + offset_y
        conf = float(score or 0)
        if conf >= best_score:
            best_score = conf
            best = LocateResult(
                x=cx, y=cy, method="ocr",
                detail=f"OCR「{text.strip()}」({conf:.2f})",
            )
    return best


def _window_rect_by_title(keyword: str) -> tuple[int, int, int, int] | None:
    try:
        import uiautomation as auto
    except ImportError:
        return None
    for win in auto.GetRootControl().GetChildren():
        name = win.Name or ""
        if keyword.lower() in name.lower():
            r = win.BoundingRectangle
            return (r.left, r.top, r.right, r.bottom)
    return None


def locate_ui_element(
    target: str,
    window_title: str = "",
    control_type: str = "",
    exact: bool = False,
    method: str = "auto",
) -> LocateResult | None:
    """Try UIA then OCR. Search-like targets prefer Edit controls when UIA name match fails."""
    target = (target or "").strip()
    if not target:
        return None

    if method == "uia":
        return find_via_uia(target, window_title, control_type, exact)
    if method == "ocr":
        return find_via_ocr(target, window_title, exact)

    hit = find_via_uia(target, window_title, control_type, exact)
    if hit:
        return hit

    if control_type == "edit" or _is_search_like_target(target):
        hit = find_first_edit_in_window(window_title)
        if hit:
            return hit

    return find_via_ocr(target, window_title, exact)


def format_locate_failure(
    target: str,
    window_title: str,
    *,
    uia_tried: bool = False,
    ocr_tried: bool = False,
) -> str:
    hints = []
    try:
        import uiautomation  # noqa: F401
    except ImportError:
        hints.append("UIA: pip install uiautomation")

    try:
        import rapidocr_onnxruntime  # noqa: F401
    except ImportError:
        hints.append("OCR: pip install rapidocr-onnxruntime pillow")

    tags = []
    if uia_tried:
        tags.append("UIA_MISS")
    if ocr_tried:
        tags.append("OCR_MISS")
    prefix = "+".join(tags) if tags else "UI_MISS"

    extra = f"（可选依赖：{'；'.join(hints)}）" if hints else ""
    win = f"窗口「{window_title}」内" if window_title else "当前屏幕"
    return f"{prefix}: 未在{win}找到「{target}」。可换关键词、加 window_title、或 screen_capture(for_vision=true) 诊断{extra}"


def locate_with_diagnostics(
    target: str,
    window_title: str = "",
    control_type: str = "",
    exact: bool = False,
    method: str = "auto",
) -> tuple[LocateResult | None, str]:
    """Locate element and return structured failure reason if not found."""
    target = (target or "").strip()
    if not target:
        return None, "UI_MISS: target 为空"

    if method == "uia":
        hit = find_via_uia(target, window_title, control_type, exact)
        if hit:
            return hit, ""
        return None, format_locate_failure(target, window_title, uia_tried=True)

    if method == "ocr":
        hit = find_via_ocr(target, window_title, exact)
        if hit:
            return hit, ""
        return None, format_locate_failure(target, window_title, ocr_tried=True)

    uia_hit = find_via_uia(target, window_title, control_type, exact)
    if uia_hit:
        return uia_hit, ""

    if control_type == "edit" or _is_search_like_target(target):
        edit_hit = find_first_edit_in_window(window_title)
        if edit_hit:
            return edit_hit, ""

    ocr_hit = find_via_ocr(target, window_title, exact)
    if ocr_hit:
        return ocr_hit, ""

    return None, format_locate_failure(
        target, window_title, uia_tried=True, ocr_tried=True,
    )

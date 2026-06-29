"""Apply user settings at runtime (UI, agent, tools, security)."""

from __future__ import annotations

import ctypes
import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING

from core.settings_store import get_bool, get_setting
from db.database import insert, query_all

if TYPE_CHECKING:
    from PySide6.QtWidgets import QApplication, QMainWindow

logger = logging.getLogger(__name__)

FILE_TOOLS = frozenset({
    "file_read", "file_write", "file_list", "file_delete", "code_create",
    "office_word_create", "office_excel_create", "office_ppt_create",
})
NETWORK_TOOLS = frozenset({
    "open_url", "web_search", "web_fetch", "skill_install", "image_analyze",
})
MCP_TOOL_PREFIX = "mcp__"
EXEC_TOOLS = frozenset({"shell_run"})  # 仅 shell 受「命令执行」限制；software_launch 是启动本地应用
APP_LAUNCH_TOOLS = frozenset({"software_launch", "find_application"})

_FONT_SIZES = {"小": 9, "默认": 11, "大": 13}


def get_workspace_path() -> str:
    path = get_setting("workspace_path", "").strip()
    if path and Path(path).is_dir():
        return path
    from utils.path_utils import exports_dir
    exports = exports_dir()
    return str(exports) if exports.exists() else ""


def send_key_is_ctrl_enter() -> bool:
    return get_setting("send_key", "Enter") == "Ctrl+Enter"


def plugins_disabled() -> bool:
    return get_bool("disable_all_plugins", False)


GUI_TOOLS = frozenset({
    "keyboard_type", "mouse_click", "ui_click", "ui_locate", "window_focus",
    "screen_capture", "hotkey_press", "list_apps",
})


def gui_automation_enabled() -> bool:
    return get_bool("enable_gui_automation", False)


def is_tool_allowed(tool_name: str) -> str | None:
    """Return error message if blocked, else None."""
    if tool_name in GUI_TOOLS and not gui_automation_enabled():
        return (
            "错误：GUI 自动化（实验性）未开启。"
            "请在 设置 → 安全中心 开启「GUI 自动化（实验性）」，"
            "或改用 office_* / library_search 等文件级工具完成任务。"
        )
    if tool_name.startswith(MCP_TOOL_PREFIX):
        if not get_bool("enable_mcp", True):
            return "错误：MCP 工具已在设置 → 安全中心关闭。"
        if not get_bool("allow_network", True):
            return "错误：MCP 需要网络访问权限，请在安全中心开启「网络访问」。"
    if tool_name in FILE_TOOLS and not get_bool("allow_file_access", True):
        return "错误：文件访问权限已在安全中心关闭。"
    if tool_name in NETWORK_TOOLS and not get_bool("allow_network", True):
        return "错误：网络访问权限已在安全中心关闭。"
    if tool_name in EXEC_TOOLS and not get_bool("allow_exec", False):
        return "错误：命令执行权限已在安全中心关闭，请在设置中开启「命令执行权限」。"
    if tool_name in APP_LAUNCH_TOOLS and not get_bool("allow_app_launch", True):
        return "错误：应用启动权限已在安全中心关闭，请在设置 → 安全中心中开启「应用启动权限」。"
    if tool_name in GUI_TOOLS and is_workstation_locked() and not get_bool("lock_screen_remote", False):
        return "错误：系统已锁屏，且未开启「锁屏远程」权限。"
    return None


def is_workstation_locked() -> bool:
    try:
        user32 = ctypes.windll.user32
        hd = user32.OpenInputDesktop(0, False, 0)
        if hd:
            user32.CloseDesktop(hd)
            return False
        return True
    except Exception:
        return False


def build_agent_settings_suffix() -> str:
    parts: list[str] = []

    user = get_setting("user_name", "").strip()
    if user:
        parts.append(f"\n\n用户称呼：{user}")

    memories = query_all(
        "SELECT memory_key, memory_value FROM memories ORDER BY id DESC LIMIT 20"
    )
    if memories:
        lines = ["\n\n## 用户记忆（请遵循）"]
        for m in memories:
            lines.append(f"- {m['memory_key']}：{m['memory_value']}")
        parts.append("\n".join(lines))

    if get_bool("disable_agent_teams", False):
        parts.append(
            "\n\n当前为**单智能体模式**：不要拆分任务给其他智能体或协作团队，由你独立完成。"
        )

    if get_bool("proactive_suggestions", True):
        parts.append(
            "\n\n在合适时**主动**提出下一步建议、风险提醒或更优方案，不要只被动等待指令。"
        )

    if get_bool("verbose_reply", False):
        parts.append("\n\n回复时请**详细**说明步骤、原因与结果，便于用户理解。")
    else:
        parts.append("\n\n回复尽量**简洁**明了，避免冗长重复。")

    if not gui_automation_enabled():
        parts.append(
            "\n\n**GUI 自动化已关闭（默认）**：不要调用 ui_click、keyboard_type、screen_capture 等。"
            "优先用资料库检索 + 生成 Word/PPT/Excel 交付结果；用户若要操控桌面软件，"
            "说明可在设置中开启实验性 GUI 能力。"
        )

    return "".join(parts)


_MEMORY_TRIGGERS = ("请记住", "记住我", "我喜欢", "我偏好", "我习惯", "以后请", "默认用", "别忘了")


def try_extract_chat_memory(user_text: str, assistant_text: str = "") -> None:
    if not get_bool("generate_chat_memory", True):
        return
    text = (user_text or "").strip()
    if not text or len(text) < 4:
        return
    if not any(t in text for t in _MEMORY_TRIGGERS):
        return

    key = "对话偏好"
    val = text[:500]
    m = re.search(r"(请记住|记住我|记住)(.+)", text)
    if m:
        val = m.group(2).strip()[:500]
        key = "用户要求"

    existing = query_all(
        "SELECT id FROM memories WHERE memory_key=? AND memory_value=? LIMIT 1",
        (key, val),
    )
    if existing:
        return
    insert("memories", {
        "memory_key": key[:100],
        "memory_value": val,
        "memory_type": "chat",
    })
    logger.info("Extracted chat memory: %s", key)


def play_notification_sound() -> None:
    if not get_bool("enable_sound", True):
        return
    try:
        import winsound
        winsound.MessageBeep(winsound.MB_OK)
    except Exception:
        pass


def reload_skill_handlers() -> None:
    from agent_runtime.tool_executor import load_installed_handlers
    load_installed_handlers()


def check_remote_catalog_on_startup() -> None:
    """Fetch remote expert/skill catalog manifest if URL is configured."""
    from core.remote_catalog import ensure_catalog_url_configured, fetch_remote_catalog

    ensure_catalog_url_configured()
    try:
        fetch_remote_catalog()
    except Exception as exc:
        logger.warning("Remote catalog startup fetch failed: %s", exc)


def check_skill_updates_on_startup() -> None:
    """Re-install Skill packages that have a source_url (best-effort)."""
    check_remote_catalog_on_startup()
    try:
        from agent_runtime.skill_installer import refresh_installed_bundled_skills
        from agent_runtime.tool_executor import load_installed_handlers

        refreshed = refresh_installed_bundled_skills()
        if refreshed:
            logger.info("Bundled skills refreshed: %s", ", ".join(refreshed))
            load_installed_handlers()
    except Exception as exc:
        logger.debug("Bundled skill refresh skipped: %s", exc)
    if not get_bool("skill_auto_update", True):
        return
    rows = query_all(
        "SELECT id, source_url, package_name FROM installed_skill_packages "
        "WHERE enabled=1 AND source_url IS NOT NULL AND source_url != ''"
    )
    if not rows:
        return
    logger.info("Skill update check: %d package(s) with source_url.", len(rows))
    from agent_runtime.skill_installer import install_skill_from_url
    from agent_runtime.tool_executor import load_installed_handlers

    for row in rows:
        url = (row.get("source_url") or "").strip()
        if not url:
            continue
        try:
            install_skill_from_url(url)
            logger.info("Skill updated from URL: %s", row.get("package_name"))
        except Exception as exc:
            logger.warning("Skill update failed for %s: %s", row.get("package_name"), exc)
    try:
        load_installed_handlers()
    except Exception:
        pass


def apply_app_settings(
    app: QApplication,
    main_window: QMainWindow | None = None,
    *,
    startup: bool = False,
    apply_theme: bool = True,
) -> None:
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QFont, QGuiApplication
    from PySide6.QtWidgets import QWidget
    from ui.theme import apply_app_palette, apply_theme_palette, load_stylesheet

    theme = get_setting("theme", "深色")
    if theme == "跟随系统":
        hints = QGuiApplication.styleHints()
        if hasattr(hints, "colorScheme"):
            scheme = hints.colorScheme()
            theme = "浅色" if scheme == Qt.ColorScheme.Light else "深色"
        else:
            theme = "深色"

    level = get_setting("font_size_level", "默认")
    pt = _FONT_SIZES.get(level, 10)
    font = QFont()
    font.setFamily("Microsoft YaHei UI")
    font.setPointSize(pt)
    font.setHintingPreference(QFont.HintingPreference.PreferFullHinting)

    if apply_theme:
        apply_theme_palette(theme)
        apply_app_palette(app, theme)
        app.setStyleSheet(load_stylesheet())
        app.setFont(font)

    compact = get_bool("compact_mode", False)
    app.setProperty("compact_mode", compact)

    if main_window is not None:
        main_window.setStyleSheet("")
        _apply_main_window_settings(main_window, refresh_files=not startup)
        from ui.i18n import retranslate_all_settings_dialogs
        retranslate_all_settings_dialogs()
        for widget in main_window.findChildren(QWidget):
            widget.setFont(font)
            widget.style().unpolish(widget)
            widget.style().polish(widget)
        main_window.update()
        app.processEvents()


def _apply_main_window_settings(window: QMainWindow, *, refresh_files: bool = True) -> None:
    from ui.i18n import retranslate_main_window

    retranslate_main_window(window)

    ws = get_workspace_path()
    if hasattr(window, "_results"):
        window._results.set_workspace(ws, refresh=refresh_files)

    user = get_setting("user_name", "").strip() or "🐷🐷Buddy 用户"
    if hasattr(window, "_sidebar") and hasattr(window._sidebar, "set_user_name"):
        window._sidebar.set_user_name(user)

    pos = get_setting("sidebar_position", "左侧")
    if hasattr(window, "_splitter") and hasattr(window, "_sidebar"):
        _apply_sidebar_position(window._splitter, window._sidebar, pos)

    if hasattr(window, "_conversation") and hasattr(window._conversation, "apply_send_key_setting"):
        window._conversation.apply_send_key_setting()

    compact = get_bool("compact_mode", False)
    _apply_compact_layout(window, compact)

    if hasattr(window, "_refresh_status"):
        window._refresh_status()
        _show_applied_hint(window)


def _apply_compact_layout(window: QMainWindow, compact: bool) -> None:
    spacing = 4 if compact else 8
    for name in ("_sidebar", "_conversation", "_results"):
        panel = getattr(window, name, None)
        if panel is None:
            continue
        panel.setProperty("compact", "true" if compact else "false")
        layout = panel.layout()
        if layout is not None:
            layout.setSpacing(spacing)
        panel.style().unpolish(panel)
        panel.style().polish(panel)


def _show_applied_hint(window: QMainWindow) -> None:
    from ui.i18n import t

    if not hasattr(window, "_status"):
        return
    level = get_setting("font_size_level", "默认")
    theme = get_setting("theme", "深色")
    compact = t("settings.common.on") if get_bool("compact_mode", False) else t("settings.common.off")
    window._status.showMessage(
        t("status_applied", font=level, theme=theme, compact=compact),
        4000,
    )


def _apply_sidebar_position(splitter, sidebar, position: str) -> None:
    idx = -1
    for i in range(splitter.count()):
        if splitter.widget(i) is sidebar:
            idx = i
            break
    if idx < 0:
        return
    want_right = position == "右侧"
    at_right = idx == splitter.count() - 1
    if want_right and not at_right:
        sidebar.setParent(None)
        splitter.addWidget(sidebar)
    elif not want_right and idx != 0:
        sidebar.setParent(None)
        splitter.insertWidget(0, sidebar)

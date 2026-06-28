"""应用顶栏菜单：编辑 / 窗口 / 帮助 及子项。"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QMenu, QMessageBox, QPushButton, QWidget

from core.app_identity import APP_NAME, APP_VERSION
from ui.i18n import t


def _menu_button(text: str, menu: QMenu, parent: QWidget | None = None) -> QPushButton:
    btn = QPushButton(text, parent)
    btn.setObjectName("AppMenuButton")
    btn.setCursor(Qt.PointingHandCursor)
    btn.setMenu(menu)
    return btn


def build_app_menus(window) -> dict[str, QPushButton]:
    """为 MainWindow 构建顶栏菜单按钮，返回 {key: button}。"""
    window._menu_i18n: list[tuple] = []

    def _act(menu, key: str, shortcut=None, handler=None):
        action = menu.addAction(t(key))
        window._menu_i18n.append((action, key))
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
        if handler:
            action.triggered.connect(handler)
        return action

    app_menu = QMenu(window)
    _act(app_menu, "menu_settings", "Ctrl+,", window._open_settings)
    app_menu.addSeparator()
    _act(app_menu, "menu_about", handler=lambda: QMessageBox.information(
        window, t("settings.title"),
        f"{APP_NAME} {APP_VERSION}\n\n"
        + ("Local AI desktop agent." if t("menu_settings") == "Settings…" else "本地 AI 桌面 Agent。"),
    ))
    _act(app_menu, "menu_quit", "Alt+F4", window.close)

    edit_menu = QMenu(window)
    _act(edit_menu, "menu_undo", "Ctrl+Z", lambda: window._conversation._input.undo())
    _act(edit_menu, "menu_cut", "Ctrl+X", lambda: window._conversation._input.cut())
    _act(edit_menu, "menu_copy", "Ctrl+C", lambda: window._conversation._input.copy())
    _act(edit_menu, "menu_paste", "Ctrl+V", lambda: window._conversation._input.paste())
    edit_menu.addSeparator()
    _act(edit_menu, "menu_clear_input", handler=lambda: window._conversation._input.clear())
    _act(edit_menu, "menu_clear_chat", handler=window._conversation.clear_messages_view)

    win_menu = QMenu(window)
    _act(win_menu, "menu_toggle_sidebar", "Ctrl+B", window._toggle_sidebar)
    _act(win_menu, "menu_toggle_results", "Ctrl+R", window._toggle_results)
    win_menu.addSeparator()
    _act(win_menu, "menu_maximize", handler=window._toggle_maximize)
    _act(win_menu, "menu_minimize", handler=window.showMinimized)

    help_menu = QMenu(window)
    _act(help_menu, "menu_help_doc", "F1", lambda: open_settings_page(window, 10))
    _act(help_menu, "menu_feedback", handler=lambda: submit_feedback(window))
    _act(help_menu, "menu_logs", handler=lambda: open_settings_page(window, 10))
    help_menu.addSeparator()
    _act(help_menu, "menu_open_settings", handler=window._open_settings)

    window._menu_buttons = {
        "app": ("menu_app", _menu_button(t("menu_app"), app_menu, window)),
        "edit": ("menu_edit", _menu_button(t("menu_edit"), edit_menu, window)),
        "window": ("menu_window", _menu_button(t("menu_window"), win_menu, window)),
        "help": ("menu_help", _menu_button(t("menu_help"), help_menu, window)),
    }
    return {k: v[1] for k, v in window._menu_buttons.items()}


def retranslate_app_menus(window) -> None:
    if not hasattr(window, "_menu_i18n"):
        return
    for action, key in window._menu_i18n:
        action.setText(t(key))
    if hasattr(window, "_menu_buttons"):
        for _key, (i18n_key, btn) in window._menu_buttons.items():
            btn.setText(t(i18n_key))


def open_settings_page(window, page_index: int) -> None:
    from ui.dialogs.open_settings import open_settings_dialog
    open_settings_dialog(window, page_index)


def submit_feedback(window) -> None:
    from PySide6.QtWidgets import QInputDialog
    from core.settings_store import set_setting
    from utils.path_utils import data_dir

    text, ok = QInputDialog.getMultiLineText(window, t("menu_feedback"), "")
    if not ok or not text.strip():
        return
    from datetime import datetime
    fb_dir = data_dir() / "feedback"
    fb_dir.mkdir(parents=True, exist_ok=True)
    path = fb_dir / f"feedback_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    path.write_text(text.strip(), encoding="utf-8")
    set_setting("last_feedback", text.strip()[:500])
    QMessageBox.information(window, t("menu_feedback"), str(path))

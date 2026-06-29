from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal, QSize, QTimer
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QFileDialog, QFrame, QHBoxLayout,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QPlainTextEdit,
    QPushButton, QScrollArea, QSlider, QStackedWidget, QVBoxLayout, QWidget,
)

from core.app_identity import APP_NAME, APP_VERSION
from core.settings_store import get_bool, get_setting, set_bool, set_setting
from db.database import delete, execute, insert, query_all, query_one, update
from rag.indexer import index_file, index_standard
from utils.file_utils import copy_to_folder
from utils.path_utils import app_root, data_dir, log_file

from ui.frameless_dialog import on_frameless_dialog_show, setup_frameless_dialog
from ui.i18n import register_settings_dialog, t, unregister_settings_dialog


_PROVIDER_PRESETS = {
    "DeepSeek V4 Pro": ("https://api.deepseek.com", "deepseek-v4-pro"),
    "DeepSeek (旧 ID)": ("https://api.deepseek.com", "deepseek-chat"),
    "OpenAI": ("https://api.openai.com/v1", "gpt-4o"),
    "Kimi/Moonshot": ("https://api.moonshot.cn/v1", "moonshot-v1-8k"),
    "智谱GLM": ("https://open.bigmodel.cn/api/paas/v4", "glm-4"),
    "腾讯混元": ("https://api.hunyuan.cloud.tencent.com/v1", "hunyuan-pro"),
    "Ollama本地": ("http://localhost:11434/v1", "llama3"),
}


class _ToggleSwitch(QCheckBox):
    """Modern toggle switch; styled via #ToggleSwitch in styles.qss."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ToggleSwitch")
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setFixedSize(48, 28)
        self.setText("")


def _setting_row(title: str, description: str, control: QWidget) -> QWidget:
    """Build a standard settings row: title + description on left, control on right."""
    row = QWidget()
    row.setObjectName("SettingsRow")
    row.setFixedHeight(56)
    hl = QHBoxLayout(row)
    hl.setContentsMargins(0, 4, 0, 4)
    hl.setSpacing(16)
    text_col = QVBoxLayout()
    text_col.setSpacing(2)
    title_label = QLabel(title)
    title_label.setObjectName("SettingsRowTitle")
    text_col.addWidget(title_label)
    if description:
        desc_label = QLabel(description)
        desc_label.setObjectName("SettingsRowDesc")
        desc_label.setWordWrap(True)
        text_col.addWidget(desc_label)
    hl.addLayout(text_col, 1)
    hl.addWidget(control, 0, Qt.AlignRight | Qt.AlignVCenter)
    return row


def _section_title(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("SettingsSection")
    return label


def _make_scroll_page() -> tuple[QScrollArea, QVBoxLayout]:
    """Create a scrollable page wrapper."""
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QScrollArea.NoFrame)
    inner = QWidget()
    layout = QVBoxLayout(inner)
    layout.setContentsMargins(28, 28, 28, 28)
    layout.setSpacing(12)
    scroll.setWidget(inner)
    return scroll, layout


class SettingsDialog(QDialog):
    settings_changed = Signal(str)

    _NAV_KEYS = [
        "settings.nav.account",
        "settings.nav.system",
        "settings.nav.agent",
        "settings.nav.memory",
        "settings.nav.models",
        "settings.nav.tools",
        "settings.nav.assistant",
        "settings.nav.personalization",
        "settings.nav.data",
        "settings.nav.security",
        "settings.nav.help",
    ]

    _FEEDBACK_KEYS = {
        "language": "settings.feedback.language",
        "font_size_level": "settings.feedback.font",
        "compact_mode": "settings.feedback.compact",
        "send_key": "settings.feedback.send_key",
        "theme": "settings.feedback.theme",
        "sidebar_position": "settings.feedback.sidebar",
        "workspace_path": "settings.feedback.workspace",
        "user_name": "settings.feedback.username",
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("SettingsDialog")
        self.resize(960, 640)
        self._i18n_widgets: list[tuple] = []

        _, body = setup_frameless_dialog(self, title_key="settings.title", min_size=(960, 640))
        layout = QHBoxLayout(body)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._nav = QListWidget()
        self._nav.setObjectName("SettingsNav")
        self._nav.setFixedWidth(180)
        for key in self._NAV_KEYS:
            item = QListWidgetItem(t(key))
            item.setSizeHint(QSize(180, 40))
            self._nav.addItem(item)
        self._nav.currentRowChanged.connect(self._switch_page)
        layout.addWidget(self._nav)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        self._feedback = QLabel("")
        self._feedback.setObjectName("SettingsFeedback")
        self._feedback.setFixedHeight(32)
        self._feedback.setAlignment(Qt.AlignCenter)
        right_layout.addWidget(self._feedback)

        self._feedback_timer = QTimer(self)
        self._feedback_timer.setSingleShot(True)
        self._feedback_timer.timeout.connect(self._clear_feedback)
        self._catalog_save_timer = QTimer(self)
        self._catalog_save_timer.setSingleShot(True)
        self._catalog_save_timer.timeout.connect(self._save_catalog_urls_from_editor)

        self._stack = QStackedWidget()
        self._stack.addWidget(self._page_account())
        self._stack.addWidget(self._page_system())
        self._stack.addWidget(self._page_agent())
        self._stack.addWidget(self._page_memory())
        self._stack.addWidget(self._page_models())
        self._stack.addWidget(self._page_tools())
        self._stack.addWidget(self._page_assistant())
        self._stack.addWidget(self._page_personalization())
        self._stack.addWidget(self._page_data())
        self._stack.addWidget(self._page_security())
        self._stack.addWidget(self._page_help())
        right_layout.addWidget(self._stack, 1)
        layout.addWidget(right, 1)
        self._nav.setCurrentRow(0)

        self._preview_card = None
        register_settings_dialog(self)
        self.destroyed.connect(lambda: unregister_settings_dialog(self))

    def showEvent(self, event) -> None:
        super().showEvent(event)
        on_frameless_dialog_show(self)

    def closeEvent(self, event) -> None:
        self._feedback_timer.stop()
        self._catalog_save_timer.stop()
        super().closeEvent(event)

    def _clear_feedback(self) -> None:
        try:
            from shiboken6 import isValid
            if isValid(self._feedback):
                self._feedback.setText("")
        except RuntimeError:
            pass

    def _save_catalog_urls_from_editor(self) -> None:
        editor = getattr(self, "_catalog_urls_editor", None)
        if editor is None:
            return
        try:
            from shiboken6 import isValid
            if not isValid(editor):
                return
            self._save_setting("remote_catalog_url", editor.toPlainText().strip())
        except RuntimeError:
            pass

    def _schedule_catalog_urls_save(self) -> None:
        self._catalog_save_timer.start(600)

    def _register_i18n(self, widget, key: str, method: str = "setText") -> None:
        self._i18n_widgets.append((widget, method, key))

    def retranslate_ui(self) -> None:
        if hasattr(self, "_frameless_title_label"):
            self._frameless_title_label.setText(t("settings.title"))
        for i, key in enumerate(self._NAV_KEYS):
            item = self._nav.item(i)
            if item:
                item.setText(t(key))
        for widget, method, key in self._i18n_widgets:
            try:
                if widget is not None and widget.isVisible() is not None:
                    getattr(widget, method)(t(key))
            except RuntimeError:
                continue
        self._refresh_preview_card()
        if hasattr(self, "_models_path_label"):
            self._models_path_label.setText(
                t("settings.models.config_path", path=str(data_dir() / "models.json"))
            )
        if hasattr(self, "_font_size_label"):
            from core.settings_store import get_setting
            level = get_setting("font_size_level", "默认")
            font_labels = {
                "小": "settings.system.font_small",
                "默认": "settings.font.default",
                "大": "settings.system.font_large",
            }
            self._font_size_label.setText(t(font_labels.get(level, "settings.font.default")))
        self.style().unpolish(self)
        self.style().polish(self)

    def _notify(self, key: str = "") -> None:
        self.settings_changed.emit(key)
        self._show_feedback(key)
        if key == "language":
            self.retranslate_ui()
            parent = self.parent()
            if parent and hasattr(parent, "apply_settings"):
                parent.apply_settings(key)

    def _show_feedback(self, key: str) -> None:
        fb_key = self._FEEDBACK_KEYS.get(key, "settings.feedback.saved")
        text = t(fb_key)
        self._feedback.setText(f"✓ {text}")
        self._feedback_timer.start(2500)
        self._refresh_preview_card()

    def _save_setting(self, key: str, value: str, setting_type: str = "string") -> None:
        set_setting(key, value, setting_type)
        self._notify(key)

    def _save_bool(self, key: str, value: bool) -> None:
        set_bool(key, value)
        self._notify(key)

    def _on_mcp_enable_toggled(self, checked: bool) -> None:
        self._save_bool("enable_mcp", checked)
        import threading
        from agent_runtime.mcp_client import refresh_mcp_tools, shutdown_mcp

        def work():
            if checked:
                refresh_mcp_tools()
            else:
                shutdown_mcp()
            self._refresh_mcp_tools_ui()

        if hasattr(self, "_mcp_tools_layout"):
            threading.Thread(target=work, daemon=True).start()

    def open_page(self, index: int) -> None:
        if 0 <= index < self._stack.count():
            self._nav.setCurrentRow(index)

    def _refresh_preview_card(self) -> None:
        if not getattr(self, "_preview_sample", None):
            return
        from core.settings_store import get_setting
        from ui.theme import preview_font_size_px

        px = preview_font_size_px()
        self._preview_sample.setStyleSheet(f"font-size: {px};")
        card = getattr(self, "_preview_card", None)
        if card:
            card.style().unpolish(card)
            card.style().polish(card)

    def _switch_page(self, index: int) -> None:
        self._stack.setCurrentIndex(index)
        self._refresh_preview_card()

    # ------------------------------------------------------------------
    # 1. 账户管理
    # ------------------------------------------------------------------
    def _page_account(self) -> QWidget:
        scroll, layout = _make_scroll_page()
        sec = _section_title(t("settings.nav.account"))
        self._register_i18n(sec, "settings.nav.account")
        layout.addWidget(sec)

        name = get_setting("user_name", "").strip() or t("default_user")

        ver_label = QLabel(f"{APP_NAME} {APP_VERSION}")
        ver_label.setObjectName("SettingsAccountVersion")
        layout.addWidget(ver_label)

        layout.addSpacing(20)

        username_title = QLabel(t("settings.account.username"))
        username_title.setObjectName("SettingsRowTitle")
        self._register_i18n(username_title, "settings.account.username")
        layout.addWidget(username_title)

        username_desc = QLabel(t("settings.account.username_desc"))
        username_desc.setObjectName("SettingsRowDesc")
        self._register_i18n(username_desc, "settings.account.username_desc")
        layout.addWidget(username_desc)

        layout.addSpacing(8)

        self._username_edit = QLineEdit(name)
        self._username_edit.setObjectName("SettingsUsernameInput")
        self._username_edit.setPlaceholderText(t("settings.account.username_ph"))
        self._register_i18n(self._username_edit, "settings.account.username_ph", "setPlaceholderText")
        self._username_edit.setMinimumWidth(360)
        self._username_edit.setMaximumWidth(480)
        self._username_edit.setFixedHeight(36)
        self._username_edit.setClearButtonEnabled(True)
        self._username_edit.returnPressed.connect(self._save_username_from_edit)
        self._username_edit.editingFinished.connect(self._save_username_from_edit)
        layout.addWidget(self._username_edit)

        layout.addStretch()
        return scroll

    def _save_username_from_edit(self) -> None:
        if not hasattr(self, "_username_edit"):
            return
        value = self._username_edit.text().strip()
        if not value:
            value = t("default_user")
            self._username_edit.setText(value)
        current = get_setting("user_name", "").strip()
        if value == current or (not current and value == t("default_user")):
            return
        self._save_setting("user_name", value)

    # ------------------------------------------------------------------
    # 2. 系统设置
    # ------------------------------------------------------------------
    def _page_system(self) -> QWidget:
        scroll, layout = _make_scroll_page()
        sec = _section_title(t("settings.nav.system"))
        self._register_i18n(sec, "settings.nav.system")
        layout.addWidget(sec)

        lang = QComboBox()
        lang.setFixedWidth(160)
        lang.addItems([t("settings.lang.zh"), t("settings.lang.en")])
        lang.blockSignals(True)
        stored = get_setting("language", "简体中文")
        lang.setCurrentText(t("settings.lang.en") if stored == "English" else t("settings.lang.zh"))
        lang.blockSignals(False)
        lang.currentTextChanged.connect(
            lambda v: self._save_setting(
                "language", "English" if v == t("settings.lang.en") else "简体中文"
            )
        )
        layout.addWidget(_setting_row(
            t("settings.system.language"), t("settings.system.language_desc"), lang
        ))

        font_slider = QSlider(Qt.Horizontal)
        font_slider.setFixedWidth(160)
        font_slider.setRange(0, 2)
        size_map = {"小": 0, "默认": 1, "大": 2}
        reverse_map = {0: "小", 1: "默认", 2: "大"}
        font_labels = {
            "小": "settings.system.font_small",
            "默认": "settings.font.default",
            "大": "settings.system.font_large",
        }
        current_font = get_setting("font_size_level", "默认")
        font_slider.setValue(size_map.get(current_font, 1))
        font_size_label = QLabel(t(font_labels.get(current_font, "settings.font.default")))
        font_size_label.setObjectName("SettingsRowDesc")
        font_size_label.setFixedWidth(48)
        self._font_size_label = font_size_label

        def _on_font_slider(v):
            level = reverse_map.get(v, "默认")
            font_size_label.setText(t(font_labels.get(level, "settings.font.default")))
            self._save_setting("font_size_level", level)

        font_slider.valueChanged.connect(_on_font_slider)
        font_ctrl = QHBoxLayout()
        small_lbl = QLabel(t("settings.system.font_small"))
        large_lbl = QLabel(t("settings.system.font_large"))
        self._register_i18n(small_lbl, "settings.system.font_small")
        self._register_i18n(large_lbl, "settings.system.font_large")
        fc = QWidget()
        fc_layout = QHBoxLayout(fc)
        fc_layout.setContentsMargins(0, 0, 0, 0)
        fc_layout.setSpacing(8)
        fc_layout.addWidget(small_lbl)
        fc_layout.addWidget(font_slider)
        fc_layout.addWidget(font_size_label)
        fc_layout.addWidget(large_lbl)
        layout.addWidget(_setting_row(
            t("settings.system.font"), t("settings.system.font_desc"), fc
        ))

        preview = QFrame()
        preview.setObjectName("SettingsPreviewCard")
        pl = QVBoxLayout(preview)
        pl.setContentsMargins(14, 10, 14, 10)
        preview_title = QLabel(t("settings.system.preview"))
        self._register_i18n(preview_title, "settings.system.preview")
        pl.addWidget(preview_title)
        self._preview_sample = QLabel(t("settings.system.preview_text"))
        self._preview_sample.setObjectName("SettingsPreviewText")
        self._preview_sample.setWordWrap(True)
        self._register_i18n(self._preview_sample, "settings.system.preview_text")
        pl.addWidget(self._preview_sample)
        layout.addWidget(preview)
        self._preview_card = preview

        compact_toggle = _ToggleSwitch()
        compact_toggle.blockSignals(True)
        compact_toggle.setChecked(get_bool("compact_mode", False))
        compact_toggle.blockSignals(False)
        compact_toggle.toggled.connect(lambda v: self._save_bool("compact_mode", v))
        layout.addWidget(_setting_row(
            t("settings.system.compact"), t("settings.system.compact_desc"), compact_toggle
        ))

        send_key = QComboBox()
        send_key.setFixedWidth(160)
        send_key.addItems([t("settings.send.enter"), t("settings.send.ctrl_enter")])
        send_key.blockSignals(True)
        sk = get_setting("send_key", "Enter")
        send_key.setCurrentText(
            t("settings.send.ctrl_enter") if sk == "Ctrl+Enter" else t("settings.send.enter")
        )
        send_key.blockSignals(False)
        send_key.currentTextChanged.connect(
            lambda v: self._save_setting(
                "send_key", "Ctrl+Enter" if v == t("settings.send.ctrl_enter") else "Enter"
            )
        )
        layout.addWidget(_setting_row(
            t("settings.system.send_key"), t("settings.system.send_key_desc"), send_key
        ))

        auto_update = _ToggleSwitch()
        auto_update.setChecked(get_bool("skill_auto_update", True))
        auto_update.toggled.connect(lambda v: self._save_bool("skill_auto_update", v))
        layout.addWidget(_setting_row(
            t("settings.system.skill_update"), t("settings.system.skill_update_desc"), auto_update
        ))

        from core.remote_catalog import DEFAULT_REMOTE_CATALOG_URL

        catalog_urls = QPlainTextEdit(
            get_setting("remote_catalog_url", "") or DEFAULT_REMOTE_CATALOG_URL
        )
        catalog_urls.setPlaceholderText(
            "每行一个 URL，或用逗号分隔\n" + DEFAULT_REMOTE_CATALOG_URL
        )
        catalog_urls.setMaximumHeight(72)
        catalog_urls.setMinimumWidth(280)
        self._catalog_urls_editor = catalog_urls
        catalog_urls.textChanged.connect(self._schedule_catalog_urls_save)
        layout.addWidget(_setting_row(
            "远程目录 URL",
            "专家中心 Skill/专家 清单；可填多个 JSON 地址，启动时合并拉取并缓存 1 小时",
            catalog_urls,
        ))

        auto_install = _ToggleSwitch()
        auto_install.setChecked(get_bool("auto_install_low_risk", False))
        auto_install.toggled.connect(lambda v: self._save_bool("auto_install_low_risk", v))
        layout.addWidget(_setting_row(
            t("settings.system.auto_install"), t("settings.system.auto_install_desc"), auto_install
        ))

        lock_remote = _ToggleSwitch()
        lock_remote.setChecked(get_bool("lock_screen_remote", False))
        lock_remote.toggled.connect(lambda v: self._save_bool("lock_screen_remote", v))
        layout.addWidget(_setting_row(
            t("settings.system.lock_remote"), t("settings.system.lock_remote_desc"), lock_remote
        ))

        workspace_edit = QLineEdit(get_setting("workspace_path", ""))
        workspace_edit.setPlaceholderText(t("settings.system.workspace_ph"))
        self._register_i18n(workspace_edit, "settings.system.workspace_ph", "setPlaceholderText")
        workspace_edit.setMinimumWidth(200)
        browse_btn = QPushButton(t("settings.browse"))
        self._register_i18n(browse_btn, "settings.browse")
        browse_btn.setFixedWidth(72)
        workspace_edit.editingFinished.connect(
            lambda: self._save_setting("workspace_path", workspace_edit.text().strip())
        )
        browse_btn.clicked.connect(
            lambda: self._pick_dir(workspace_edit, "workspace_path")
        )
        ws_ctrl = QWidget()
        ws_layout = QHBoxLayout(ws_ctrl)
        ws_layout.setContentsMargins(0, 0, 0, 0)
        ws_layout.setSpacing(6)
        ws_layout.addWidget(workspace_edit, 1)
        ws_layout.addWidget(browse_btn)
        layout.addWidget(_setting_row(
            t("settings.system.workspace"), t("settings.system.workspace_desc"), ws_ctrl
        ))

        layout.addStretch()
        return scroll

    # ------------------------------------------------------------------
    # 3. 智能体设置
    # ------------------------------------------------------------------
    def _page_agent(self) -> QWidget:
        scroll, layout = _make_scroll_page()
        layout.addWidget(_section_title("智能体设置"))

        disable_plugins = _ToggleSwitch()
        disable_plugins.setChecked(get_bool("disable_all_plugins", False))
        disable_plugins.toggled.connect(lambda v: self._save_bool("disable_all_plugins", v))
        layout.addWidget(_setting_row(
            "禁用全部插件",
            "关闭后，智能体将不会加载任何插件，适用于排查插件冲突或提升启动速度",
            disable_plugins,
        ))

        disable_teams = _ToggleSwitch()
        disable_teams.setChecked(get_bool("disable_agent_teams", False))
        disable_teams.toggled.connect(lambda v: self._save_bool("disable_agent_teams", v))
        layout.addWidget(_setting_row(
            "禁用智能体团队",
            "关闭后，任务将只由单个智能体处理，不会分配给协作团队",
            disable_teams,
        ))

        layout.addStretch()
        return scroll

    # ------------------------------------------------------------------
    # 4. 记忆
    # ------------------------------------------------------------------
    def _page_memory(self) -> QWidget:
        scroll, layout = _make_scroll_page()
        layout.addWidget(_section_title("记忆"))

        desc = QLabel("系统会记住你的偏好和习惯，帮助提供更个性化的体验")
        desc.setStyleSheet("font-size: 12px; color: #9CA3AF; padding-bottom: 8px;")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        gen_memory = _ToggleSwitch()
        gen_memory.setChecked(get_bool("generate_chat_memory", True))
        gen_memory.toggled.connect(lambda v: self._save_bool("generate_chat_memory", v))
        layout.addWidget(_setting_row(
            "生成对话记忆", "从对话中自动提取偏好并记忆", gen_memory
        ))

        layout.addSpacing(8)
        mem_label = QLabel("已保存的记忆")
        mem_label.setStyleSheet("font-size: 13px; font-weight: bold; color: #F0F2F5;")
        layout.addWidget(mem_label)

        self._memory_list_widget = QWidget()
        self._memory_list_layout = QVBoxLayout(self._memory_list_widget)
        self._memory_list_layout.setContentsMargins(0, 0, 0, 0)
        self._memory_list_layout.setSpacing(4)
        layout.addWidget(self._memory_list_widget)
        self._refresh_memories()

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        add_mem_btn = QPushButton("＋ 添加记忆")
        add_mem_btn.setFixedWidth(120)
        add_mem_btn.setProperty("variant", "primary")
        add_mem_btn.clicked.connect(self._add_memory)
        import_btn = QPushButton("从文件导入")
        import_btn.setFixedWidth(120)
        import_btn.setProperty("variant", "secondary")
        import_btn.clicked.connect(self._import_memory)
        clear_mem_btn = QPushButton("清空全部")
        clear_mem_btn.setFixedWidth(100)
        clear_mem_btn.setStyleSheet("color: #EF4444;")
        clear_mem_btn.clicked.connect(self._clear_memories)
        btn_row.addWidget(add_mem_btn)
        btn_row.addWidget(import_btn)
        btn_row.addWidget(clear_mem_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        layout.addStretch()
        return scroll

    def _refresh_memories(self) -> None:
        layout = self._memory_list_layout
        while layout.count():
            child = layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        memories = query_all("SELECT * FROM memories ORDER BY id DESC")
        if not memories:
            empty = QLabel("暂无记忆 — 点击「添加记忆」手动录入或从对话中自动提取")
            empty.setStyleSheet("font-size: 12px; color: #6b7280; padding: 12px;")
            layout.addWidget(empty)
            return

        for m in memories:
            row = QWidget()
            row.setFixedHeight(44)
            row.setObjectName("SettingsListCard")
            rl = QHBoxLayout(row)
            rl.setContentsMargins(12, 4, 8, 4)
            rl.setSpacing(8)
            key_lbl = QLabel(m.get("memory_key", ""))
            key_lbl.setStyleSheet("font-size: 12px; font-weight: bold; color: #F0F2F5;")
            val_lbl = QLabel(m.get("memory_value", ""))
            val_lbl.setStyleSheet("font-size: 12px; color: #9CA3AF;")
            val_lbl.setWordWrap(False)
            type_lbl = QLabel(m.get("memory_type", "preference"))
            type_lbl.setStyleSheet(
                "font-size: 10px; color: #3B82F6; background: #1E3A5F;"
                "border-radius: 3px; padding: 1px 4px;"
            )
            del_btn = QPushButton("×")
            del_btn.setFixedSize(24, 24)
            del_btn.setCursor(Qt.PointingHandCursor)
            del_btn.setStyleSheet("font-size: 14px; color: #EF4444; background: transparent; border: none;")
            mid = m["id"]
            del_btn.clicked.connect(lambda _, _id=mid: self._delete_memory(_id))
            rl.addWidget(key_lbl)
            rl.addWidget(val_lbl, 1)
            rl.addWidget(type_lbl)
            rl.addWidget(del_btn)
            layout.addWidget(row)

    def _add_memory(self) -> None:
        from PySide6.QtWidgets import QInputDialog
        key, ok = QInputDialog.getText(self, "添加记忆", "记忆标题（如：偏好、习惯）:")
        if not ok or not key.strip():
            return
        val, ok2 = QInputDialog.getText(self, "添加记忆", f"「{key.strip()}」的内容:")
        if not ok2 or not val.strip():
            return
        insert("memories", {
            "memory_key": key.strip()[:100],
            "memory_value": val.strip()[:500],
            "memory_type": "manual",
        })
        self._refresh_memories()

    def _delete_memory(self, mem_id: int) -> None:
        delete("memories", mem_id)
        self._refresh_memories()

    def _clear_memories(self) -> None:
        from PySide6.QtWidgets import QMessageBox
        reply = QMessageBox.question(
            self, "确认清空", "确定要清空所有记忆吗？此操作不可恢复。",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            execute("DELETE FROM memories")
            self._refresh_memories()

    def _import_memory(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "选择记忆文件", "",
            "JSON/Text (*.json *.txt *.md);;All (*.*)"
        )
        if not path:
            return
        try:
            text = Path(path).read_text(encoding="utf-8", errors="ignore")
            for line in text.strip().splitlines():
                line = line.strip().lstrip("•-").strip()
                if not line:
                    continue
                if ":" in line:
                    key, val = line.split(":", 1)
                else:
                    key, val = "imported", line
                insert("memories", {
                    "memory_key": key.strip()[:100],
                    "memory_value": val.strip()[:500],
                    "memory_type": "imported",
                })
            self._refresh_memories()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # 5. 模型
    # ------------------------------------------------------------------
    def _page_models(self) -> QWidget:
        scroll, layout = _make_scroll_page()
        layout.addWidget(_section_title(t("settings.nav.models")))

        layout.addSpacing(4)
        custom_label = QLabel(t("settings.models.custom"))
        self._register_i18n(custom_label, "settings.models.custom")
        custom_label.setObjectName("SettingsCardTitle")
        layout.addWidget(custom_label)

        config_path = data_dir() / "models.json"
        path_label = QLabel(t("settings.models.config_path", path=str(config_path)))
        self._models_path_label = path_label
        path_label.setObjectName("SettingsCardMuted")
        layout.addWidget(path_label)

        add_btn = QPushButton(t("settings.models.add"))
        self._register_i18n(add_btn, "settings.models.add")
        add_btn.setFixedWidth(120)
        add_btn.setProperty("variant", "primary")
        add_btn.clicked.connect(self._add_model)
        layout.addWidget(add_btn)

        layout.addSpacing(12)
        saved_label = QLabel(t("settings.models.saved"))
        self._register_i18n(saved_label, "settings.models.saved")
        saved_label.setObjectName("SettingsCardTitle")
        layout.addWidget(saved_label)

        self._model_list_widget = QWidget()
        self._model_list_layout = QVBoxLayout(self._model_list_widget)
        self._model_list_layout.setContentsMargins(0, 0, 0, 0)
        self._model_list_layout.setSpacing(4)
        layout.addWidget(self._model_list_widget)

        self._refresh_models()

        layout.addStretch()
        return scroll

    def _refresh_models(self) -> None:
        layout = self._model_list_layout
        while layout.count():
            child = layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        models = query_all(
            "SELECT * FROM models ORDER BY is_default DESC, enabled DESC, id DESC"
        )
        for m in models:
            row = QWidget()
            row.setFixedHeight(48)
            row.setObjectName("SettingsListCard")
            rl = QHBoxLayout(row)
            rl.setContentsMargins(12, 4, 12, 4)
            rl.setSpacing(12)

            provider = QLabel(m.get("provider_name", ""))
            provider.setObjectName("SettingsCardMuted")
            name = QLabel(m.get("model_name", ""))
            name.setObjectName("SettingsCardTitle")
            default_tag = QLabel("")
            if m.get("is_default"):
                default_tag.setText(t("settings.models.default"))
                default_tag.setObjectName("SettingsBadge")

            edit_btn = QPushButton(t("settings.models.edit"))
            edit_btn.setFixedSize(48, 28)
            mid = m["id"]
            edit_btn.clicked.connect(lambda checked=False, _id=mid: self._edit_model(_id))

            default_btn = QPushButton(t("settings.models.set_default"))
            default_btn.setFixedSize(72, 28)
            if not m.get("is_default"):
                default_btn.clicked.connect(lambda checked=False, _id=mid: self._set_default_model(_id))

            del_btn = QPushButton(t("settings.models.delete"))
            del_btn.setFixedSize(48, 28)
            del_btn.setObjectName("SettingsDangerBtn")
            del_btn.clicked.connect(lambda checked=False, _id=mid: self._delete_model(_id))

            rl.addWidget(provider)
            rl.addWidget(name)
            rl.addWidget(default_tag)
            rl.addStretch()
            if not m.get("is_default"):
                rl.addWidget(default_btn)
            rl.addWidget(edit_btn)
            rl.addWidget(del_btn)

            layout.addWidget(row)

    def _add_model(self) -> None:
        dlg = _ModelDialog(self)
        if dlg.exec():
            data = dlg.values()
            data["enabled"] = 1
            insert("models", data)
            self._refresh_models()

    def _edit_model(self, model_id: int) -> None:
        row = query_one("SELECT * FROM models WHERE id=?", (model_id,))
        if not row:
            return
        dlg = _ModelDialog(self, row)
        if dlg.exec():
            update("models", model_id, dlg.values())
            self._refresh_models()

    def _delete_model(self, model_id: int) -> None:
        delete("models", model_id)
        self._refresh_models()

    def _set_default_model(self, model_id: int) -> None:
        execute("UPDATE models SET is_default=0")
        execute("UPDATE models SET is_default=1, enabled=1 WHERE id=?", (model_id,))
        self._refresh_models()
        self._notify("models")

    # ------------------------------------------------------------------
    # 6. 工具管理
    # ------------------------------------------------------------------
    def _page_tools(self) -> QWidget:
        scroll, layout = _make_scroll_page()
        layout.addWidget(_section_title("工具管理"))

        desc = QLabel("查看和管理 Agent 可调用的工具。禁用的工具不会传给 AI 模型。")
        desc.setStyleSheet("font-size: 12px; color: #9CA3AF; padding-bottom: 8px;")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        layout.addWidget(_section_title("内置工具"))

        from agent_runtime.tool_definitions import TOOLS, TOOL_RISK_LEVELS
        import json as _json

        disabled_raw = get_setting("disabled_tools", "[]")
        try:
            disabled_set = set(_json.loads(disabled_raw))
        except Exception:
            disabled_set = set()

        TOOL_ICONS = {
            "shell_run": "⚡", "file_read": "📖", "file_write": "✏️",
            "file_list": "📂", "file_delete": "🗑️", "software_launch": "🚀",
            "open_url": "🌐", "web_search": "🔍", "web_fetch": "📡", "office_word_create": "📄", "office_excel_create": "📊",
            "office_ppt_create": "📑", "code_create": "💻", "keyboard_type": "⌨️",
            "mouse_click": "🖱️", "screen_capture": "📸", "list_apps": "📋", "skill_install": "📦",
        }
        RISK_STYLE = {
            "low": "color:#22c55e; background:#052e16;",
            "medium": "color:#f59e0b; background:#422006;",
            "high": "color:#ef4444; background:#450a0a;",
        }
        RISK_CN = {"low": "低", "medium": "中", "high": "高"}

        self._tool_toggles: dict[str, _ToggleSwitch] = {}

        for tool_def in TOOLS:
            func = tool_def.get("function", {})
            name = func.get("name", "")
            tool_desc = func.get("description", "")
            risk = TOOL_RISK_LEVELS.get(name, "low")
            icon = TOOL_ICONS.get(name, "🔧")

            row = QWidget()
            row.setFixedHeight(52)
            row.setObjectName("SettingsListCard")
            rl = QHBoxLayout(row)
            rl.setContentsMargins(12, 4, 12, 4)
            rl.setSpacing(10)

            icon_lbl = QLabel(icon)
            icon_lbl.setFixedWidth(24)
            icon_lbl.setStyleSheet("font-size:16px; background:transparent;")
            rl.addWidget(icon_lbl)

            info = QVBoxLayout()
            info.setSpacing(1)
            name_lbl = QLabel(name)
            name_lbl.setStyleSheet("font-size:13px; font-weight:bold; color:#F0F2F5;")
            info.addWidget(name_lbl)
            desc_lbl = QLabel(tool_desc[:60] + ("…" if len(tool_desc) > 60 else ""))
            desc_lbl.setStyleSheet("font-size:11px; color:#9CA3AF;")
            info.addWidget(desc_lbl)
            rl.addLayout(info, 1)

            risk_lbl = QLabel(RISK_CN.get(risk, risk))
            risk_lbl.setFixedWidth(28)
            risk_lbl.setAlignment(Qt.AlignCenter)
            risk_lbl.setStyleSheet(
                f"font-size:11px; border-radius:4px; padding:2px 6px; "
                f"{RISK_STYLE.get(risk, '')}"
            )
            rl.addWidget(risk_lbl)

            toggle = _ToggleSwitch()
            toggle.setChecked(name not in disabled_set)
            toggle.toggled.connect(lambda checked, n=name: self._on_tool_toggled(n, checked))
            self._tool_toggles[name] = toggle
            rl.addWidget(toggle)

            layout.addWidget(row)

        layout.addSpacing(16)
        layout.addWidget(_section_title("已安装工具"))

        self._installed_tools_widget = QWidget()
        self._installed_tools_layout = QVBoxLayout(self._installed_tools_widget)
        self._installed_tools_layout.setContentsMargins(0, 0, 0, 0)
        self._installed_tools_layout.setSpacing(4)
        layout.addWidget(self._installed_tools_widget)
        self._refresh_installed_tools()

        install_btn = QPushButton("从 URL 安装新工具")
        install_btn.setFixedWidth(180)
        install_btn.setProperty("variant", "primary")
        install_btn.clicked.connect(self._install_tool_from_url)
        layout.addWidget(install_btn)

        layout.addSpacing(16)
        layout.addWidget(_section_title("MCP 外部工具"))

        mcp_desc = QLabel(
            "9 mainstream MCP presets (Filesystem, GitHub, Fetch, …) pre-configured. "
            "Enable in the dialog; add custom servers under the Custom tab."
        )
        mcp_desc.setStyleSheet("font-size: 12px; color: #9CA3AF;")
        mcp_desc.setWordWrap(True)
        layout.addWidget(mcp_desc)

        self._mcp_status_label = QLabel("")
        self._mcp_status_label.setObjectName("MutedLabel")
        self._mcp_status_label.setWordWrap(True)
        layout.addWidget(self._mcp_status_label)

        mcp_btn_row = QHBoxLayout()
        mcp_cfg = QPushButton("配置 MCP Servers…")
        mcp_cfg.setProperty("variant", "primary")
        mcp_cfg.setFixedWidth(180)
        mcp_cfg.clicked.connect(self._open_mcp_dialog)
        mcp_btn_row.addWidget(mcp_cfg)
        mcp_reload = QPushButton("重新连接")
        mcp_reload.setProperty("variant", "secondary")
        mcp_reload.clicked.connect(self._reload_mcp)
        mcp_btn_row.addWidget(mcp_reload)
        mcp_btn_row.addStretch()
        layout.addLayout(mcp_btn_row)

        self._mcp_tools_widget = QWidget()
        self._mcp_tools_layout = QVBoxLayout(self._mcp_tools_widget)
        self._mcp_tools_layout.setContentsMargins(0, 0, 0, 0)
        self._mcp_tools_layout.setSpacing(4)
        layout.addWidget(self._mcp_tools_widget)
        self._refresh_mcp_tools_ui()

        layout.addStretch()
        return scroll

    def _open_mcp_dialog(self) -> None:
        from ui.dialogs.mcp_dialog import MCPDialog
        if MCPDialog(self).exec() == QDialog.Accepted:
            self._refresh_mcp_tools_ui()
            self._notify("mcp_config")

    def _reload_mcp(self) -> None:
        import threading
        from agent_runtime.mcp_client import refresh_mcp_tools

        def work():
            refresh_mcp_tools()
            self._refresh_mcp_tools_ui()

        threading.Thread(target=work, daemon=True).start()

    def _refresh_mcp_tools_ui(self) -> None:
        from agent_runtime.mcp_client import mcp_manager, mcp_enabled

        layout = self._mcp_tools_layout
        while layout.count():
            child = layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        self._mcp_status_label.setText("\n".join(mcp_manager.get_status_lines()))

        if not mcp_enabled():
            empty = QLabel("MCP 已在安全中心关闭。")
            empty.setStyleSheet("font-size:12px; color:#6b7280; padding:8px;")
            layout.addWidget(empty)
            return

        tools = mcp_manager.get_cached_tool_definitions()
        if not tools:
            empty = QLabel("暂无 MCP 工具。点击「配置 MCP Servers」添加并测试连接。")
            empty.setStyleSheet("font-size:12px; color:#6b7280; padding:8px;")
            layout.addWidget(empty)
            return

        import json as _json
        disabled_raw = get_setting("disabled_tools", "[]")
        try:
            disabled_set = set(_json.loads(disabled_raw))
        except Exception:
            disabled_set = set()

        for tool_def in tools[:40]:
            func = tool_def.get("function", {})
            name = func.get("name", "")
            tool_desc = func.get("description", "")[:80]
            row = QWidget()
            row.setFixedHeight(44)
            row.setObjectName("SettingsListCard")
            rl = QHBoxLayout(row)
            rl.setContentsMargins(12, 4, 12, 4)
            name_lbl = QLabel(name)
            name_lbl.setStyleSheet("font-size:12px; font-weight:bold; color:#F0F2F5;")
            rl.addWidget(name_lbl, 1)
            desc_lbl = QLabel(tool_desc)
            desc_lbl.setStyleSheet("font-size:11px; color:#9CA3AF;")
            rl.addWidget(desc_lbl, 2)
            toggle = _ToggleSwitch()
            toggle.setChecked(name not in disabled_set)
            toggle.toggled.connect(lambda checked, n=name: self._on_tool_toggled(n, checked))
            rl.addWidget(toggle)
            layout.addWidget(row)

    def _on_tool_toggled(self, name: str, checked: bool) -> None:
        import json as _json
        disabled_raw = get_setting("disabled_tools", "[]")
        try:
            disabled = set(_json.loads(disabled_raw))
        except Exception:
            disabled = set()
        if checked:
            disabled.discard(name)
        else:
            disabled.add(name)
        set_setting("disabled_tools", _json.dumps(sorted(disabled)), "json")
        self._notify("disabled_tools")

    def _refresh_installed_tools(self) -> None:
        layout = self._installed_tools_layout
        while layout.count():
            child = layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        rows = query_all(
            "SELECT * FROM installed_skill_packages ORDER BY enabled DESC, id DESC"
        )
        if not rows:
            empty = QLabel("暂无已安装工具。点击上方按钮从 URL 安装。")
            empty.setStyleSheet("font-size:12px; color:#6b7280; padding:8px;")
            layout.addWidget(empty)
            return

        for pkg in rows:
            row = QWidget()
            row.setFixedHeight(48)
            row.setObjectName("SettingsListCard")
            rl = QHBoxLayout(row)
            rl.setContentsMargins(12, 4, 12, 4)
            rl.setSpacing(10)

            icon_lbl = QLabel("📦")
            icon_lbl.setFixedWidth(24)
            icon_lbl.setStyleSheet("font-size:14px; background:transparent;")
            rl.addWidget(icon_lbl)

            info = QVBoxLayout()
            info.setSpacing(1)
            display = pkg.get("display_name") or pkg.get("package_name", "")
            ver = pkg.get("version", "0.1.0")
            name_lbl = QLabel(f"{display}  v{ver}")
            name_lbl.setStyleSheet("font-size:13px; font-weight:bold; color:#F0F2F5;")
            info.addWidget(name_lbl)
            src = pkg.get("source_type", "market")
            src_url = pkg.get("source_url", "")
            sub_text = f"来源: {src}"
            if src_url:
                sub_text += f"  ({src_url[:40]}{'…' if len(src_url) > 40 else ''})"
            sub_lbl = QLabel(sub_text)
            sub_lbl.setStyleSheet("font-size:11px; color:#9CA3AF;")
            info.addWidget(sub_lbl)
            rl.addLayout(info, 1)

            enabled_toggle = _ToggleSwitch()
            enabled_toggle.setChecked(bool(pkg.get("enabled", 1)))
            pid = pkg["id"]
            enabled_toggle.toggled.connect(
                lambda v, _id=pid: self._toggle_installed_skill(_id, v)
            )
            rl.addWidget(enabled_toggle)

            del_btn = QPushButton("卸载")
            del_btn.setFixedSize(52, 28)
            del_btn.setCursor(Qt.PointingHandCursor)
            del_btn.setStyleSheet("font-size:11px; color:#EF4444;")
            del_btn.clicked.connect(lambda _, _id=pid: self._uninstall_tool(_id))
            rl.addWidget(del_btn)

            layout.addWidget(row)

    def _toggle_installed_skill(self, pkg_id: int, enabled: bool) -> None:
        execute(
            "UPDATE installed_skill_packages SET enabled=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (1 if enabled else 0, pkg_id),
        )
        from core.settings_runtime import reload_skill_handlers
        reload_skill_handlers()
        self._notify("disable_all_plugins")

    def _uninstall_tool(self, pkg_id: int) -> None:
        from PySide6.QtWidgets import QMessageBox
        pkg = query_one("SELECT * FROM installed_skill_packages WHERE id=?", (pkg_id,))
        if not pkg:
            return
        reply = QMessageBox.question(
            self, "确认卸载",
            f"确定要卸载工具「{pkg.get('display_name', '')}」吗？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        import shutil
        install_path = pkg.get("install_path", "")
        if install_path and Path(install_path).is_dir():
            shutil.rmtree(install_path, ignore_errors=True)
        delete("installed_skill_packages", pkg_id)
        from core.settings_runtime import reload_skill_handlers
        reload_skill_handlers()
        self._notify("disable_all_plugins")
        self._refresh_installed_tools()

    def _install_tool_from_url(self) -> None:
        from PySide6.QtWidgets import QInputDialog, QMessageBox
        url, ok = QInputDialog.getText(
            self, "安装工具", "输入 Skill 下载地址或 GitHub 仓库地址："
        )
        if not ok or not url.strip():
            return
        try:
            from agent_runtime.skill_installer import install_skill_from_url
            result = install_skill_from_url(url.strip())
            display = result.get("manifest", {}).get("display_name", result.get("package_name", ""))
            QMessageBox.information(
                self, "安装成功",
                f"工具「{display}」已安装。\n路径：{result.get('install_path', '')}",
            )
            from core.settings_runtime import reload_skill_handlers
            reload_skill_handlers()
            self._notify("disable_all_plugins")
            self._refresh_installed_tools()
        except Exception as e:
            QMessageBox.critical(self, "安装失败", str(e))

    # ------------------------------------------------------------------
    # 7. 助理设置
    # ------------------------------------------------------------------
    def _page_assistant(self) -> QWidget:
        scroll, layout = _make_scroll_page()
        layout.addWidget(_section_title("助理设置"))

        auto_save = _ToggleSwitch()
        auto_save.setChecked(get_bool("auto_save_chat", True))
        auto_save.toggled.connect(lambda v: self._save_bool("auto_save_chat", v))
        layout.addWidget(_setting_row(
            "自动保存对话", "每次对话结束后自动保存记录", auto_save
        ))

        auto_exec = _ToggleSwitch()
        auto_exec.setChecked(get_bool("auto_execute_low_risk", False))
        auto_exec.toggled.connect(lambda v: self._save_bool("auto_execute_low_risk", v))
        layout.addWidget(_setting_row(
            "非高风险自动执行", "对低风险操作自动执行，无需确认", auto_exec
        ))

        proactive = _ToggleSwitch()
        proactive.setChecked(get_bool("proactive_suggestions", True))
        proactive.toggled.connect(lambda v: self._save_bool("proactive_suggestions", v))
        layout.addWidget(_setting_row(
            "主动建议", "助理会根据上下文主动提供建议", proactive
        ))

        verbose = _ToggleSwitch()
        verbose.setChecked(get_bool("verbose_reply", False))
        verbose.toggled.connect(lambda v: self._save_bool("verbose_reply", v))
        layout.addWidget(_setting_row(
            "详细回复", "回复时包含更多解释和步骤细节", verbose
        ))

        layout.addStretch()
        return scroll

    # ------------------------------------------------------------------
    # 7. 个性化
    # ------------------------------------------------------------------
    def _page_personalization(self) -> QWidget:
        scroll, layout = _make_scroll_page()
        layout.addWidget(_section_title("个性化"))

        theme = QComboBox()
        theme.setFixedWidth(160)
        theme.addItems(["深色", "浅色", "跟随系统"])
        theme.setCurrentText(get_setting("theme", "深色"))
        theme.currentTextChanged.connect(lambda v: self._save_setting("theme", v))
        layout.addWidget(_setting_row("主题", "界面配色方案", theme))

        sidebar_pos = QComboBox()
        sidebar_pos.setFixedWidth(160)
        sidebar_pos.addItems(["左侧", "右侧"])
        sidebar_pos.setCurrentText(get_setting("sidebar_position", "左侧"))
        sidebar_pos.currentTextChanged.connect(lambda v: self._save_setting("sidebar_position", v))
        layout.addWidget(_setting_row("侧边栏位置", "调整导航栏的位置", sidebar_pos))

        animation = _ToggleSwitch()
        animation.setChecked(get_bool("enable_animations", True))
        animation.toggled.connect(lambda v: self._save_bool("enable_animations", v))
        layout.addWidget(_setting_row(
            "动画效果", "启用界面过渡和动画", animation
        ))

        sound = _ToggleSwitch()
        sound.setChecked(get_bool("enable_sound", True))
        sound.toggled.connect(lambda v: self._save_bool("enable_sound", v))
        layout.addWidget(_setting_row(
            "提示音", "操作完成或收到消息时播放提示音", sound
        ))

        layout.addStretch()
        return scroll

    # ------------------------------------------------------------------
    # 8. 数据管理
    # ------------------------------------------------------------------
    def _page_data(self) -> QWidget:
        scroll, layout = _make_scroll_page()
        layout.addWidget(_section_title("数据管理"))

        stats_row = QHBoxLayout()
        stats_row.setSpacing(12)
        conv_count = len(query_all("SELECT id FROM conversations"))
        task_count = len(query_all("SELECT id FROM tasks"))
        artifact_count = len(query_all("SELECT id FROM artifacts"))
        try:
            archived_count = len(query_all("SELECT id FROM conversations WHERE title LIKE '%[归档]%'"))
        except Exception:
            archived_count = 0
        for value, label_text in [
            (conv_count, "对话总数"),
            (task_count, "任务总数"),
            (artifact_count, "产物总数"),
            (archived_count, "已归档"),
        ]:
            card = QWidget()
            card.setObjectName("StatCard")
            card.setFixedSize(150, 90)
            card.setObjectName("SettingsStatCard")
            cl = QVBoxLayout(card)
            cl.setAlignment(Qt.AlignCenter)
            val_label = QLabel(str(value))
            val_label.setObjectName("SettingsStatValue")
            val_label.setAlignment(Qt.AlignCenter)
            cl.addWidget(val_label)
            desc_label = QLabel(label_text)
            desc_label.setObjectName("SettingsCardMuted")
            desc_label.setAlignment(Qt.AlignCenter)
            cl.addWidget(desc_label)
            stats_row.addWidget(card)
        stats_row.addStretch()
        layout.addLayout(stats_row)

        layout.addSpacing(16)
        layout.addWidget(QLabel("维护操作"))

        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)
        clean_btn = QPushButton("清理缓存")
        clean_btn.setProperty("variant", "secondary")
        clean_btn.clicked.connect(self._clean_cache)
        export_btn = QPushButton("导出数据")
        export_btn.setProperty("variant", "secondary")
        export_btn.clicked.connect(self._export_data)
        btn_row.addWidget(clean_btn)
        btn_row.addWidget(export_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        layout.addStretch()
        return scroll

    def _clean_cache(self) -> None:
        import shutil
        project_root = app_root()
        for p in project_root.rglob("__pycache__"):
            if p.is_dir():
                shutil.rmtree(p, ignore_errors=True)
        for p in project_root.rglob("*.pyc"):
            p.unlink(missing_ok=True)

    def _export_data(self) -> None:
        import shutil
        from datetime import datetime
        from PySide6.QtWidgets import QMessageBox
        dest = QFileDialog.getExistingDirectory(self, "选择导出目录")
        if not dest:
            return
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out = Path(dest) / f"dna_agent_backup_{stamp}"
        try:
            shutil.copytree(data_dir(), out / "data")
            QMessageBox.information(self, "导出完成", f"数据已导出到：\n{out / 'data'}")
        except Exception as exc:
            QMessageBox.critical(self, "导出失败", str(exc))

    def _show_help_doc(self) -> None:
        from PySide6.QtWidgets import QMessageBox
        readme = app_root() / "README.md"
        text = readme.read_text(encoding="utf-8", errors="ignore")[:4000] if readme.exists() else (
            "1. 在底部输入任务，选择「问一问 / 做一做 / 想一想」模式\n"
            "2. 做一做：Agent 直接调用工具执行\n"
            "3. 想一想：先规划再执行\n"
            "4. 左栏 ⚙ 打开设置，配置模型与工具\n"
            "5. 右栏查看产物与文件"
        )
        QMessageBox.information(self, "使用帮助", text)

    def _submit_feedback(self) -> None:
        from ui.app_menu import submit_feedback
        submit_feedback(self.window())

    # ------------------------------------------------------------------
    # 9. 安全中心
    # ------------------------------------------------------------------
    def _page_security(self) -> QWidget:
        scroll, layout = _make_scroll_page()
        layout.addWidget(_section_title("安全中心"))

        file_access = _ToggleSwitch()
        file_access.setChecked(get_bool("allow_file_access", True))
        file_access.toggled.connect(lambda v: self._save_bool("allow_file_access", v))
        layout.addWidget(_setting_row(
            "文件访问权限", "允许智能体读取和写入本地文件", file_access
        ))

        net_access = _ToggleSwitch()
        net_access.setChecked(get_bool("allow_network", True))
        net_access.toggled.connect(lambda v: self._save_bool("allow_network", v))
        layout.addWidget(_setting_row(
            "网络访问权限", "允许智能体访问互联网资源", net_access
        ))

        exec_perm = _ToggleSwitch()
        exec_perm.setChecked(get_bool("allow_exec", False))
        exec_perm.toggled.connect(lambda v: self._save_bool("allow_exec", v))
        layout.addWidget(_setting_row(
            "命令执行权限", "允许执行 PowerShell/CMD 等系统命令（需谨慎）", exec_perm
        ))

        app_launch = _ToggleSwitch()
        app_launch.setChecked(get_bool("allow_app_launch", True))
        app_launch.toggled.connect(lambda v: self._save_bool("allow_app_launch", v))
        layout.addWidget(_setting_row(
            "应用启动权限", "允许启动本地程序（仅打开窗口，不含自动点击）", app_launch
        ))

        gui_auto = _ToggleSwitch()
        gui_auto.setChecked(get_bool("enable_gui_automation", False))
        gui_auto.toggled.connect(lambda v: self._save_bool("enable_gui_automation", v))
        layout.addWidget(_setting_row(
            "GUI 自动化（实验性）",
            "允许 ui_click、键盘模拟等操控桌面软件。默认关闭；推荐优先使用文档生成与资料库检索",
            gui_auto,
        ))

        confirm_danger = _ToggleSwitch()
        confirm_danger.setChecked(get_bool("confirm_dangerous_ops", True))
        confirm_danger.toggled.connect(lambda v: self._save_bool("confirm_dangerous_ops", v))
        layout.addWidget(_setting_row(
            "高风险操作确认", "执行高风险操作前要求用户确认", confirm_danger
        ))

        mcp_enable = _ToggleSwitch()
        mcp_enable.setChecked(get_bool("enable_mcp", True))
        mcp_enable.toggled.connect(self._on_mcp_enable_toggled)
        layout.addWidget(_setting_row(
            "MCP 外部工具", "允许 Agent 调用已配置的 MCP Server 工具", mcp_enable
        ))

        layout.addStretch()
        return scroll

    # ------------------------------------------------------------------
    # 10. 帮助与反馈
    # ------------------------------------------------------------------
    def _page_help(self) -> QWidget:
        scroll, layout = _make_scroll_page()
        layout.addWidget(_section_title("帮助与反馈"))

        help_btn = QPushButton("使用帮助")
        help_btn.setFixedWidth(160)
        help_btn.setProperty("variant", "secondary")
        help_btn.clicked.connect(lambda: self._show_help_doc())
        layout.addWidget(_setting_row("使用帮助", "查看使用文档和常见问题", help_btn))

        feedback_btn = QPushButton("提交反馈")
        feedback_btn.setFixedWidth(160)
        feedback_btn.setProperty("variant", "secondary")
        feedback_btn.clicked.connect(lambda: self._submit_feedback())
        layout.addWidget(_setting_row("意见反馈", "向开发团队提交问题或建议", feedback_btn))

        layout.addSpacing(16)
        layout.addWidget(_section_title("关于"))

        info_text = (
            f"{APP_NAME} {APP_VERSION}\n\n"
            "面向工程技术领域的本地 AI 桌面 Agent 平台。\n"
            "支持自然语言驱动的任务规划与执行，Office 文档生成，本地文件操作，\n"
            "行业标准检索，以及与 VS Code、PyCharm 等开发工具的集成。"
        )
        info_label = QLabel(info_text)
        info_label.setWordWrap(True)
        info_label.setStyleSheet("font-size: 12px; color: #9CA3AF; line-height: 1.6;")
        layout.addWidget(info_label)

        layout.addSpacing(8)
        log_label = QLabel("运行日志")
        log_label.setStyleSheet("font-size: 13px; font-weight: bold; color: #F0F2F5;")
        layout.addWidget(log_label)

        log_text = QPlainTextEdit()
        log_text.setReadOnly(True)
        log_text.setObjectName("LogViewer")
        log_text.setMinimumHeight(160)
        log_path = log_file()
        if log_path.exists():
            log_text.setPlainText(
                log_path.read_text(encoding="utf-8", errors="ignore")[-20000:]
            )
        else:
            log_text.setPlainText("暂无日志")
        layout.addWidget(log_text, 1)

        return scroll

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------
    def _pick_dir(self, line_edit: QLineEdit, setting_key: str) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择目录")
        if path:
            line_edit.setText(path)
            self._save_setting(setting_key, path)


class _ModelDialog(QDialog):
    def __init__(self, parent=None, data=None):
        super().__init__(parent)
        self.setWindowTitle("模型配置")
        self.setMinimumWidth(500)
        self.data = data or {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        from PySide6.QtWidgets import QFormLayout
        form = QFormLayout()
        form.setSpacing(10)

        self._template = QComboBox()
        self._template.addItem("自定义")
        self._template.addItems(list(_PROVIDER_PRESETS.keys()))
        self._template.currentTextChanged.connect(self._apply_preset)
        form.addRow("提供商模板", self._template)

        self.provider = QLineEdit(self.data.get("provider_name", ""))
        self.provider.setPlaceholderText("例如 DeepSeek、腾讯混元、Ollama")
        self.api_base = QLineEdit(self.data.get("api_base", ""))
        self.api_base.setPlaceholderText("https://api.deepseek.com")
        self.api_key = QLineEdit(self.data.get("api_key", ""))
        self.api_key.setEchoMode(QLineEdit.Password)
        self.model_name = QLineEdit(self.data.get("model_name", ""))
        self.model_name.setPlaceholderText("deepseek-v4-pro")
        from PySide6.QtWidgets import QSpinBox, QDoubleSpinBox
        self.context_window = QSpinBox()
        self.context_window.setRange(8192, 2_000_000)
        self.context_window.setSingleStep(1024)
        self.context_window.setValue(int(self.data.get("context_window") or 128000))
        self.max_tokens = QSpinBox()
        self.max_tokens.setRange(256, 131072)
        self.max_tokens.setValue(int(self.data.get("max_tokens") or 8192))
        self.temperature = QDoubleSpinBox()
        self.temperature.setRange(0.0, 2.0)
        self.temperature.setSingleStep(0.1)
        self.temperature.setValue(float(self.data.get("temperature") or 0.7))
        self.reasoning_effort = QComboBox()
        self.reasoning_effort.addItems(["", "high", "max"])
        effort = (self.data.get("reasoning_effort") or "").strip()
        idx = self.reasoning_effort.findText(effort)
        self.reasoning_effort.setCurrentIndex(idx if idx >= 0 else 0)
        self.thinking_enabled = _ToggleSwitch()
        self.thinking_enabled.setChecked(bool(self.data.get("thinking_enabled", 0)))
        form.addRow("供应商", self.provider)
        form.addRow("API Base", self.api_base)
        form.addRow("API Key", self.api_key)
        form.addRow("Model", self.model_name)
        form.addRow("上下文窗口 (tokens)", self.context_window)
        form.addRow("单次输出上限", self.max_tokens)
        form.addRow("Temperature", self.temperature)
        form.addRow("Reasoning Effort", self.reasoning_effort)
        form.addRow("Thinking 模式", self.thinking_enabled)
        layout.addLayout(form)

        btns = QHBoxLayout()
        btns.addStretch()
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        ok = QPushButton("保存")
        ok.setProperty("variant", "primary")
        ok.clicked.connect(self.accept)
        btns.addWidget(cancel)
        btns.addWidget(ok)
        layout.addLayout(btns)

    def _apply_preset(self, name: str) -> None:
        preset = _PROVIDER_PRESETS.get(name)
        if not preset:
            return
        api_base, model = preset
        from core.model_profiles import enrich_model_config, match_model_profile

        profile = match_model_profile(model) or {}
        self.provider.setText(str(profile.get("provider_name") or name.split("(")[0].strip()))
        self.api_base.setText(api_base)
        self.model_name.setText(model)
        enriched = enrich_model_config({
            "model_name": model,
            "api_base": api_base,
            "provider_name": self.provider.text().strip(),
        }) or {}
        if enriched.get("context_window"):
            self.context_window.setValue(int(enriched["context_window"]))
        if enriched.get("max_tokens"):
            self.max_tokens.setValue(int(enriched["max_tokens"]))
        if enriched.get("temperature") is not None:
            self.temperature.setValue(float(enriched["temperature"]))
        effort = str(enriched.get("reasoning_effort") or "")
        idx = self.reasoning_effort.findText(effort)
        if idx >= 0:
            self.reasoning_effort.setCurrentIndex(idx)
        self.thinking_enabled.setChecked(bool(enriched.get("thinking_enabled", 0)))

    def values(self) -> dict:
        from core.model_client import ModelClient
        from core.model_profiles import enrich_model_config

        base = {
            "provider_name": self.provider.text().strip(),
            "provider_type": "openai_compatible",
            "api_base": ModelClient.normalize_api_base(self.api_base.text().strip()),
            "api_key": self.api_key.text().strip(),
            "model_name": self.model_name.text().strip(),
            "context_window": int(self.context_window.value()),
            "max_tokens": int(self.max_tokens.value()),
            "temperature": float(self.temperature.value()),
            "reasoning_effort": self.reasoning_effort.currentText().strip(),
            "thinking_enabled": 1 if self.thinking_enabled.isChecked() else 0,
        }
        return enrich_model_config(base) or base

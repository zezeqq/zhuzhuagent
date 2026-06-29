from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QHBoxLayout, QMainWindow, QPushButton,
    QSplitter, QStackedWidget, QStatusBar, QVBoxLayout, QWidget,
)

from ui.i18n import t
from core.agent_context import current_project, default_model
from ui.app_menu import build_app_menus
from ui.window_chrome import TitleBarFrame, apply_window_effects
from ui.conversation_panel import ConversationPanel
from ui.pages.automation_page import AutomationPage
from ui.pages.expert_center_page import ExpertCenterPage
from ui.pages.more_page import MorePage
from ui.pages.project_page import ProjectPage
from ui.result_panel import ResultPanel
from ui.task_sidebar import TaskSidebar
from core.app_identity import APP_VERSION

PAGE_INDEX = {
    "assistant": 0,
    "project": 1,
    "expert": 2,
    "automation": 3,
    "more": 4,
}


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(t("window_title"))
        self.resize(1500, 940)
        self.setMinimumSize(1180, 740)
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        self._maximize_btn: QPushButton | None = None

        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self._sidebar = TaskSidebar()
        self._conversation = ConversationPanel()
        self._project_page = ProjectPage()
        self._expert_center = ExpertCenterPage()
        self._automation_page = AutomationPage()
        self._more_page = MorePage()
        self._results = ResultPanel()

        root_layout.addWidget(self._build_menu_bar())

        self._content_stack = QStackedWidget()
        self._content_stack.setObjectName("ContentStack")
        self._content_stack.addWidget(self._conversation)
        self._content_stack.addWidget(self._project_page)
        self._content_stack.addWidget(self._expert_center)
        self._content_stack.addWidget(self._automation_page)
        self._content_stack.addWidget(self._more_page)

        self._splitter = QSplitter(Qt.Horizontal)
        self._splitter.setObjectName("MainSplitter")
        self._splitter.setHandleWidth(1)
        self._splitter.addWidget(self._sidebar)
        self._splitter.addWidget(self._content_stack)
        self._splitter.addWidget(self._results)
        self._splitter.setSizes([308, 852, 400])
        self._splitter.setStretchFactor(0, 0)
        self._splitter.setStretchFactor(1, 1)
        self._splitter.setStretchFactor(2, 0)

        root_layout.addWidget(self._splitter, 1)
        self.setCentralWidget(root)

        self._status = QStatusBar()
        self._status.setObjectName("AppStatusBar")
        self.setStatusBar(self._status)
        self._refresh_status()

        self._connect_signals()
        self.apply_settings()

    def apply_settings(self, changed_key: str = "") -> None:
        from PySide6.QtWidgets import QApplication
        from core.settings_runtime import apply_app_settings, reload_skill_handlers

        app = QApplication.instance()
        if app:
            apply_app_settings(app, self)
        if changed_key in ("", "disable_all_plugins", "disabled_tools", "enable_mcp", "mcp_config"):
            reload_skill_handlers()
            if changed_key in ("enable_mcp", "mcp_config", "disable_all_plugins", ""):
                import threading
                from agent_runtime.mcp_client import refresh_mcp_tools, shutdown_mcp, mcp_enabled
                def _mcp():
                    if mcp_enabled():
                        refresh_mcp_tools()
                    else:
                        shutdown_mcp()
                    from PySide6.QtCore import QTimer
                    QTimer.singleShot(0, self._refresh_status)
                threading.Thread(target=_mcp, daemon=True).start()
        self._conversation._load_models()

    def _build_menu_bar(self) -> TitleBarFrame:
        bar = TitleBarFrame(self)
        bar.setObjectName("AppMenuBar")
        bar.setFixedHeight(32)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(12, 0, 0, 0)
        layout.setSpacing(8)
        menus = build_app_menus(self)
        for key in ("app", "edit", "window", "help"):
            layout.addWidget(menus[key])
        layout.addStretch()
        toggle_result = QPushButton(t("toggle_results"))
        self._toggle_result_btn = toggle_result
        toggle_result.setObjectName("MenuToggleButton")
        toggle_result.setCursor(Qt.PointingHandCursor)
        toggle_result.clicked.connect(self._toggle_results)
        layout.addWidget(toggle_result)

        min_btn = QPushButton("—")
        min_btn.setObjectName("TitleBarButton")
        min_btn.setCursor(Qt.PointingHandCursor)
        min_btn.clicked.connect(self.showMinimized)
        layout.addWidget(min_btn)

        self._maximize_btn = QPushButton("□")
        self._maximize_btn.setObjectName("TitleBarButton")
        self._maximize_btn.setCursor(Qt.PointingHandCursor)
        self._maximize_btn.clicked.connect(self._toggle_maximize)
        layout.addWidget(self._maximize_btn)

        close_btn = QPushButton("✕")
        close_btn.setObjectName("TitleBarCloseButton")
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.clicked.connect(self.close)
        layout.addWidget(close_btn)
        return bar

    def _toggle_maximize(self) -> None:
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == event.Type.WindowStateChange and self._maximize_btn:
            self._maximize_btn.setText("❐" if self.isMaximized() else "□")

    def showEvent(self, event):
        super().showEvent(event)
        apply_window_effects(self)

    def _connect_signals(self) -> None:
        self._sidebar.new_task_requested.connect(self._on_new_task)
        self._sidebar.conversation_selected.connect(self._on_conversation_selected)
        self._sidebar.settings_requested.connect(self._open_settings)
        self._sidebar.page_changed.connect(self._on_page_changed)
        self._sidebar.sub_page_requested.connect(self._on_sub_page)

        self._conversation.conversation_changed.connect(self._on_conversation_created)
        self._conversation.task_created.connect(self._on_task_created)
        self._conversation.files_changed.connect(self._results.refresh_file_views)
        self._conversation.artifact_created.connect(self._results.add_artifact)

        self._expert_center.expert_selected.connect(self._on_expert_selected)
        self._expert_center.skill_installed.connect(self._on_skill_installed)
        self._more_page.prompt_selected.connect(self._on_inspiration_prompt)

        self._automation_page.automation_triggered.connect(self._on_automation_triggered)
        self._project_page.project_activated.connect(self._on_project_activated)

    def _on_page_changed(self, page_key: str) -> None:
        idx = PAGE_INDEX.get(page_key, 0)
        self._content_stack.setCurrentIndex(idx)
        show_results = (page_key == "assistant")
        self._results.setVisible(show_results)
        if page_key == "project":
            self._project_page.refresh()

    def _on_sub_page(self, sub_key: str) -> None:
        if sub_key == "mcp":
            from ui.dialogs.mcp_dialog import open_mcp_dialog
            open_mcp_dialog(self)
            return
        mapping = {
            "skills": ("expert", "skills"),
            "connectors": ("expert", "connectors"),
            "resources": ("more", "resources"),
            "inspiration": ("more", "inspiration"),
        }
        page_key, tab_name = mapping.get(sub_key, ("assistant", None))
        self._on_page_changed(page_key)
        self._sidebar.highlight_nav(page_key)
        if tab_name and page_key == "expert":
            self._expert_center.switch_to_tab(tab_name)
        elif tab_name and page_key == "more":
            self._more_page.scroll_to_section(tab_name)

    def _on_new_task(self) -> None:
        self._on_page_changed("assistant")
        self._sidebar.highlight_nav("assistant")
        self._conversation.clear_conversation()
        self._results.clear()
        self._sidebar.select_conversation(-1)

    def _on_conversation_selected(self, conv_id: int) -> None:
        self._on_page_changed("assistant")
        self._sidebar.highlight_nav("assistant")
        from core.conversation_manager import get_conversation, conversation_task_info
        conv = get_conversation(conv_id)
        title = conv.get("title", "") if conv else ""
        self._conversation.load_conversation(conv_id, title=title)
        self._results.set_conversation(conv_id)
        info = conversation_task_info(conv_id)
        if info:
            self._results.set_task(info["id"])
        else:
            self._results.set_task(None)
        self._refresh_status()

    def _on_conversation_created(self, conv_id: int) -> None:
        self._sidebar.refresh()
        self._sidebar.select_conversation(conv_id)

    def _on_task_created(self, task_id: int) -> None:
        self._sidebar.refresh()
        self._results.set_task(task_id)
        if self._conversation._conversation_id:
            self._results.set_conversation(self._conversation._conversation_id)
        self._results.refresh_artifacts()
        self._results.refresh_files()
        self._refresh_status()

    def _open_settings(self, page: int = 0) -> None:
        from ui.dialogs.open_settings import open_settings_dialog
        open_settings_dialog(self, page)

    def _toggle_sidebar(self) -> None:
        self._sidebar.setVisible(not self._sidebar.isVisible())

    def _toggle_results(self) -> None:
        self._results.setVisible(not self._results.isVisible())

    def _on_expert_selected(self, name: str, prompt: str) -> None:
        self._on_page_changed("assistant")
        self._sidebar.highlight_nav("assistant")
        item = getattr(self._expert_center, "_last_summoned_item", None)
        team = item if isinstance(item, dict) and item.get("kind") == "team" else None
        self._conversation.set_expert(name, prompt, team=team)
        if team:
            members = team.get("members") or []
            self._conversation._input.setPlaceholderText(
                f"向专家团「{name}」描述任务（将并行调用 {len(members)} 位成员）…"
            )
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.information(
                self,
                "专家团已激活",
                f"已召唤「{name}」。\n\n"
                f"成员：{'、'.join(str(m) for m in members)}\n\n"
                "请在下方输入任务并发送，将自动进入真并行协作（非普通单专家对话）。",
            )
        else:
            from ui.i18n import t
            self._conversation._input.setPlaceholderText(t("chat_input_placeholder"))

    def _on_skill_installed(self, package_name: str, display_name: str) -> None:
        self._conversation.activate_skill_package(package_name)
        self._on_page_changed("assistant")
        self._sidebar.highlight_nav("assistant")

    def _on_automation_triggered(self, conv_id: int) -> None:
        self._on_page_changed("assistant")
        self._sidebar.highlight_nav("assistant")
        from core.conversation_manager import get_conversation, get_messages
        conv = get_conversation(conv_id)
        title = conv.get("title", "") if conv else ""
        self._conversation.load_conversation(conv_id, title=title)
        self._results.set_conversation(conv_id)
        self._sidebar.refresh()
        self._sidebar.select_conversation(conv_id)
        messages = get_messages(conv_id)
        if messages:
            last_user = [m for m in messages if m.get("role") == "user"]
            if last_user:
                self._conversation.replay_agent(last_user[-1]["content"])

    def _on_inspiration_prompt(self, prompt: str) -> None:
        self._on_page_changed("assistant")
        self._sidebar.highlight_nav("assistant")
        self._conversation._input.setPlainText(prompt)
        self._conversation.send()

    def _on_project_activated(self, project_id: int) -> None:
        self._refresh_status()
        self._on_page_changed("assistant")
        self._sidebar.highlight_nav("assistant")
        self._conversation.clear_conversation()
        self._results.clear()

    def _refresh_status(self) -> None:
        from ui.i18n import t

        model = default_model()
        project = current_project()
        model_text = model["model_name"] if model else t("status_no_model")
        project_text = project["project_name"] if project else t("status_no_project")
        mcp_text = ""
        try:
            from agent_runtime.mcp_client import get_mcp_status_summary, mcp_enabled
            if mcp_enabled():
                s = get_mcp_status_summary()
                n = int(s.get("tool_count") or 0)
                if n > 0:
                    mcp_text = f"    MCP：{n} 工具"
                else:
                    mcp_text = "    MCP：未连接（点 MCP → Test & reload）"
        except Exception:
            pass
        self._status.showMessage(
            f"{t('status_model')}：{model_text}    {t('status_project')}：{project_text}{mcp_text}    {APP_VERSION}"
        )

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from PySide6.QtCore import Qt, Signal, QTimer, QMimeData, QUrl
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QPixmap, QImage, QTextCursor
from PySide6.QtMultimedia import QAudioInput, QMediaCaptureSession, QMediaRecorder
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QFrame, QHBoxLayout, QLabel,
    QMenu, QPushButton, QScrollArea, QSizePolicy, QTextEdit, QVBoxLayout, QWidget,
)

from core.agent_context import current_project, default_model
from core.conversation_manager import (
    add_message, create_conversation, get_conversation, get_messages, update_conversation,
)
from db.database import query_all
from ui.i18n import t
from ui.widgets.message_widget import (
    AgentMessage, ArtifactMessage, FollowUpActionMessage, GuideMessage, PermissionRequestMessage,
    PlanMessage, StepProgressMessage, ThinkingBlock, ToolCallMessage, ToolCallsGroup, UserMessage,
    WelcomeWidget, _qobject_alive,
)
from ui.widgets.mode_selector import ModeSelector
from ui.widgets.chat_input import ChatInputEdit, format_mention_for_display
from ui.widgets.file_reference_popup import FileReferencePopup
from ui.widgets.reference_strip import ReferenceStrip
from ui.widgets.send_menu_button import SendMenuButton
from ui.workers import AgentWorker, ExpertTeamWorker, VoiceTranscribeWorker


IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tiff", ".ico"}
AUDIO_EXTS = {".mp3", ".wav", ".ogg", ".m4a", ".flac", ".aac", ".wma"}
ALLOWED_EXTS = IMAGE_EXTS | AUDIO_EXTS

_PLACEHOLDER_TEXTS = frozenset({
    "🤔 思考中…", "🤔 继续执行中…", "🔧 执行工具中…", "",
})

# 仅匹配「任务进行中、询问是否继续执行」类话术，不匹配普通闲聊/澄清问题
_EXECUTION_CONTINUE_CUES = (
    "继续执行", "是否继续", "要我继续", "需要我继续", "还要我继续",
    "是否开始执行", "开始执行吗", "现在执行吗", "是否按此计划", "按此计划执行",
    "是否执行", "执行吗", "要继续吗", "继续吗", "下一步",
)


_GUIDE_PREFIX = "💡 引导 · "


def _looks_like_follow_up_prompt(text: str) -> bool:
    """Agent 是否在多步任务中询问「是否继续执行」，而非普通对话提问。"""
    t = (text or "").strip()
    if len(t) < 10:
        return False
    has_question = "？" in t or "?" in t or t.rstrip().endswith(("吗", "呢"))
    if not has_question:
        return False
    return any(cue in t for cue in _EXECUTION_CONTINUE_CUES)


def _is_placeholder_message(widget: AgentMessage | None) -> bool:
    if widget is None or not _qobject_alive(widget):
        return False
    return getattr(widget, "_raw_text", "") in _PLACEHOLDER_TEXTS


class _AttachmentStrip(QWidget):
    """Horizontal strip showing attachment thumbnails with remove buttons."""

    attachment_removed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(6)
        self._layout.addStretch()
        self.setVisible(False)

    def add_file(self, path: str) -> None:
        suffix = Path(path).suffix.lower()
        card = QFrame()
        card.setObjectName("AttachmentCard")
        card.setFixedSize(92, 76)
        card.setProperty("file_path", path)
        cl = QVBoxLayout(card)
        cl.setContentsMargins(6, 6, 6, 4)
        cl.setSpacing(3)

        if suffix in IMAGE_EXTS:
            thumb = QLabel()
            pix = QPixmap(path)
            if not pix.isNull():
                pix = pix.scaled(80, 48, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            thumb.setPixmap(pix)
            thumb.setAlignment(Qt.AlignCenter)
            thumb.setStyleSheet("background: transparent;")
            cl.addWidget(thumb)
        else:
            icon = QLabel("🎵" if suffix in AUDIO_EXTS else "📎")
            icon.setAlignment(Qt.AlignCenter)
            icon.setStyleSheet("font-size: 24px; background: transparent;")
            cl.addWidget(icon)

        name_lbl = QLabel(Path(path).name[:12])
        name_lbl.setObjectName("AttachmentCardName")
        name_lbl.setAlignment(Qt.AlignCenter)
        cl.addWidget(name_lbl)

        remove_btn = QPushButton("×")
        remove_btn.setObjectName("AttachmentRemoveBtn")
        remove_btn.setFixedSize(20, 20)
        remove_btn.setCursor(Qt.PointingHandCursor)
        remove_btn.move(70, 2)
        remove_btn.setParent(card)
        remove_btn.clicked.connect(lambda _, p=path: self._remove(p))

        idx = self._layout.count() - 1
        self._layout.insertWidget(idx, card)
        self.setVisible(True)

    def _remove(self, path: str) -> None:
        for i in range(self._layout.count()):
            item = self._layout.itemAt(i)
            w = item.widget() if item else None
            if w and w.property("file_path") == path:
                self._layout.removeWidget(w)
                w.deleteLater()
                break
        self.attachment_removed.emit(path)
        if self._layout.count() <= 1:
            self.setVisible(False)

    def clear_all(self) -> None:
        while self._layout.count() > 1:
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.setVisible(False)

    def file_paths(self) -> list[str]:
        paths: list[str] = []
        for i in range(self._layout.count()):
            item = self._layout.itemAt(i)
            w = item.widget() if item else None
            if w and w.property("file_path"):
                paths.append(w.property("file_path"))
        return paths


EXPERTS = [
    ("default", "通用助理", ""),
    ("highway", "公路机电专家", "你是一位资深的公路机电工程专家，精通交通监控、收费、通信、供配电、照明和隧道机电系统。回答要引用相关标准（JTG/T 3520、JTG 2182 等），给出工程化、可落地的建议。"),
    ("bid", "投标专家", "你是一位经验丰富的投标技术响应专家。你擅长解读招标文件技术要求，组织技术方案和响应内容，确保偏离表准确、评分项全覆盖。"),
    ("test", "测试专家", "你是一位现场测试专家，熟悉公路机电工程各系统的测试方法、仪器使用和记录规范。回答时引用测试规程标准条款。"),
    ("code", "编程助手", "你是一位 Python 全栈开发专家，精通自动化脚本、数据处理、Web 开发和嵌入式通信协议。代码简洁高效，有清晰的错误处理。"),
    ("quality", "质量专家", "你是一位工程质量管理专家，精通质量检验评定标准（JTG 2182-2020），熟悉工序、分部、单位工程的检验流程和评定方法。"),
    ("docs", "文档专家", "你是一位工程技术文档编写专家，擅长项目方案、施工组织设计、工程总结和验收资料的撰写，文风严谨规范。"),
]

_FILE_PRODUCING_TOOLS = frozenset({
    "file_write", "file_delete", "code_create",
    "office_word_create", "office_excel_create", "office_ppt_create",
})


class ConversationPanel(QFrame):
    task_created = Signal(int)
    artifact_created = Signal(dict)
    files_changed = Signal()
    conversation_changed = Signal(int)
    sidebar_toggle_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ConversationPanel")
        self._conversation_id: int | None = None
        self._worker: AgentWorker | None = None
        self._step_widget: StepProgressMessage | None = None
        self._pending_plan = None
        self._expert_prompt: str = ""
        self._active_team: dict | None = None
        self._current_agent_msg: AgentMessage | None = None
        self._tool_call_count: int = 0
        self._tool_group: ToolCallsGroup | None = None
        self._thinking_block: ThinkingBlock | None = None
        self._run_placeholder: AgentMessage | None = None
        self._session_auto_approve: bool = False
        self._ui_session_id: int = 0
        self._background_workers: dict[int, AgentWorker] = {}
        self._run_tool_counts: dict[int, int] = {}
        self._pending_permissions: dict[int, tuple[dict, AgentWorker]] = {}
        self._pending_plan_text: str = ""
        self._voice_recorder: QMediaRecorder | None = None
        self._voice_session: QMediaCaptureSession | None = None
        self._voice_audio_input: QAudioInput | None = None
        self._voice_audio_path: str = ""
        self._voice_worker: VoiceTranscribeWorker | None = None
        self._is_recording_voice = False
        self._ref_popup: FileReferencePopup | None = None
        self._ref_popup_visible = False
        self._scroll_scheduled = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._input_area = self._build_input_area()
        layout.addWidget(self._build_toolbar())
        layout.addWidget(self._build_message_area(), 1)
        layout.addWidget(self._input_area)

    def _build_toolbar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("ConversationToolbar")
        bar.setFixedHeight(48)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(20, 8, 20, 8)
        layout.setSpacing(12)

        self._conv_title = QLabel("")
        self._conv_title.setObjectName("ConvTitle")
        layout.addWidget(self._conv_title)

        self._team_badge = QLabel("")
        self._team_badge.setObjectName("MutedLabel")
        self._team_badge.setVisible(False)
        self._team_badge.setStyleSheet(
            "color:#38bdf8; font-weight:600; padding:2px 8px; "
            "background:rgba(56,189,248,0.12); border-radius:6px;"
        )
        layout.addWidget(self._team_badge)

        layout.addStretch()

        self._model_label = QLabel(t("chat_model"))
        layout.addWidget(self._model_label)
        self._model_combo = QComboBox()
        self._model_combo.setObjectName("ToolbarCombo")
        self._model_combo.setMinimumWidth(180)
        layout.addWidget(self._model_combo)

        self._load_models()
        return bar

    def _build_message_area(self) -> QScrollArea:
        self._scroll = QScrollArea()
        self._scroll.setObjectName("MessageScroll")
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        container = QWidget()
        container.setObjectName("MessageContainer")
        self._msg_layout = QVBoxLayout(container)
        self._msg_layout.setContentsMargins(0, 0, 0, 0)
        self._msg_layout.setSpacing(0)
        self._welcome = WelcomeWidget()
        self._welcome.prompt_selected.connect(self._on_prompt_selected)
        self._msg_layout.addWidget(self._welcome)
        self._msg_layout.addStretch()
        self._scroll.setWidget(container)
        return self._scroll

    def _build_input_area(self) -> QFrame:
        area = QFrame()
        area.setObjectName("InputArea")
        area.setAcceptDrops(True)
        layout = QVBoxLayout(area)
        layout.setContentsMargins(20, 10, 20, 14)
        layout.setSpacing(8)

        self._attach_strip = _AttachmentStrip()
        self._attach_strip.attachment_removed.connect(self._on_attachment_removed)
        layout.addWidget(self._attach_strip)

        self._ref_strip = ReferenceStrip()
        layout.addWidget(self._ref_strip)

        composer = QFrame()
        composer.setObjectName("InputComposer")
        composer_layout = QVBoxLayout(composer)
        composer_layout.setContentsMargins(16, 14, 16, 12)
        composer_layout.setSpacing(10)

        self._input = ChatInputEdit()
        self._input.setObjectName("ChatInput")
        self._input.setPlaceholderText("今天帮你做些什么？输入 @ 引用资料库或生成文件，/ 调用技能")
        self._input.setFixedHeight(92)
        self._input.installEventFilter(self)
        self._input.files_dropped.connect(self._on_files_dropped)
        self._input.reference_trigger.connect(self._on_reference_trigger)
        self._input.reference_cancel.connect(self._hide_reference_popup)
        composer_layout.addWidget(self._input)

        self._ref_popup = FileReferencePopup(self)
        self._ref_popup.item_chosen.connect(self._on_reference_chosen)

        controls_host = QFrame()
        controls_host.setObjectName("InputControlsStrip")
        controls = QHBoxLayout(controls_host)
        controls.setContentsMargins(0, 0, 0, 0)
        controls.setSpacing(6)

        self._mode = ModeSelector()
        self._mode.mode_changed.connect(self._on_mode_changed)
        self._mode.setFixedWidth(104)
        controls.addWidget(self._mode)

        tools_btn = QPushButton("⚙ 工具")
        tools_btn.setObjectName("InputBarButton")
        tools_btn.setCursor(Qt.PointingHandCursor)
        tools_btn.setToolTip("Skill / MCP")
        tools_btn.setFixedWidth(78)
        tools_menu = QMenu(tools_btn)
        self._my_skills_action = tools_menu.addAction(t("chat_my_skills"))
        self._my_skills_action.triggered.connect(lambda: self._open_skills(my_skills=True))
        self._skill_store_action = tools_menu.addAction(t("chat_skill_store"))
        self._skill_store_action.triggered.connect(self._open_skills)
        tools_menu.addSeparator()
        self._mcp_action = tools_menu.addAction(t("chat_mcp"))
        self._mcp_action.triggered.connect(self._open_mcp)
        tools_btn.setMenu(tools_menu)
        self._tools_btn = tools_btn

        self._expert_combo = QComboBox()
        self._expert_combo.setObjectName("InputBarCombo")
        self._expert_combo.setFixedWidth(132)
        for key, display, _ in EXPERTS:
            self._expert_combo.addItem(f"👤 {display}", key)
        self._expert_combo.currentIndexChanged.connect(self._on_expert_changed)
        controls.addWidget(self._expert_combo)

        self._auto_btn = QPushButton(t("chat_auto"))
        self._auto_btn.setObjectName("InputBarButton")
        self._auto_btn.setCursor(Qt.PointingHandCursor)
        self._auto_btn.setCheckable(True)
        self._auto_btn.setToolTip(t("chat_auto_tip"))
        self._auto_btn.toggled.connect(self._on_auto_model_toggled)
        self._auto_btn.setVisible(False)

        self._skill_combo = QComboBox()
        self._skill_combo.setObjectName("InputBarCombo")
        self._skill_combo.setFixedWidth(128)
        self._skill_combo.setToolTip("选择本对话优先使用的 Skill（空=注入全部已启用 Skill）")
        self._load_skill_combo()
        self._skill_combo.setVisible(False)

        controls.addWidget(tools_btn)

        self._perm_btn = QPushButton(t("chat_perm_default"))
        self._perm_btn.setObjectName("InputBarButton")
        self._perm_btn.setCursor(Qt.PointingHandCursor)
        self._perm_btn.setCheckable(True)
        self._perm_btn.setToolTip(t("chat_perm_tip"))
        self._perm_btn.clicked.connect(self._toggle_permission)
        controls.addWidget(self._perm_btn)
        controls.addStretch(1)

        action_group = QFrame()
        action_group.setObjectName("InputActionGroup")
        action_group.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        action_layout = QHBoxLayout(action_group)
        action_layout.setContentsMargins(4, 0, 0, 0)
        action_layout.setSpacing(7)

        self._stop_btn = QPushButton("⏹")
        self._stop_btn.setObjectName("InputIconButton")
        self._stop_btn.setToolTip(t("chat_stop_tip"))
        self._stop_btn.setCursor(Qt.PointingHandCursor)
        self._stop_btn.setFixedSize(34, 34)
        self._stop_btn.setVisible(False)
        self._stop_btn.clicked.connect(self._stop_generation)
        action_layout.addWidget(self._stop_btn)

        attach_btn = QPushButton("＋")
        attach_btn.setObjectName("InputIconButton")
        attach_btn.setToolTip(t("chat_attach_tip"))
        attach_btn.setCursor(Qt.PointingHandCursor)
        attach_btn.setFixedSize(34, 34)
        attach_btn.clicked.connect(self._attach_file)
        self._attach_btn = attach_btn
        action_layout.addWidget(attach_btn)

        self._net_btn = QPushButton()
        self._net_btn.setObjectName("NetworkToggleButton")
        self._net_btn.setCursor(Qt.PointingHandCursor)
        self._net_btn.setFixedSize(34, 34)
        self._net_btn.setCheckable(True)
        self._net_btn.setFocusPolicy(Qt.StrongFocus)
        self._net_btn.clicked.connect(self._on_network_clicked)
        from ui.icons.network_icon import network_toggle_icon, network_toggle_icon_size
        self._net_btn.setIconSize(network_toggle_icon_size())
        self._network_icon_fn = network_toggle_icon
        action_layout.addWidget(self._net_btn)
        self.sync_network_toggle()

        ref_btn = QPushButton("@")
        ref_btn.setObjectName("InputIconButton")
        ref_btn.setToolTip("引用资料库或生成文件")
        ref_btn.setCursor(Qt.PointingHandCursor)
        ref_btn.setFixedSize(34, 34)
        ref_btn.clicked.connect(self._input.trigger_reference_picker)
        action_layout.addWidget(ref_btn)

        self._voice_btn = QPushButton("🎙")
        self._voice_btn.setObjectName("VoiceButton")
        self._voice_btn.setToolTip("语音输入")
        self._voice_btn.setCursor(Qt.PointingHandCursor)
        self._voice_btn.setFixedSize(34, 34)
        self._voice_btn.clicked.connect(self._toggle_voice_input)
        action_layout.addWidget(self._voice_btn)

        self._send_btn = SendMenuButton()
        self._send_btn.send_normal.connect(lambda: self._send_as_normal(interrupt=True))
        self._send_btn.send_guide.connect(self._send_as_guide)
        action_layout.addWidget(self._send_btn)
        controls.addWidget(action_group, 0, Qt.AlignRight)

        composer_layout.addWidget(controls_host)
        layout.addWidget(composer)

        workspace_row = QFrame()
        workspace_row.setObjectName("WorkspaceRow")
        workspace_layout = QHBoxLayout(workspace_row)
        workspace_layout.setContentsMargins(14, 0, 14, 0)
        workspace_layout.setSpacing(6)
        self._workspace_btn = QPushButton("▢  选择工作空间  ›")
        self._workspace_btn.setObjectName("WorkspacePickerButton")
        self._workspace_btn.setToolTip(t("chat_workspace_tip"))
        self._workspace_btn.setCursor(Qt.PointingHandCursor)
        self._workspace_btn.clicked.connect(self._choose_workspace)
        workspace_layout.addWidget(self._workspace_btn, 0, Qt.AlignLeft)
        workspace_layout.addStretch(1)
        layout.addWidget(workspace_row)
        return area

    def eventFilter(self, obj, event):
        if obj is self._input and self._ref_popup_visible and self._ref_popup:
            if event.type() == event.Type.KeyPress:
                key = event.key()
                if key in (Qt.Key_Up, Qt.Key_Down, Qt.Key_Return, Qt.Key_Enter, Qt.Key_Escape):
                    if key == Qt.Key_Up:
                        self._ref_popup.select_prev()
                        return True
                    if key == Qt.Key_Down:
                        self._ref_popup.select_next()
                        return True
                    if key in (Qt.Key_Return, Qt.Key_Enter):
                        self._ref_popup.accept_current()
                        return True
                    if key == Qt.Key_Escape:
                        self._hide_reference_popup()
                        return True
        if obj is self._input and event.type() == event.Type.KeyPress:
            from core.settings_runtime import send_key_is_ctrl_enter
            if event.key() == Qt.Key_Return and not event.modifiers() & Qt.ShiftModifier:
                ctrl = bool(event.modifiers() & Qt.ControlModifier)
                if send_key_is_ctrl_enter():
                    if ctrl:
                        self._on_enter_send()
                        return True
                else:
                    if not ctrl:
                        self._on_enter_send()
                        return True
        return super().eventFilter(obj, event)

    def apply_send_key_setting(self) -> None:
        from core.settings_runtime import send_key_is_ctrl_enter

        if not self._running_worker():
            tip = t("send_ctrl_enter") if send_key_is_ctrl_enter() else t("send_enter")
            self._send_btn.setToolTip(tip)
        else:
            self._send_btn.set_busy(True)

    def retranslate_ui(self) -> None:
        if hasattr(self, "_model_label"):
            self._model_label.setText(t("chat_model"))
        if hasattr(self, "_workspace_btn"):
            self._workspace_btn.setToolTip(t("chat_workspace_tip"))
        self._input.setPlaceholderText("今天帮你做些什么？输入 @ 引用资料库或生成文件，/ 调用技能")
        self._auto_btn.setText(t("chat_auto"))
        self._auto_btn.setToolTip(t("chat_auto_tip"))
        if hasattr(self, "_skill_store_btn"):
            self._skill_store_btn.setText(t("chat_skill_store"))
            self._skill_store_btn.setToolTip(t("chat_skill_store_tip"))
        if hasattr(self, "_my_skills_btn"):
            self._my_skills_btn.setText(t("chat_my_skills"))
            self._my_skills_btn.setToolTip(t("chat_my_skills_tip"))
        if hasattr(self, "_mcp_btn"):
            self._mcp_btn.setText(t("chat_mcp"))
            self._mcp_btn.setToolTip(t("chat_mcp_tip"))
        if hasattr(self, "_my_skills_action"):
            self._my_skills_action.setText(t("chat_my_skills"))
        if hasattr(self, "_skill_store_action"):
            self._skill_store_action.setText(t("chat_skill_store"))
        if hasattr(self, "_mcp_action"):
            self._mcp_action.setText(t("chat_mcp"))
        if self._perm_btn.isChecked():
            self._perm_btn.setText(t("chat_perm_full"))
        else:
            self._perm_btn.setText(t("chat_perm_default"))
        self._perm_btn.setToolTip(t("chat_perm_tip"))
        self._stop_btn.setToolTip(t("chat_stop_tip"))
        if hasattr(self, "_attach_btn"):
            self._attach_btn.setToolTip(t("chat_attach_tip"))
        if hasattr(self, "_net_btn"):
            self.sync_network_toggle()
        if hasattr(self, "_voice_btn"):
            self._voice_btn.setToolTip("语音输入")
        if hasattr(self, "_mode") and hasattr(self._mode, "retranslate_ui"):
            self._mode.retranslate_ui()
        self.apply_send_key_setting()
        self._load_models()

    def _load_models(self) -> None:
        prev_data = self._model_combo.currentData()
        prev_id = prev_data["id"] if isinstance(prev_data, dict) and "id" in prev_data else None

        self._model_combo.blockSignals(True)
        self._model_combo.clear()
        self._model_combo.addItem(t("chat_local_search"), {"_local_search": True})

        restore_idx = 0
        from core.model_profiles import enrich_model_config
        models = query_all("SELECT * FROM models WHERE enabled=1 ORDER BY is_default DESC, id DESC")
        for i, m in enumerate(models):
            enriched = enrich_model_config(dict(m)) or m
            self._model_combo.addItem(
                f"{enriched['provider_name']} / {enriched['model_name']}", enriched,
            )
            if prev_id and enriched["id"] == prev_id:
                restore_idx = i + 1
            elif not prev_id and enriched.get("is_default"):
                restore_idx = i + 1

        self._model_combo.setCurrentIndex(restore_idx)
        self._model_combo.blockSignals(False)

    @staticmethod
    def _resolve_model(model_data, auto_checked: bool) -> tuple[dict | None, bool]:
        """Returns (model_config, local_search_only)."""
        if isinstance(model_data, dict) and model_data.get("_local_search"):
            return None, True
        model = model_data
        if auto_checked and not isinstance(model, dict):
            model = default_model() or model
        if isinstance(model, dict):
            from core.model_profiles import enrich_model_config
            model = enrich_model_config(dict(model)) or model
        return model, False

    def _on_expert_changed(self, index: int) -> None:
        key = self._expert_combo.currentData()
        self._active_team = None
        self._team_badge.setVisible(False)
        for k, display, prompt in EXPERTS:
            if k == key:
                self._expert_prompt = prompt
                break

    def _load_skill_combo(self) -> None:
        if not hasattr(self, "_skill_combo"):
            return
        prev = self._skill_combo.currentData()
        self._skill_combo.blockSignals(True)
        self._skill_combo.clear()
        self._skill_combo.addItem("Skill: 全部", "")
        try:
            from db.database import query_all
            for row in query_all(
                "SELECT package_name, display_name FROM installed_skill_packages "
                "WHERE enabled=1 ORDER BY display_name"
            ):
                pkg = row.get("package_name") or ""
                label = row.get("display_name") or pkg
                if pkg:
                    self._skill_combo.addItem(f"Skill: {label}", pkg)
        except Exception:
            pass
        idx = self._skill_combo.findData(prev)
        self._skill_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self._skill_combo.blockSignals(False)

    def activate_skill_package(self, package_name: str) -> None:
        """安装 Skill 后选中底栏 Skill 下拉（仅此 Skill 注入 Agent）。"""
        if not hasattr(self, "_skill_combo"):
            return
        self._load_skill_combo()
        key = package_name.strip().lower().replace(" ", "_")
        for i in range(self._skill_combo.count()):
            data = (self._skill_combo.itemData(i) or "").strip().lower().replace(" ", "_")
            if data == key:
                self._skill_combo.setCurrentIndex(i)
                return

    def _active_skill_package(self) -> str:
        if not hasattr(self, "_skill_combo"):
            return ""
        data = self._skill_combo.currentData()
        return str(data) if data else ""

    def _open_skills(self, *, my_skills: bool = False) -> None:
        from ui.dialogs.skill_dialog import SkillDialog
        dlg = SkillDialog(self.window(), initial_tab=1 if my_skills else 0)
        dlg.exec()
        self._load_skill_combo()

    def _open_mcp(self) -> None:
        from ui.dialogs.mcp_dialog import open_mcp_dialog
        open_mcp_dialog(self.window())

    def load_conversation(self, conv_id: int, title: str = "") -> None:
        self._detach_worker_ui()
        self._conversation_id = conv_id
        conv = get_conversation(conv_id)
        if conv and conv.get("mode"):
            self._mode.set_mode(conv["mode"])
        self._conv_title.setText(title or (conv.get("title") if conv else "") or "对话")
        self._reload_conversation_view(conv_id)

    def clear_messages_view(self) -> None:
        """清空当前对话 UI（不删数据库记录）。"""
        if self._conversation_id:
            self._reload_conversation_view(self._conversation_id)
        else:
            self._clear_messages()
            self._welcome.setVisible(True)

    def _render_messages(self, messages: list[dict]) -> None:
        if not messages:
            self._welcome.setVisible(True)
            return
        self._welcome.setVisible(False)
        i = 0
        while i < len(messages):
            msg = messages[i]
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "user":
                if content.startswith(_GUIDE_PREFIX):
                    self._add_widget(GuideMessage(content[len(_GUIDE_PREFIX):]))
                else:
                    self._add_widget(UserMessage(content))
                i += 1
            elif role == "assistant":
                self._add_widget(AgentMessage(content))
                i += 1
            elif role == "artifact":
                try:
                    arts = json.loads(content)
                    self._add_widget(ArtifactMessage(arts))
                except Exception:
                    pass
                i += 1
            elif role == "agent_step":
                thinking_parts: list[str] = []
                while i < len(messages) and messages[i].get("role") == "agent_step":
                    try:
                        data = json.loads(messages[i].get("content", "{}"))
                        part = (data.get("reasoning_content") or data.get("content") or "").strip()
                        if part and (not thinking_parts or thinking_parts[-1] != part):
                            thinking_parts.append(part)
                    except Exception:
                        pass
                    i += 1
                if thinking_parts:
                    block = ThinkingBlock()
                    block.set_text("\n\n".join(thinking_parts))
                    block.finalize()
                    self._add_widget(block)
                continue
            elif role == "tool_call":
                group = ToolCallsGroup()
                while i < len(messages) and messages[i].get("role") == "tool_call":
                    try:
                        data = json.loads(messages[i].get("content", "{}"))
                        group.add_tool(
                            data.get("name", ""),
                            data.get("args", {}),
                            data.get("result", ""),
                        )
                    except Exception:
                        pass
                    i += 1
                group.finalize()
                group.set_collapsed(True)
                self._add_widget(group)
            else:
                i += 1

    def _attach_background_worker(self, conv_id: int) -> None:
        worker = self._background_workers.get(conv_id)
        if not worker or not worker.isRunning():
            self._background_workers.pop(conv_id, None)
            self._set_busy(False)
            return
        self._worker = worker
        self._tool_call_count = self._run_tool_counts.get(conv_id, 0)
        thinking = AgentMessage("🤔 继续执行中…")
        self._run_placeholder = thinking
        self._add_widget(thinking)
        self._welcome.setVisible(False)
        self._set_busy(True)
        pending = self._pending_permissions.pop(conv_id, None)
        if pending:
            self._show_permission_request(pending[0], pending[1])
        self._scroll_to_bottom()

    def _detach_worker_ui(self) -> None:
        """切换视图时保留 worker 信号，任务在后台继续并写入数据库。"""
        if self._worker:
            conv_id = self._worker.conversation_id
            if conv_id and self._worker.isRunning():
                self._background_workers[conv_id] = self._worker
            self._worker = None
        self._run_placeholder = None
        self._set_busy(False)

    def _ensure_worker_connected(self, worker: AgentWorker) -> None:
        if getattr(worker, "_dna_connected", False):
            return
        worker.tool_call.connect(lambda ev, w=worker: self._handle_tool_call(ev, w))
        worker.assistant_step.connect(lambda ev, w=worker: self._handle_assistant_step(ev, w))
        worker.token.connect(lambda tok, w=worker: self._handle_token(tok, w))
        worker.plan_ready.connect(lambda plan, w=worker: self._handle_plan_ready(plan, w))
        worker.task_started.connect(lambda tid, w=worker: self._handle_task_started(tid, w))
        worker.final_reply.connect(lambda reply, w=worker: self._handle_final_reply(reply, w))
        worker.error.connect(lambda err, w=worker: self._handle_error(err, w))
        worker.need_permission.connect(lambda req, w=worker: self._handle_permission(req, w))
        worker.guidance_applied.connect(lambda note, w=worker: self._handle_guidance_applied(note, w))
        worker.finished.connect(lambda w=worker: self._handle_worker_finished(w))
        worker._dna_connected = True

    def _is_viewing(self, conv_id: int | None) -> bool:
        return conv_id is not None and conv_id == self._conversation_id

    def _handle_token(self, token: str, worker: AgentWorker) -> None:
        if not token or not self._is_viewing(worker.conversation_id) or worker is not self._worker:
            return
        self._hide_run_placeholder(self._run_placeholder)
        if self._current_agent_msg is None or _is_placeholder_message(self._current_agent_msg):
            self._current_agent_msg = AgentMessage("")
            self._add_widget(self._current_agent_msg)
            self._run_placeholder = None
        self._current_agent_msg.append_token(token)
        self._scroll_to_bottom()

    def _handle_plan_ready(self, plan_text: str, worker: AgentWorker) -> None:
        conv_id = worker.conversation_id
        self._pending_plan_text = plan_text or ""
        if not self._is_viewing(conv_id) or worker is not self._worker:
            return
        title = "任务计划"
        if plan_text.strip().startswith("#"):
            title = plan_text.strip().splitlines()[0].lstrip("# ").strip() or title
        plan_widget = PlanMessage(title, plan_body=plan_text)
        plan_widget.confirmed.connect(lambda p=plan_text, w=plan_widget: self._execute_confirmed_plan(p, w))
        plan_widget.cancelled.connect(self._on_plan_cancelled)
        self._add_widget(plan_widget)
        self._scroll_to_bottom()

    def _execute_confirmed_plan(self, plan_text: str, plan_widget: PlanMessage | None = None) -> None:
        if plan_widget:
            plan_widget.set_confirmed()
        goal = getattr(self, "_last_user_text", "") or "请按计划执行"
        project = current_project()
        model_data = self._model_combo.currentData()
        model, local_only = self._resolve_model(model_data, self._auto_btn.isChecked())
        if local_only or not model:
            from ui.common import warn
            warn(self, "执行计划需要选择 AI 模型，不能使用「本地检索」。")
            return
        full_access = self._perm_btn.isChecked() or self._session_auto_approve
        self._run_agent(
            goal, model, project, "craft", full_access,
            plan_execute=True, plan_context=plan_text,
        )

    def _on_plan_cancelled(self) -> None:
        self._pending_plan_text = ""

    def _handle_task_started(self, task_id: int, worker: AgentWorker) -> None:
        if task_id > 0:
            self.task_created.emit(task_id)
            self.files_changed.emit()

    def _handle_assistant_step(self, message: dict, worker: AgentWorker) -> None:
        conv_id = worker.conversation_id
        if conv_id and message:
            add_message(
                conv_id,
                "agent_step",
                json.dumps(message, ensure_ascii=False),
            )

        if not self._is_viewing(conv_id) or worker is not self._worker:
            return

        preview = (
            (message.get("reasoning_content") or message.get("content") or "")
            .strip()
        )
        if preview:
            block = self._ensure_thinking_block(self._run_placeholder)
            block.append_text(preview)
            self._scroll_to_bottom()

    def _handle_tool_call(self, event: dict, worker: AgentWorker) -> None:
        conv_id = worker.conversation_id
        name = event.get("name", "")
        args = event.get("args", {})
        result = event.get("result", "")

        if conv_id:
            from core.context_builder import clip_tool_result_for_storage

            add_message(conv_id, "tool_call", json.dumps({
                "id": event.get("id") or "",
                "name": name,
                "args": args,
                "result": clip_tool_result_for_storage(result),
            }, ensure_ascii=False))
            self._run_tool_counts[conv_id] = self._run_tool_counts.get(conv_id, 0) + 1

        if name in _FILE_PRODUCING_TOOLS:
            self.files_changed.emit()

        if not self._is_viewing(conv_id) or worker is not self._worker:
            return

        self._tool_call_count = self._run_tool_counts.get(conv_id, 0)
        group = self._ensure_tool_group(self._run_placeholder)
        group.add_tool(name, args, result)
        self._scroll_to_bottom()

    def _handle_final_reply(self, reply: str, worker: AgentWorker) -> None:
        conv_id = worker.conversation_id
        tool_count = self._run_tool_counts.pop(conv_id, 0) if conv_id else 0
        if conv_id:
            self._background_workers.pop(conv_id, None)

        text = (reply or "").strip()
        if conv_id:
            if text and len(text) > 5:
                add_message(conv_id, "assistant", text)
            elif tool_count > 0:
                add_message(conv_id, "assistant", "✅ 任务已完成。")
            elif text:
                add_message(conv_id, "assistant", text)

        if not self._is_viewing(conv_id) or worker is not self._worker:
            if tool_count > 0:
                self.files_changed.emit()
            return

        if worker.mode == "plan" and not worker.plan_execute:
            if self._current_agent_msg and text:
                self._current_agent_msg.set_text(text)
            elif text:
                self._append_assistant_message(text, conv_id, self._run_placeholder, save_db=False)
            self._tool_group = None
            self._thinking_block = None
            self._run_placeholder = None
            self._set_busy(False)
            from core.settings_runtime import play_notification_sound, try_extract_chat_memory
            try_extract_chat_memory(getattr(self, "_last_user_text", ""), text)
            play_notification_sound()
            self._scroll_to_bottom()
            return

        if self._thinking_block:
            self._thinking_block.finalize()

        if self._tool_group:
            self._tool_group.finalize()
            self._tool_group.set_collapsed(True)

        if text and len(text) > 5:
            self._finalize_assistant_text(text, conv_id, self._run_placeholder, save_db=False)
        elif tool_count > 0:
            self._finalize_assistant_text("✅ 任务已完成。", conv_id, self._run_placeholder, save_db=False)
        else:
            self._finalize_assistant_text(text or "✅ 任务已完成。", conv_id, self._run_placeholder, save_db=False)

        self._current_agent_msg = None

        mode = self._mode.current_mode()
        # 仅在本轮实际调用过工具（多步任务进行中）且明确询问是否继续执行时，才展示确认条
        if (
            mode in ("craft", "plan")
            and tool_count > 0
            and text
            and _looks_like_follow_up_prompt(text)
        ):
            if self._session_auto_approve or self._perm_btn.isChecked():
                QTimer.singleShot(200, lambda: self._send_continue_text("好的，请继续执行。"))
            else:
                follow = FollowUpActionMessage()
                follow.chosen.connect(self._on_follow_up_choice)
                self._add_widget(follow)

        self._tool_group = None
        self._thinking_block = None
        self._run_placeholder = None
        self._set_busy(False)
        if tool_count > 0:
            self.files_changed.emit()
        from core.settings_runtime import play_notification_sound, try_extract_chat_memory
        try_extract_chat_memory(getattr(self, "_last_user_text", ""), text)
        play_notification_sound()
        self._scroll_to_bottom()

    def _handle_error(self, error: str, worker: AgentWorker) -> None:
        conv_id = worker.conversation_id
        if conv_id:
            self._background_workers.pop(conv_id, None)
            self._run_tool_counts.pop(conv_id, None)
            add_message(conv_id, "assistant", f"❌ 错误：{error}")

        if not self._is_viewing(conv_id) or worker is not self._worker:
            return

        if self._tool_group:
            self._tool_group.finalize()
            self._tool_group.set_collapsed(True)
            self._tool_group = None
        if self._thinking_block:
            self._thinking_block.finalize()
            self._thinking_block = None

        self._append_assistant_message(f"❌ 错误：{error}", conv_id, self._run_placeholder, save_db=False)
        self._run_placeholder = None
        self._set_busy(False)
        self._scroll_to_bottom()

    def _handle_worker_finished(self, worker: AgentWorker) -> None:
        conv_id = worker.conversation_id
        if conv_id:
            self._background_workers.pop(conv_id, None)
            self._pending_permissions.pop(conv_id, None)
        if worker is self._worker:
            self._worker = None
        if self._is_viewing(conv_id):
            self._set_busy(False)

    def _handle_permission(self, req: dict, worker: AgentWorker) -> None:
        conv_id = worker.conversation_id
        if not self._is_viewing(conv_id) or worker is not self._worker:
            self._pending_permissions[conv_id] = (req, worker)
            return
        self._show_permission_request(req, worker)

    def _show_permission_request(self, req: dict, worker: AgentWorker) -> None:
        from agent_runtime.permissions import describe_risk, get_risk_level

        name = req.get("name", "")
        args = req.get("args", {}) or {}
        risk = req.get("risk") or get_risk_level(name)
        desc = describe_risk(name)
        preview = json.dumps(args, ensure_ascii=False, indent=2)
        if len(preview) > 400:
            preview = preview[:400] + "\n…"

        widget = PermissionRequestMessage(name, desc, risk, preview)

        def _on_decided(choice: str) -> None:
            if choice == "execute_all":
                self._session_auto_approve = True
                worker.enable_auto_approve()
                worker.submit_permission(True, approve_all=True)
            elif choice == "execute":
                worker.submit_permission(True)
            else:
                worker.submit_permission(False)

        widget.decided.connect(_on_decided)
        self._add_widget(widget)
        self._scroll_to_bottom()

    def clear_conversation(self) -> None:
        self._detach_worker_ui()
        self._ui_session_id += 1
        self._session_auto_approve = False
        self._conversation_id = None
        self._conv_title.setText("")
        self._clear_messages()
        self._welcome.setVisible(True)

    def send(self) -> None:
        """兼容旧调用：运行中默认引导，否则正常发送。"""
        self._on_enter_send()

    def _on_enter_send(self) -> None:
        if self._running_worker():
            self._send_as_guide()
        else:
            self._send_as_normal(interrupt=True)

    def _running_worker(self) -> AgentWorker | None:
        conv_id = self._conversation_id
        if self._worker and self._worker.isRunning():
            return self._worker
        if conv_id and conv_id in self._background_workers:
            worker = self._background_workers[conv_id]
            if worker.isRunning():
                return worker
        return None

    def _send_as_normal(self, *, interrupt: bool = True) -> None:
        text = self._input.toPlainText().strip()
        if not text:
            return
        if interrupt:
            old = self._running_worker()
            if old and old.isRunning():
                old.cancel()
                cid = old.conversation_id
                if cid:
                    self._background_workers.pop(cid, None)
                    self._run_tool_counts.pop(cid, None)
                if old is self._worker:
                    self._detach_worker_ui()
        self._commit_user_message(text, run_agent=True)

    def _send_as_guide(self) -> None:
        text = self._input.toPlainText().strip()
        if not text:
            return
        worker = self._running_worker()
        if not worker or not worker.isRunning():
            self._send_as_normal(interrupt=True)
            return
        display = self._commit_user_message(text, run_agent=False, as_guide=True)
        if worker.submit_guidance(text):
            self._show_status(t("guidance_applied"))
        else:
            self._show_status(t("guidance_failed"))

    def _commit_user_message(
        self,
        text: str,
        *,
        run_agent: bool,
        as_guide: bool = False,
    ) -> str:
        if not self._conversation_id:
            project = current_project()
            mode = self._mode.current_mode()
            self._conversation_id = create_conversation(
                project_id=project["id"] if project else None,
                title=text[:40],
                mode=mode,
            )
            self.conversation_changed.emit(self._conversation_id)

        self._welcome.setVisible(False)
        project = current_project()

        attachments = self._attach_strip.file_paths()
        referenced = self._ref_strip.file_paths()
        display_text = format_mention_for_display(text)
        if referenced:
            ref_names = [Path(f).name for f in referenced]
            display_text += "\n📎 @" + ", @".join(ref_names)
        if attachments:
            file_names = [Path(f).name for f in attachments]
            display_text += "\n🖼 " + ", ".join(file_names)

        stored_text = f"{_GUIDE_PREFIX}{display_text}" if as_guide else display_text
        add_message(
            self._conversation_id, "user", stored_text,
            project_id=project["id"] if project else None,
        )
        self._last_user_text = text
        if as_guide:
            self._add_widget(GuideMessage(display_text))
        else:
            self._add_widget(UserMessage(display_text))
        self._input.clear()
        self._attach_strip.clear_all()
        self._ref_strip.clear_all()
        self._hide_reference_popup()
        self._scroll_to_bottom()

        if not run_agent:
            return stored_text

        mode = self._mode.current_mode()
        model_data = self._model_combo.currentData()
        model, local_only = self._resolve_model(model_data, self._auto_btn.isChecked())
        full_access = self._perm_btn.isChecked() or self._session_auto_approve

        self._run_agent(
            text, model, project, mode, full_access,
            attachments=attachments,
            referenced_files=referenced,
            local_search_only=local_only,
        )
        return stored_text

    def _handle_guidance_applied(self, note: str, worker: AgentWorker) -> None:
        if not self._is_viewing(worker.conversation_id) or worker is not self._worker:
            return

    def _send_continue_text(self, text: str) -> None:
        """Send a canned user reply and continue the agent (for inline action buttons)."""
        if not self._conversation_id or not text.strip():
            return
        self._welcome.setVisible(False)
        project = current_project()
        add_message(
            self._conversation_id, "user", text,
            project_id=project["id"] if project else None,
        )
        self._add_widget(UserMessage(text))
        self._input.clear()
        self._scroll_to_bottom()
        mode = self._mode.current_mode()
        model_data = self._model_combo.currentData()
        model, local_only = self._resolve_model(model_data, self._auto_btn.isChecked())
        full_access = self._perm_btn.isChecked() or self._session_auto_approve
        self._run_agent(text, model, project, mode, full_access, local_search_only=local_only)

    def replay_agent(self, text: str) -> None:
        """Trigger the agent on already-saved user text without re-adding the message."""
        model_data = self._model_combo.currentData()
        model, local_only = self._resolve_model(model_data, self._auto_btn.isChecked())
        project = current_project()
        mode = self._mode.current_mode()
        full_access = self._perm_btn.isChecked() or self._session_auto_approve
        self._run_agent(text, model, project, mode, full_access, local_search_only=local_only)

    def _run_agent(self, text: str, model: dict | None, project: dict | None,
                   mode: str = "craft", full_access: bool = False,
                   attachments: list[str] | None = None,
                   referenced_files: list[str] | None = None,
                   local_search_only: bool = False,
                   plan_execute: bool = False,
                   plan_context: str = "") -> None:
        conv_id = self._conversation_id
        old = self._worker
        if conv_id and conv_id in self._background_workers:
            old = old or self._background_workers.get(conv_id)
        if old and old.isRunning():
            old.cancel()
            cid = old.conversation_id
            if cid:
                self._background_workers.pop(cid, None)
                self._run_tool_counts.pop(cid, None)

        self._detach_worker_ui()
        self._set_busy(True)
        self._tool_call_count = 0
        self._tool_group = None
        self._thinking_block = None
        self._current_agent_msg = None
        if conv_id:
            self._run_tool_counts[conv_id] = 0

        thinking = AgentMessage("🤔 思考中…")
        self._run_placeholder = thinking
        self._add_widget(thinking)
        self._scroll_to_bottom()

        history = get_messages(conv_id) if conv_id else []

        if (
            self._active_team
            and mode in ("craft", "ask")
            and not plan_execute
            and not local_search_only
        ):
            self._run_team_worker(text, model, conv_id, thinking)
            return

        worker = AgentWorker(
            text,
            model=model,
            project=project,
            expert_prompt=self._expert_prompt,
            mode=mode,
            full_access=full_access,
            history=history,
            attachments=attachments or [],
            referenced_files=referenced_files or [],
            conversation_id=conv_id,
            auto_approve=self._session_auto_approve,
            local_search_only=local_search_only,
            plan_execute=plan_execute,
            plan_context=plan_context,
            active_skill_package=self._active_skill_package(),
        )
        self._worker = worker
        if conv_id:
            self._background_workers[conv_id] = worker
        self._ensure_worker_connected(worker)
        worker.start()

    def _run_team_worker(
        self,
        text: str,
        model: dict | None,
        conv_id: int | None,
        placeholder: AgentMessage,
    ) -> None:
        team = self._active_team or {}
        worker = ExpertTeamWorker(
            text,
            team,
            model=model,
            conversation_id=conv_id,
        )
        self._worker = worker
        worker.thinking.connect(
            lambda msg, ph=placeholder: self._update_team_thinking(ph, msg)
        )
        worker.team_plan.connect(
            lambda plan, ph=placeholder: self._update_team_thinking(ph, f"📋 分工计划\n{plan}")
        )
        worker.member_done.connect(self._on_team_member_done)
        worker.final_reply.connect(
            lambda reply, w=worker: self._handle_team_final(reply, w, placeholder)
        )
        worker.error.connect(
            lambda err, w=worker, ph=placeholder: self._handle_team_error(err, w, ph)
        )
        worker.finished.connect(lambda w=worker: self._handle_worker_finished(w))  # type: ignore[arg-type]
        worker.start()

    def _update_team_thinking(self, placeholder: AgentMessage | None, text: str) -> None:
        if placeholder and _qobject_alive(placeholder):
            placeholder.setText(f"👥 {text}")

    def _on_team_member_done(self, member: str, content: str) -> None:
        preview = (content or "")[:120].replace("\n", " ")
        if len(content or "") > 120:
            preview += "…"
        group = self._ensure_tool_group(self._run_placeholder)
        group.add_tool(f"团员·{member}", {}, preview or "（已完成）")

    def _handle_team_final(
        self,
        reply: str,
        worker: ExpertTeamWorker,
        placeholder: AgentMessage | None,
    ) -> None:
        conv_id = worker.conversation_id or self._conversation_id
        if self._tool_group:
            self._tool_group.finalize()
            self._tool_group.set_collapsed(True)
        self._append_assistant_message(reply, conv_id, placeholder)
        self._tool_group = None
        self._run_placeholder = None
        self._set_busy(False)
        from core.settings_runtime import play_notification_sound, try_extract_chat_memory
        try_extract_chat_memory(getattr(self, "_last_user_text", ""), reply)
        play_notification_sound()
        self._scroll_to_bottom()

    def _handle_team_error(
        self,
        error: str,
        worker: ExpertTeamWorker,
        placeholder: AgentMessage | None,
    ) -> None:
        conv_id = worker.conversation_id or self._conversation_id
        if conv_id:
            add_message(conv_id, "assistant", f"❌ 专家团错误：{error}")
        self._append_assistant_message(
            f"❌ 专家团错误：{error}", conv_id, placeholder, save_db=False,
        )
        self._tool_group = None
        self._run_placeholder = None
        self._set_busy(False)
        self._scroll_to_bottom()

    def set_expert(self, name: str, prompt: str, *, team: dict | None = None) -> None:
        self._expert_prompt = prompt
        self._active_team = team if team and team.get("kind") == "team" else None
        if self._active_team:
            n = len(self._active_team.get("members") or [])
            self._team_badge.setText(f"👥 专家团并行 · {n} 位成员")
            self._team_badge.setVisible(True)
            self._conv_title.setText(f"👥 {name}")
        else:
            self._team_badge.setVisible(False)
            if name:
                self._conv_title.setText(f"👤 {name}")
        idx = self._expert_combo.findText(name, Qt.MatchContains)
        if idx >= 0:
            self._expert_combo.setCurrentIndex(idx)
        else:
            prefix = "👥" if self._active_team else "👤"
            self._expert_combo.blockSignals(True)
            self._expert_combo.addItem(f"{prefix} {name}", f"custom_{name}")
            self._expert_combo.setCurrentIndex(self._expert_combo.count() - 1)
            self._expert_combo.blockSignals(False)

    def _hide_run_placeholder(self, placeholder: AgentMessage | None) -> None:
        if placeholder and _qobject_alive(placeholder) and _is_placeholder_message(placeholder):
            placeholder.setVisible(False)

    def _finalize_assistant_text(
        self,
        text: str,
        conv_id: int | None,
        placeholder: AgentMessage | None,
        *,
        save_db: bool = False,
    ) -> None:
        """写入正式回答；若 token 流已创建气泡则复用，避免重复显示。"""
        display = (text or "").strip() or "✅ 任务已完成。"
        self._hide_run_placeholder(placeholder)
        if self._current_agent_msg and not _is_placeholder_message(self._current_agent_msg):
            self._current_agent_msg.set_text(display)
            return
        self._append_assistant_message(display, conv_id, None, save_db=save_db)

    def _append_assistant_message(
        self,
        content: str,
        conv_id: int | None,
        placeholder: AgentMessage | None,
        *,
        save_db: bool = True,
    ) -> AgentMessage:
        text = (content or "").strip()
        if not text:
            text = "✅ 任务已完成。"
        if save_db and conv_id:
            add_message(conv_id, "assistant", text)
        self._hide_run_placeholder(placeholder)
        msg = AgentMessage(text)
        self._add_widget(msg)
        self._current_agent_msg = msg
        return msg

    def _ensure_thinking_block(self, placeholder: AgentMessage | None) -> ThinkingBlock:
        if self._thinking_block is None:
            self._hide_run_placeholder(placeholder)
            self._thinking_block = ThinkingBlock()
            self._add_widget(self._thinking_block)
        return self._thinking_block

    def _ensure_tool_group(self, placeholder: AgentMessage | None) -> ToolCallsGroup:
        if self._tool_group is None:
            self._hide_run_placeholder(placeholder)
            self._tool_group = ToolCallsGroup()
            self._add_widget(self._tool_group)
        return self._tool_group

    def _reload_conversation_view(self, conv_id: int) -> None:
        if self._conversation_id != conv_id:
            return
        title = self._conv_title.text()
        self._clear_messages()
        self._render_messages(get_messages(conv_id))
        self._attach_background_worker(conv_id)
        self._conv_title.setText(title)
        self._scroll_to_bottom()

    def _on_auto_model_toggled(self, checked: bool) -> None:
        if checked:
            self._auto_btn.setText("🤖 自动 ✓")
            for i in range(self._model_combo.count()):
                data = self._model_combo.itemData(i)
                if isinstance(data, dict) and data.get("is_default"):
                    self._model_combo.setCurrentIndex(i)
                    return
            if self._model_combo.count() > 1:
                self._model_combo.setCurrentIndex(1)
        else:
            self._auto_btn.setText("🤖 自动")

    def _on_mode_changed(self, mode: str) -> None:
        if self._conversation_id:
            update_conversation(self._conversation_id, mode=mode)

    def _add_widget(self, widget: QWidget) -> None:
        idx = self._msg_layout.count() - 1
        if idx < 0:
            idx = 0
        self._msg_layout.insertWidget(idx, widget)

    def _clear_messages(self) -> None:
        while self._msg_layout.count() > 1:
            item = self._msg_layout.takeAt(0)
            if item.widget() and item.widget() is not self._welcome:
                item.widget().deleteLater()
        self._step_widget = None
        self._pending_plan = None
        self._current_agent_msg = None
        self._tool_call_count = 0
        self._tool_group = None
        self._run_placeholder = None

    def _scroll_to_bottom(self) -> None:
        if self._scroll_scheduled:
            return
        self._scroll_scheduled = True
        QTimer.singleShot(80, self._do_scroll_to_bottom)

    def _do_scroll_to_bottom(self) -> None:
        self._scroll_scheduled = False
        bar = self._scroll.verticalScrollBar()
        bar.setValue(bar.maximum())

    def _set_busy(self, busy: bool) -> None:
        self._send_btn.set_busy(busy)
        self._stop_btn.setVisible(busy)
        # 生成过程中仍允许编辑输入框，方便用户预先写下一条消息或发送引导
        self._input.setReadOnly(False)
        self._input.setProperty("generating", "true" if busy else "false")
        self._repolish(self._input)
        if hasattr(self, "_voice_btn"):
            self._voice_btn.setEnabled(not busy or self._is_recording_voice)
        if not busy:
            self.apply_send_key_setting()

    def _stop_generation(self) -> None:
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            conv_id = self._worker.conversation_id
            if conv_id:
                self._background_workers.pop(conv_id, None)
        self._set_busy(False)

    def _on_prompt_selected(self, prompt: str) -> None:
        self._input.setPlainText(prompt)
        self.send()

    def _toggle_voice_input(self) -> None:
        if self._is_recording_voice:
            self._stop_voice_recording()
        else:
            self._start_voice_recording()

    def _start_voice_recording(self) -> None:
        try:
            audio_path = str(Path(tempfile.gettempdir()) / "buddy_voice_input.wav")
            self._voice_audio_path = audio_path
            self._voice_session = QMediaCaptureSession(self)
            self._voice_audio_input = QAudioInput(self)
            self._voice_recorder = QMediaRecorder(self)
            self._voice_session.setAudioInput(self._voice_audio_input)
            self._voice_session.setRecorder(self._voice_recorder)
            self._voice_recorder.setOutputLocation(QUrl.fromLocalFile(audio_path))
            self._voice_recorder.record()
        except Exception as exc:
            self._show_status(f"语音输入启动失败：{exc}")
            return

        self._is_recording_voice = True
        self._voice_btn.setText("■")
        self._voice_btn.setProperty("recording", "true")
        self._repolish(self._voice_btn)
        self._show_status("正在录音，再次点击麦克风停止并转写。")

    def _stop_voice_recording(self) -> None:
        if self._voice_recorder:
            self._voice_recorder.stop()
        self._is_recording_voice = False
        self._voice_btn.setText("🎙")
        self._voice_btn.setProperty("recording", "false")
        self._repolish(self._voice_btn)
        self._show_status("录音已停止，正在识别文字…")
        QTimer.singleShot(350, self._transcribe_voice_recording)

    def _transcribe_voice_recording(self) -> None:
        path = self._voice_audio_path
        if not path or not Path(path).is_file() or Path(path).stat().st_size == 0:
            self._show_status("没有录到可识别的音频。")
            return
        model_data = self._model_combo.currentData()
        model, local_only = self._resolve_model(model_data, self._auto_btn.isChecked())
        if local_only:
            model = default_model()
        self._voice_worker = VoiceTranscribeWorker(path, model)
        self._voice_worker.transcribed.connect(self._on_voice_transcribed)
        self._voice_worker.error.connect(self._on_voice_error)
        self._voice_worker.finished.connect(lambda: setattr(self, "_voice_worker", None))
        self._voice_worker.start()

    def _on_voice_transcribed(self, text: str) -> None:
        existing = self._input.toPlainText().rstrip()
        self._input.setPlainText(f"{existing}\n{text}".strip() if existing else text)
        cursor = self._input.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self._input.setTextCursor(cursor)
        self._input.setFocus()
        self._show_status("语音已转成文字。")

    def _on_voice_error(self, error: str) -> None:
        self._show_status(error or "语音识别失败。")

    @staticmethod
    def _repolish(widget: QWidget) -> None:
        widget.style().unpolish(widget)
        widget.style().polish(widget)
        widget.update()

    def _show_status(self, message: str, timeout: int = 4000) -> None:
        win = self.window()
        if win and hasattr(win, "_status"):
            win._status.showMessage(message, timeout)

    def _choose_workspace(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择工作目录")
        if path:
            from core.settings_store import set_setting
            set_setting("workspace_path", path)
            win = self.window()
            if win and hasattr(win, "apply_settings"):
                win.apply_settings("workspace_path")

    def sync_network_toggle(self) -> None:
        from core.settings_store import get_bool

        if not hasattr(self, "_net_btn"):
            return
        self._apply_network_btn_state(get_bool("allow_network", True))

    def _apply_network_btn_state(self, enabled: bool) -> None:
        if not hasattr(self, "_net_btn"):
            return
        self._net_btn.blockSignals(True)
        self._net_btn.setChecked(enabled)
        self._net_btn.setText("")
        self._net_btn.setIcon(self._network_icon_fn(enabled=enabled))
        self._net_btn.setProperty("networkOn", "true" if enabled else "false")
        self._net_btn.setToolTip(t("chat_network_on_tip" if enabled else "chat_network_off_tip"))
        self._repolish(self._net_btn)
        self._net_btn.blockSignals(False)

    def _on_network_clicked(self) -> None:
        from core.settings_store import set_bool

        enabled = self._net_btn.isChecked()
        set_bool("allow_network", enabled)
        self._apply_network_btn_state(enabled)
        self._show_status(
            t("chat_network_on_status" if enabled else "chat_network_off_status"),
            2500,
        )

    def _toggle_permission(self) -> None:
        if self._perm_btn.isChecked():
            self._perm_btn.setText(t("chat_perm_full"))
        else:
            self._perm_btn.setText(t("chat_perm_default"))

    def _on_follow_up_choice(self, choice: str) -> None:
        if choice == "execute_all":
            self._session_auto_approve = True
            self._send_continue_text("好的，后续请直接执行，无需再向我确认。")
        elif choice == "execute":
            self._send_continue_text("好的，请继续执行。")
        else:
            self._send_continue_text("不用了，取消这次操作。")

    def _attach_file(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, "附加文件", "",
            "图片/音频 (*.png *.jpg *.jpeg *.gif *.bmp *.webp *.mp3 *.wav *.ogg *.m4a *.flac);;"
            "图片 (*.png *.jpg *.jpeg *.gif *.bmp *.webp);;"
            "音频 (*.mp3 *.wav *.ogg *.m4a *.flac *.aac);;"
            "所有文件 (*.*)",
        )
        for path in paths:
            self._attach_strip.add_file(path)

    def _on_files_dropped(self, files: list[str]) -> None:
        for f in files:
            self._attach_strip.add_file(f)

    def _on_attachment_removed(self, path: str) -> None:
        pass

    def _on_reference_trigger(self, query: str, global_pos) -> None:
        if not self._ref_popup:
            return
        self._ref_popup.set_query(query)
        self._ref_popup.move(global_pos)
        self._ref_popup.show()
        self._ref_popup_visible = True

    def _hide_reference_popup(self) -> None:
        if self._ref_popup and self._ref_popup.isVisible():
            self._ref_popup.hide()
        self._ref_popup_visible = False

    def _on_reference_chosen(self, item: dict) -> None:
        path = item.get("path", "")
        name = item.get("name") or Path(path).name
        if not path:
            return
        self._input.insert_file_reference(name)
        self._ref_strip.add_reference(
            path,
            icon=item.get("icon", "📎"),
            category=item.get("subtitle", ""),
        )
        self._hide_reference_popup()
        self._input.setFocus()

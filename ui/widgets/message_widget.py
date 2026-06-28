from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy,
    QTextBrowser, QVBoxLayout, QWidget,
)

from core.app_identity import APP_NAME
from utils.markdown_renderer import markdown_to_html


def _qobject_alive(obj) -> bool:
    if obj is None:
        return False
    try:
        from shiboken6 import isValid
        return isValid(obj)
    except Exception:
        return True


class UserMessage(QFrame):
    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        self.setObjectName("UserMessage")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        label = QLabel(text)
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        label.setObjectName("UserMessageText")
        layout.addWidget(label)


class AgentMessage(QFrame):
    regenerate_requested = Signal()

    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        self.setObjectName("AgentMessage")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(6)

        header_row = QHBoxLayout()
        header_row.setSpacing(6)
        header = QLabel(APP_NAME)
        header.setObjectName("AgentMessageHeader")
        header_row.addWidget(header)
        self._status_label = QLabel("")
        self._status_label.setObjectName("AgentMessageStatus")
        header_row.addWidget(self._status_label)
        header_row.addStretch()
        layout.addLayout(header_row)

        self._raw_text = text
        self._browser = QTextBrowser()
        self._browser.setObjectName("AgentMessageBrowser")
        self._browser.setOpenExternalLinks(False)
        self._browser.setFrameShape(QFrame.NoFrame)
        self._browser.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._browser.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._browser.document().setDocumentMargin(0)
        self._browser.anchorClicked.connect(self._on_link_clicked)
        self._browser.setHtml(markdown_to_html(text))
        self._browser.document().contentsChanged.connect(self._adjust_height)
        self._adjust_height()
        layout.addWidget(self._browser)

        self._action_bar = QFrame()
        self._action_bar.setObjectName("MessageActionBar")
        action_layout = QHBoxLayout(self._action_bar)
        action_layout.setContentsMargins(0, 4, 0, 0)
        action_layout.setSpacing(2)
        for icon, tooltip, callback in [
            ("📋", "复制", self._copy_text),
            ("👍", "有帮助", lambda: None),
            ("👎", "没帮助", lambda: None),
            ("🔄", "重新生成", lambda: self.regenerate_requested.emit()),
            ("🔊", "朗读", self._read_aloud),
        ]:
            btn = QPushButton(icon)
            btn.setObjectName("MessageActionButton")
            btn.setToolTip(tooltip)
            btn.setFixedSize(30, 26)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(callback)
            action_layout.addWidget(btn)
        action_layout.addStretch()
        self._action_bar.setVisible(False)
        layout.addWidget(self._action_bar)

    def _adjust_height(self) -> None:
        if not _qobject_alive(self._browser):
            return
        self._browser.document().setTextWidth(self._browser.viewport().width())
        doc_height = self._browser.document().size().height()
        new_h = max(int(doc_height) + 8, 28)
        self._browser.setFixedHeight(new_h)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._adjust_height()

    def set_text(self, text: str) -> None:
        if not _qobject_alive(self._browser):
            return
        self._raw_text = text
        self._browser.setHtml(markdown_to_html(text))
        self._adjust_height()
        from PySide6.QtCore import QTimer
        QTimer.singleShot(100, self._adjust_height)
        is_final = not text.startswith("🤔") and not text.startswith("🔧") and len(text) > 10
        if _qobject_alive(self._action_bar):
            self._action_bar.setVisible(is_final)

    def append_token(self, token: str) -> None:
        if not token or not _qobject_alive(self._browser):
            return
        self._raw_text = (self._raw_text or "") + token
        if self._raw_text.startswith("🤔"):
            self._raw_text = self._raw_text.lstrip("🤔 思考中…").lstrip()
        self._browser.setHtml(markdown_to_html(self._raw_text))
        self._adjust_height()

    def append_text(self, chunk: str) -> None:
        if not _qobject_alive(self._browser):
            return
        self._raw_text += chunk
        self._browser.setHtml(markdown_to_html(self._raw_text))
        self._adjust_height()

    def _on_link_clicked(self, url) -> None:
        """Handle clicks on links — open file paths locally, URLs in browser."""
        import webbrowser
        link = url.toString() if hasattr(url, "toString") else str(url)
        link = link.replace("file:///", "").replace("file://", "")

        p = Path(link)
        if p.exists():
            os.startfile(str(p))
            return
        if link.replace("\\", "/").count("/") >= 2:
            p2 = Path(link.replace("/", "\\"))
            if p2.exists():
                os.startfile(str(p2))
                return
        if link.startswith("http://") or link.startswith("https://"):
            webbrowser.open(link)
            return
        webbrowser.open(link)

    def _copy_text(self) -> None:
        clipboard = QGuiApplication.clipboard()
        if clipboard:
            clipboard.setText(self._raw_text)

    def _read_aloud(self) -> None:
        try:
            import subprocess
            text = self._raw_text[:500].replace('"', '\\"').replace("'", "\\'")
            subprocess.Popen(
                ["powershell", "-Command",
                 f"Add-Type -AssemblyName System.Speech; "
                 f"$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                 f"$s.Speak('{text}')"],
                shell=False,
            )
        except Exception:
            pass


class StepProgressMessage(QFrame):
    def __init__(self, task_id: int, steps: list[dict] | None = None, parent=None):
        super().__init__(parent)
        self.setObjectName("StepProgressMessage")
        self.task_id = task_id
        self._step_labels: dict[int, QLabel] = {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(6)
        header = QLabel(f"任务 #{task_id} 执行中")
        header.setObjectName("StepHeader")
        layout.addWidget(header)
        self._steps_layout = QVBoxLayout()
        self._steps_layout.setSpacing(4)
        layout.addLayout(self._steps_layout)
        if steps:
            for s in steps:
                self.add_step(s.get("step_index", 0), s.get("step_name", ""), s.get("status", "pending"))

    def add_step(self, index: int, name: str, status: str = "pending") -> None:
        icon = {"pending": "○", "running": "◉", "completed": "●", "failed": "✕"}.get(status, "○")
        label = QLabel(f"  {icon}  {index}. {name}")
        label.setObjectName(f"StepItem_{status}")
        label.setProperty("step_status", status)
        self._step_labels[index] = label
        self._steps_layout.addWidget(label)

    def update_step(self, index: int, status: str) -> None:
        label = self._step_labels.get(index)
        if not label:
            return
        icon = {"pending": "○", "running": "◉", "completed": "●", "failed": "✕"}.get(status, "○")
        text = label.text()
        parts = text.strip().split(". ", 1)
        name = parts[1] if len(parts) > 1 else parts[0]
        label.setText(f"  {icon}  {index}. {name}")
        label.setProperty("step_status", status)
        label.style().unpolish(label)
        label.style().polish(label)

    def set_completed(self, artifact_count: int = 0) -> None:
        header = self.findChild(QLabel, "StepHeader")
        if header:
            header.setText(f"任务 #{self.task_id} 已完成  ·  产物 {artifact_count} 个")


class ArtifactMessage(QFrame):
    def __init__(self, artifacts: list[dict], parent=None):
        super().__init__(parent)
        self.setObjectName("ArtifactMessage")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)
        header = QLabel(f"生成产物 ({len(artifacts)})")
        header.setObjectName("ArtifactHeader")
        layout.addWidget(header)
        for art in artifacts:
            row = QHBoxLayout()
            path = Path(art.get("path", ""))
            icon = {"docx": "📄", "xlsx": "📊", "pptx": "📑", "py": "🐍"}.get(
                art.get("type", ""), "📁"
            )
            name = QLabel(f"{icon}  {path.name}")
            name.setObjectName("ArtifactName")
            name.setCursor(Qt.PointingHandCursor)
            row.addWidget(name, 1)
            open_btn = QPushButton("打开")
            open_btn.setObjectName("ArtifactAction")
            open_btn.setCursor(Qt.PointingHandCursor)
            open_btn.clicked.connect(lambda _, p=str(path): os.startfile(p) if p and Path(p).exists() else None)
            row.addWidget(open_btn)
            folder_btn = QPushButton("目录")
            folder_btn.setObjectName("ArtifactAction")
            folder_btn.setCursor(Qt.PointingHandCursor)
            folder_btn.clicked.connect(lambda _, p=str(path): os.startfile(str(Path(p).parent)) if p and Path(p).exists() else None)
            row.addWidget(folder_btn)
            layout.addLayout(row)


class PlanMessage(QFrame):
    confirmed = Signal()
    cancelled = Signal()

    def __init__(
        self,
        plan_title: str,
        steps: list[dict] | None = None,
        plan_body: str = "",
        parent=None,
    ):
        super().__init__(parent)
        self.setObjectName("PlanMessage")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)
        header = QLabel(f"执行计划：{plan_title}")
        header.setObjectName("PlanHeader")
        layout.addWidget(header)
        if plan_body:
            body = QLabel(plan_body)
            body.setObjectName("PlanBody")
            body.setWordWrap(True)
            body.setTextInteractionFlags(Qt.TextSelectableByMouse)
            layout.addWidget(body)
        elif steps:
            for s in steps:
                label = QLabel(f"  {s.get('step_index', 0)}. {s.get('name', '')}  →  {s.get('tool', '')}")
                label.setObjectName("PlanStep")
                layout.addWidget(label)
        self._actions = QHBoxLayout()
        self._actions.setSpacing(8)
        self._actions.addStretch()
        cancel_btn = QPushButton("取消")
        cancel_btn.setProperty("variant", "ghost")
        cancel_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn.clicked.connect(self.cancelled.emit)
        self._confirm_btn = QPushButton("确认执行")
        self._confirm_btn.setProperty("variant", "primary")
        self._confirm_btn.setCursor(Qt.PointingHandCursor)
        self._confirm_btn.clicked.connect(self.confirmed.emit)
        self._actions.addWidget(cancel_btn)
        self._actions.addWidget(self._confirm_btn)
        layout.addLayout(self._actions)

    def set_confirmed(self) -> None:
        self._confirm_btn.setText("已确认")
        self._confirm_btn.setEnabled(False)


class PermissionRequestMessage(QFrame):
    """Inline high-risk tool approval in the chat stream."""

    decided = Signal(str)  # execute | reject | execute_all

    def __init__(
        self,
        tool_name: str,
        description: str,
        risk: str,
        args_preview: str,
        parent=None,
    ):
        super().__init__(parent)
        self.setObjectName("PermissionRequestMessage")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)

        header = QLabel("⚠️ 操作确认（默认权限）")
        header.setObjectName("PermissionRequestHeader")
        layout.addWidget(header)

        summary = QLabel(
            f"Agent 请求执行：<b>{tool_name}</b>（{description}）\n"
            f"风险等级：<b>{risk}</b>"
        )
        summary.setObjectName("PermissionRequestSummary")
        summary.setWordWrap(True)
        summary.setTextFormat(Qt.RichText)
        layout.addWidget(summary)

        if args_preview:
            args_box = QLabel(f"参数：\n{args_preview}")
            args_box.setObjectName("PermissionRequestArgs")
            args_box.setWordWrap(True)
            args_box.setTextInteractionFlags(Qt.TextSelectableByMouse)
            layout.addWidget(args_box)

        hint = QLabel("请选择，无需在输入框打字：")
        hint.setObjectName("PermissionRequestStatus")
        layout.addWidget(hint)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        self._reject_btn = QPushButton("拒绝")
        self._reject_btn.setProperty("variant", "ghost")
        self._reject_btn.setCursor(Qt.PointingHandCursor)
        self._reject_btn.clicked.connect(lambda: self._decide("reject"))
        btn_row.addWidget(self._reject_btn)
        self._execute_btn = QPushButton("执行")
        self._execute_btn.setProperty("variant", "primary")
        self._execute_btn.setCursor(Qt.PointingHandCursor)
        self._execute_btn.clicked.connect(lambda: self._decide("execute"))
        btn_row.addWidget(self._execute_btn)
        self._execute_all_btn = QPushButton("以下都执行")
        self._execute_all_btn.setProperty("variant", "secondary")
        self._execute_all_btn.setCursor(Qt.PointingHandCursor)
        self._execute_all_btn.clicked.connect(lambda: self._decide("execute_all"))
        btn_row.addWidget(self._execute_all_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self._status = QLabel("")
        self._status.setObjectName("PermissionRequestStatus")
        layout.addWidget(self._status)

    def _decide(self, choice: str) -> None:
        self._execute_btn.setEnabled(False)
        self._reject_btn.setEnabled(False)
        self._execute_all_btn.setEnabled(False)
        labels = {
            "execute": "✅ 已确认执行…",
            "reject": "❌ 已拒绝",
            "execute_all": "✅ 后续操作将自动执行…",
        }
        self._status.setText(labels.get(choice, ""))
        self.decided.emit(choice)


class FollowUpActionMessage(QFrame):
    """Inline continue / reject / auto-approve when Agent asks a follow-up question."""

    chosen = Signal(str)  # execute | reject | execute_all

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("FollowUpActionMessage")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(8)

        header = QLabel("Agent 等待你的确认，请选择（无需打字）：")
        header.setObjectName("FollowUpActionHeader")
        layout.addWidget(header)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        reject_btn = QPushButton("拒绝")
        reject_btn.setProperty("variant", "ghost")
        reject_btn.setCursor(Qt.PointingHandCursor)
        reject_btn.clicked.connect(lambda: self._choose("reject"))
        btn_row.addWidget(reject_btn)
        execute_btn = QPushButton("执行")
        execute_btn.setProperty("variant", "primary")
        execute_btn.setCursor(Qt.PointingHandCursor)
        execute_btn.clicked.connect(lambda: self._choose("execute"))
        btn_row.addWidget(execute_btn)
        execute_all_btn = QPushButton("以下都执行")
        execute_all_btn.setProperty("variant", "secondary")
        execute_all_btn.setCursor(Qt.PointingHandCursor)
        execute_all_btn.clicked.connect(lambda: self._choose("execute_all"))
        btn_row.addWidget(execute_all_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self._buttons = (reject_btn, execute_btn, execute_all_btn)
        self._status = QLabel("")
        self._status.setObjectName("FollowUpActionStatus")
        layout.addWidget(self._status)

    def _choose(self, choice: str) -> None:
        for btn in self._buttons:
            btn.setEnabled(False)
        labels = {
            "execute": "正在继续执行…",
            "reject": "已取消",
            "execute_all": "已开启自动执行，正在继续…",
        }
        self._status.setText(labels.get(choice, ""))
        self.chosen.emit(choice)


class ToolCallMessage(QFrame):
    """Displays a single tool call with its name, arguments, and result."""

    def __init__(self, name: str, args: dict, result: str = "", *, compact: bool = False, parent=None):
        super().__init__(parent)
        self.setObjectName("ToolCallMessage")
        self._compact = compact
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12 if compact else 16, 6 if compact else 10, 12 if compact else 16, 6 if compact else 10)
        layout.setSpacing(4)

        TOOL_ICONS = {
            "shell_run": "⚡", "file_read": "📖", "file_write": "✏️",
            "file_list": "📂", "file_delete": "🗑️", "software_launch": "🚀",
            "open_url": "🌐", "office_word_create": "📄", "office_excel_create": "📊",
            "office_ppt_create": "📑", "code_create": "💻", "keyboard_type": "⌨️",
            "hotkey_press": "🎹", "window_focus": "🪟", "list_apps": "📋",
            "ui_locate": "🎯", "ui_click": "👆",
            "mouse_click": "🖱️", "screen_capture": "📸", "skill_install": "📦",
        }
        icon = TOOL_ICONS.get(name, "🔧")
        args_text = self._format_args(name, args)

        header = QHBoxLayout()
        header.setSpacing(6)
        icon_label = QLabel(icon)
        icon_label.setObjectName("ToolCallIcon")
        icon_label.setFixedWidth(20)
        header.addWidget(icon_label)

        title_parts = [name]
        if compact and args_text:
            short = args_text if len(args_text) <= 72 else args_text[:72] + "…"
            title_parts.append(short)
        name_label = QLabel("  ·  ".join(title_parts) if len(title_parts) > 1 else name)
        name_label.setObjectName("ToolCallName")
        name_label.setWordWrap(False)
        header.addWidget(name_label, 1)

        self._toggle_btn = QPushButton("▶")
        self._toggle_btn.setObjectName("ToolCallToggle")
        self._toggle_btn.setFixedSize(22, 22)
        self._toggle_btn.setCursor(Qt.PointingHandCursor)
        self._toggle_btn.clicked.connect(self._toggle_details)
        header.addWidget(self._toggle_btn)
        layout.addLayout(header)

        self._args_label = None
        if args_text and not compact:
            self._args_label = QLabel(args_text)
            self._args_label.setObjectName("ToolCallArgs")
            self._args_label.setWordWrap(True)
            self._args_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            layout.addWidget(self._args_label)

        self._detail_frame = QFrame()
        self._detail_frame.setObjectName("ToolCallDetail")
        self._detail_frame.setVisible(False)
        detail_layout = QVBoxLayout(self._detail_frame)
        detail_layout.setContentsMargins(4, 4, 4, 4)
        detail_layout.setSpacing(2)
        if args_text and compact:
            args_label = QLabel(args_text)
            args_label.setObjectName("ToolCallArgs")
            args_label.setWordWrap(True)
            args_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            detail_layout.addWidget(args_label)
        result_preview = result[:500] if result else "(no output)"
        if len(result) > 500:
            result_preview += "..."
        self._result_label = QLabel(result_preview)
        self._result_label.setObjectName("ToolCallResult")
        self._result_label.setWordWrap(True)
        self._result_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        detail_layout.addWidget(self._result_label)
        layout.addWidget(self._detail_frame)

    def set_result(self, result: str) -> None:
        preview = result[:500]
        if len(result) > 500:
            preview += "..."
        self._result_label.setText(preview)

    def _toggle_details(self) -> None:
        visible = not self._detail_frame.isVisible()
        self._detail_frame.setVisible(visible)
        self._toggle_btn.setText("▼" if visible else "▶")

    @staticmethod
    def _format_args(name: str, args: dict) -> str:
        if name == "shell_run":
            return f"$ {args.get('command', '')}"
        if name in ("file_read", "file_list", "file_delete"):
            return f"路径: {args.get('path', '')}"
        if name == "file_write":
            content = args.get("content", "")
            preview = content[:100] + "..." if len(content) > 100 else content
            return f"写入: {args.get('path', '')}  ({len(content)} 字符)"
        if name == "software_launch":
            return f"启动: {args.get('name', '')} {args.get('args', '')}"
        if name == "open_url":
            return f"URL: {args.get('url', '')}"
        if name in ("office_word_create", "office_excel_create", "office_ppt_create"):
            return f"标题: {args.get('title', '')}  文件: {args.get('filename', '')}"
        if name == "code_create":
            return f"文件: {args.get('path', '')}  ({len(args.get('content', ''))} 字符)"
        if name == "keyboard_type":
            text = args.get("text", "")
            return f"输入: {text[:50]}{'...' if len(text) > 50 else ''}"
        if name == "hotkey_press":
            return f"快捷键: {args.get('keys', '')}"
        if name == "mouse_click":
            return f"点击: ({args.get('x', 0)}, {args.get('y', 0)})"
        if name == "skill_install":
            return f"URL: {args.get('url', '')}"
        if name == "window_focus":
            return f"窗口: {args.get('title', '')}"
        if name in ("ui_click", "ui_locate"):
            parts = [f"目标: {args.get('target', '')}"]
            if args.get("window_title"):
                parts.append(f"窗口: {args.get('window_title')}")
            return "  ".join(parts)
        return ""


class ToolCallsGroup(QFrame):
    """Collapsible group of tool calls for one agent run."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ToolCallsGroup")
        self._count = 0
        self._collapsed = True
        self._running = True

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._header_btn = QPushButton()
        self._header_btn.setObjectName("ToolCallsGroupHeader")
        self._header_btn.setCursor(Qt.PointingHandCursor)
        self._header_btn.clicked.connect(self._toggle_collapsed)
        header_layout = QHBoxLayout(self._header_btn)
        header_layout.setContentsMargins(12, 8, 12, 8)
        header_layout.setSpacing(8)
        self._summary_label = QLabel("🔧 执行中…")
        self._summary_label.setObjectName("ToolCallsGroupSummary")
        header_layout.addWidget(self._summary_label, 1)
        self._chevron = QLabel("▶")
        self._chevron.setObjectName("ToolCallsGroupChevron")
        self._chevron.setFixedWidth(16)
        header_layout.addWidget(self._chevron)
        layout.addWidget(self._header_btn)

        self._body = QFrame()
        self._body.setObjectName("ToolCallsGroupBody")
        self._body.setVisible(False)
        body_layout = QVBoxLayout(self._body)
        body_layout.setContentsMargins(8, 4, 8, 8)
        body_layout.setSpacing(4)
        self._tools_layout = QVBoxLayout()
        self._tools_layout.setSpacing(4)
        body_layout.addLayout(self._tools_layout)
        layout.addWidget(self._body)

    @property
    def count(self) -> int:
        return self._count

    def add_tool(self, name: str, args: dict, result: str = "") -> None:
        self._count += 1
        self._tools_layout.addWidget(ToolCallMessage(name, args, result, compact=True))
        self._refresh_summary()

    def finalize(self) -> None:
        self._running = False
        self._refresh_summary()

    def set_collapsed(self, collapsed: bool) -> None:
        self._collapsed = collapsed
        self._body.setVisible(not collapsed)
        self._chevron.setText("▶" if collapsed else "▼")

    def _toggle_collapsed(self) -> None:
        self.set_collapsed(not self._collapsed)

    def _refresh_summary(self) -> None:
        if self._running:
            self._summary_label.setText(f"🔧 执行中… ({self._count} 个操作)")
        else:
            self._summary_label.setText(f"🔧 已执行 {self._count} 个操作")


class WelcomeWidget(QWidget):
    prompt_selected = Signal(str)

    CATEGORIES = {
        "日常办公": [
            ("📋 今日待办", "帮我整理一份今日工作待办"),
            ("📊 项目汇报", "帮我生成项目汇报 PPT"),
            ("📁 文件整理", "帮我总结当前项目资料"),
            ("📈 数据分析", "帮我生成数据分析 Excel"),
        ],
        "代码开发": [
            ("🐍 Python 脚本", "帮我写一个 Python 工具脚本"),
            ("🌐 Web 应用", "帮我搭建一个简单的 Web 应用"),
            ("🔧 自动化脚本", "写一个自动化办公脚本"),
            ("📦 项目搭建", "帮我初始化一个新的开发项目"),
        ],
        "设计创意": [
            ("✍️ 文案撰写", "帮我写一篇产品推广文案"),
            ("📑 方案撰写", "帮我生成一份技术方案 Word"),
            ("💡 头脑风暴", "围绕一个主题做创意头脑风暴"),
            ("🎨 设计建议", "推荐当下流行的 UI 设计趋势"),
        ],
    }

    SUB_CATEGORIES = [
        ("📄 文档处理", "帮我处理和分析一份文档"),
        ("💰 金融服务", "帮我做一份简单的财务分析"),
        ("🔧 现场测试", "根据标准生成现场测试记录"),
        ("📖 标准查询", "帮我查询公路机电验收依据"),
        ("📑 投标响应", "生成投标技术响应方案 Word"),
        ("📚 更多", "你还能帮我做什么？"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(48, 0, 48, 48)
        layout.setSpacing(12)
        layout.addStretch(2)

        title = QLabel(APP_NAME)
        title.setObjectName("WelcomeTitle")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        subtitle = QLabel("你的职场超能力")
        subtitle.setObjectName("WelcomeSubtitle")
        subtitle.setAlignment(Qt.AlignCenter)
        layout.addWidget(subtitle)

        layout.addSpacing(8)

        cat_row = QHBoxLayout()
        cat_row.setAlignment(Qt.AlignCenter)
        cat_row.setSpacing(8)
        self._cat_buttons: dict[str, QPushButton] = {}
        for cat_name in self.CATEGORIES:
            btn = QPushButton(f"  {cat_name}")
            btn.setObjectName("WelcomeCatButton")
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _, c=cat_name: self._select_category(c))
            self._cat_buttons[cat_name] = btn
            cat_row.addWidget(btn)
        layout.addLayout(cat_row)

        sub_row = QHBoxLayout()
        sub_row.setAlignment(Qt.AlignCenter)
        sub_row.setSpacing(16)
        for sub_name, sub_prompt in self.SUB_CATEGORIES:
            lbl = QPushButton(sub_name)
            lbl.setObjectName("WelcomeSubLink")
            lbl.setCursor(Qt.PointingHandCursor)
            lbl.clicked.connect(lambda _, p=sub_prompt: self.prompt_selected.emit(p))
            sub_row.addWidget(lbl)
        layout.addLayout(sub_row)

        layout.addSpacing(8)

        from ui.components import flow_grid, ActionCard
        self._card_container = QWidget()
        self._card_layout = QVBoxLayout(self._card_container)
        self._card_layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._card_container)

        first_cat = list(self.CATEGORIES.keys())[0]
        self._select_category(first_cat)

        layout.addStretch(3)

    def _select_category(self, cat_name: str):
        for k, btn in self._cat_buttons.items():
            btn.setChecked(k == cat_name)

        from ui.components import clear_layout, flow_grid, ActionCard
        clear_layout(self._card_layout)

        scenes = self.CATEGORIES.get(cat_name, [])
        cards = []
        for title_text, prompt in scenes:
            card = ActionCard(title_text, prompt)
            card.clicked.connect(lambda p=prompt: self.prompt_selected.emit(p))
            cards.append(card)
        self._card_layout.addWidget(flow_grid(cards, columns=4))

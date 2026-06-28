from __future__ import annotations

import json
import uuid

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QScrollArea, QTextEdit, QVBoxLayout, QWidget,
)

from core.conversation_manager import add_message, create_conversation
from core.settings_store import get_setting, set_setting


AUTOMATION_TEMPLATES = [
    ("📰", "每日 AI 新闻推送", "关注当天 AI 领域的重要动态，刷新 AI Coding 与具身智能进展"),
    ("🔤", "每日 5 个英语单词", "每天推荐 5 个高频实用英语单词，含词义、音标、例句"),
    ("📖", "每日儿童睡前故事", "生成 3-5 分钟可读的温和睡前故事，情节完整并附简短寓意"),
    ("📋", "每周工作报", "每周五汇总仓库 PR 与 Issue 进展，输出关键更新与待关注项"),
    ("🎬", "经典电影推荐", "推荐一部高分经典电影，简要介绍剧情、亮点和观看建议"),
    ("📅", "历史上的今天", "从科技、电影、音乐等领域搜选一个今天发生过的有趣历史"),
    ("❓", "每日一个为什么", "每天提出一个有趣问题，先提问再解答，语气轻松、通俗易懂"),
    ("👨‍👩‍👧", "父母联系提醒", "每周日 10:00 提醒你给家人打电话或发消息，简单问候就好"),
    ("🏥", "体检预约提醒", "按医嘱提醒你确认体检时间、准备证件、注意事项"),
    ("💼", "面试准备提醒", "工作日每 2 小时提醒你复习大模型面试内容，并生成 3 个模拟题"),
    ("📝", "会议前准备", "在会议开始前提醒你整理议程、目标，确认问题和关注话题"),
    ("🐱", "可爱萌宠手机壁纸", "随机从 7 种不同风格中挑选一种，为你生成一张 9:16 壁纸"),
]

_WEEKDAY_LABELS = [
    ("周一", 0), ("周二", 1), ("周三", 2), ("周四", 3),
    ("周五", 4), ("周六", 5), ("周日", 6),
]

_SCHEDULE_TYPE_LABELS = [
    ("仅手动运行", "manual"),
    ("每日定时", "daily"),
    ("每周定时", "weekly"),
]


def _format_schedule(entry: dict) -> str:
    sched = entry.get("schedule") or {}
    stype = sched.get("type", "manual")
    if stype == "manual":
        return "手动"
    if not sched.get("enabled", True):
        return "已暂停"
    time_str = sched.get("time", "09:00")
    if stype == "daily":
        return f"每日 {time_str}"
    if stype == "weekly":
        wd = sched.get("weekday", 6)
        label = next((n for n, v in _WEEKDAY_LABELS if v == int(wd)), "周日")
        return f"每{label} {time_str}"
    return "手动"


class _AutomationCard(QFrame):
    clicked = Signal(str, str)

    def __init__(self, icon: str, title: str, desc: str, parent=None):
        super().__init__(parent)
        self.setObjectName("ActionCard")
        self.setCursor(Qt.PointingHandCursor)
        self._title = title
        self._desc = desc

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(12)

        ic = QLabel(icon)
        ic.setFixedSize(36, 36)
        ic.setAlignment(Qt.AlignCenter)
        ic.setStyleSheet("font-size:18px; background:#1e293b; border-radius:8px;")
        layout.addWidget(ic)

        col = QVBoxLayout()
        col.setSpacing(2)
        t = QLabel(title)
        t.setObjectName("CardTitle")
        t.setStyleSheet("font-size:13px; font-weight:600;")
        col.addWidget(t)
        d = QLabel(desc)
        d.setObjectName("MutedLabel")
        d.setWordWrap(True)
        col.addWidget(d)
        layout.addLayout(col, 1)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self._title, self._desc)
        super().mouseReleaseEvent(event)


class _SavedAutomationCard(QFrame):
    clicked = Signal(str, str)
    delete_requested = Signal(int)

    def __init__(self, index: int, entry: dict, parent=None):
        super().__init__(parent)
        self.setObjectName("ActionCard")
        self.setCursor(Qt.PointingHandCursor)
        self._index = index
        self._name = entry.get("name", "")
        self._prompt = entry.get("prompt", "")
        sched_text = _format_schedule(entry)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(12)

        ic = QLabel("⚙")
        ic.setFixedSize(36, 36)
        ic.setAlignment(Qt.AlignCenter)
        ic.setStyleSheet("font-size:18px; background:#1e293b; border-radius:8px;")
        layout.addWidget(ic)

        col = QVBoxLayout()
        col.setSpacing(2)
        top = QHBoxLayout()
        t = QLabel(self._name)
        t.setObjectName("CardTitle")
        t.setStyleSheet("font-size:13px; font-weight:600;")
        top.addWidget(t)
        sched_lbl = QLabel(sched_text)
        sched_lbl.setObjectName("MutedLabel")
        sched_lbl.setStyleSheet("font-size:11px;")
        top.addWidget(sched_lbl)
        top.addStretch()
        col.addLayout(top)
        d = QLabel(self._prompt if len(self._prompt) <= 60 else self._prompt[:57] + "…")
        d.setObjectName("MutedLabel")
        d.setWordWrap(True)
        col.addWidget(d)
        layout.addLayout(col, 1)

        del_btn = QPushButton("✕")
        del_btn.setFixedSize(24, 24)
        del_btn.setCursor(Qt.PointingHandCursor)
        del_btn.setStyleSheet(
            "QPushButton{background:transparent;color:#94a3b8;border:none;font-size:14px;}"
            "QPushButton:hover{color:#ef4444;}"
        )
        del_btn.clicked.connect(lambda: self.delete_requested.emit(self._index))
        layout.addWidget(del_btn)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self._name, self._prompt)
        super().mouseReleaseEvent(event)


class _NewAutomationDialog(QDialog):
    def __init__(self, parent=None, *, preset_name: str = "", preset_prompt: str = ""):
        super().__init__(parent)
        self.setWindowTitle("新建自动化")
        self.setFixedSize(480, 440)
        self.setObjectName("SettingsDialog")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        layout.addWidget(QLabel("名称"))
        self._name_input = QLineEdit()
        self._name_input.setPlaceholderText("为你的自动化取一个名字")
        if preset_name:
            self._name_input.setText(preset_name)
        layout.addWidget(self._name_input)

        layout.addWidget(QLabel("指令"))
        self._prompt_input = QTextEdit()
        self._prompt_input.setPlaceholderText("描述你希望自动化完成的任务……")
        self._prompt_input.setFixedHeight(100)
        if preset_prompt:
            self._prompt_input.setPlainText(preset_prompt)
        layout.addWidget(self._prompt_input)

        layout.addWidget(QLabel("调度"))
        sched_row = QHBoxLayout()
        self._sched_type = QComboBox()
        for label, value in _SCHEDULE_TYPE_LABELS:
            self._sched_type.addItem(label, value)
        self._sched_type.currentIndexChanged.connect(self._on_sched_type_changed)
        sched_row.addWidget(self._sched_type, 1)

        self._time_input = QLineEdit("09:00")
        self._time_input.setPlaceholderText("HH:MM")
        self._time_input.setFixedWidth(72)
        sched_row.addWidget(self._time_input)

        self._weekday = QComboBox()
        for label, value in _WEEKDAY_LABELS:
            self._weekday.addItem(label, value)
        self._weekday.setCurrentIndex(6)
        self._weekday.setVisible(False)
        sched_row.addWidget(self._weekday)
        layout.addLayout(sched_row)

        self._enabled = QCheckBox("启用定时调度")
        self._enabled.setChecked(True)
        layout.addWidget(self._enabled)

        hint = QLabel("应用运行期间到点自动创建会话并执行；关闭应用后需下次启动才会继续检查。")
        hint.setObjectName("MutedLabel")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        layout.addStretch()

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel = QPushButton("取消")
        cancel.setProperty("variant", "secondary")
        cancel.setCursor(Qt.PointingHandCursor)
        cancel.clicked.connect(self.reject)
        btn_row.addWidget(cancel)
        ok = QPushButton("确定")
        ok.setProperty("variant", "primary")
        ok.setCursor(Qt.PointingHandCursor)
        ok.clicked.connect(self._accept)
        btn_row.addWidget(ok)
        layout.addLayout(btn_row)

        self.result_entry: dict = {}
        self._on_sched_type_changed()

    def _on_sched_type_changed(self) -> None:
        stype = self._sched_type.currentData()
        is_scheduled = stype in ("daily", "weekly")
        self._time_input.setEnabled(is_scheduled)
        self._weekday.setVisible(stype == "weekly")
        self._enabled.setEnabled(is_scheduled)

    def _accept(self) -> None:
        name = self._name_input.text().strip()
        prompt = self._prompt_input.toPlainText().strip()
        if not name or not prompt:
            return
        stype = self._sched_type.currentData()
        schedule = {"type": stype, "enabled": self._enabled.isChecked()}
        if stype in ("daily", "weekly"):
            schedule["time"] = self._time_input.text().strip() or "09:00"
        if stype == "weekly":
            schedule["weekday"] = self._weekday.currentData()
        self.result_entry = {
            "id": uuid.uuid4().hex[:12],
            "name": name,
            "prompt": prompt,
            "schedule": schedule,
        }
        self.accept()


class AutomationPage(QFrame):
    automation_triggered = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("PageContainer")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setObjectName("PageScroll")

        content = QWidget()
        self._content_layout = QVBoxLayout(content)
        self._content_layout.setContentsMargins(40, 32, 40, 32)
        self._content_layout.setSpacing(20)

        header = QHBoxLayout()
        title = QLabel("自动化")
        title.setObjectName("PageTitle")
        header.addWidget(title)
        header.addStretch()
        add_btn = QPushButton("+ 添加")
        add_btn.setProperty("variant", "secondary")
        add_btn.setCursor(Qt.PointingHandCursor)
        add_btn.clicked.connect(self._on_add_clicked)
        header.addWidget(add_btn)
        self._content_layout.addLayout(header)

        sub = QLabel("保存指令并设置定时；点击卡片可立即运行一次。")
        sub.setObjectName("PageSubtitle")
        self._content_layout.addWidget(sub)

        self._my_section_label = QLabel("我的自动化")
        self._my_section_label.setObjectName("SectionTitle")
        self._content_layout.addWidget(self._my_section_label)

        self._my_grid_widget = QWidget()
        self._my_grid = QGridLayout(self._my_grid_widget)
        self._my_grid.setSpacing(12)
        self._content_layout.addWidget(self._my_grid_widget)

        section = QLabel("从模板入手")
        section.setObjectName("SectionTitle")
        self._content_layout.addWidget(section)

        grid_w = QWidget()
        grid = QGridLayout(grid_w)
        grid.setSpacing(12)
        for i, (icon, name, desc) in enumerate(AUTOMATION_TEMPLATES):
            card = _AutomationCard(icon, name, desc)
            card.clicked.connect(self._on_template_clicked)
            grid.addWidget(card, i // 3, i % 3)
        self._content_layout.addWidget(grid_w)

        self._content_layout.addStretch()
        scroll.setWidget(content)
        outer.addWidget(scroll)

        self._refresh_saved()

    def _load_saved(self) -> list[dict]:
        raw = get_setting("automations", "[]")
        try:
            items = json.loads(raw)
            if isinstance(items, list):
                return items
        except Exception:
            pass
        return []

    def _save_all(self, items: list[dict]) -> None:
        set_setting("automations", json.dumps(items, ensure_ascii=False), "json")

    def _refresh_saved(self) -> None:
        while self._my_grid.count():
            item = self._my_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        items = self._load_saved()
        self._my_section_label.setVisible(bool(items))
        self._my_grid_widget.setVisible(bool(items))

        for i, entry in enumerate(items):
            card = _SavedAutomationCard(i, entry)
            card.clicked.connect(self._on_template_clicked)
            card.delete_requested.connect(self._on_delete_saved)
            self._my_grid.addWidget(card, i // 3, i % 3)

    def _on_template_clicked(self, name: str, prompt: str) -> None:
        user_text = f"[自动化] {name}\n\n{prompt}"
        conv_id = create_conversation(title=name)
        add_message(conv_id, "user", user_text)
        self.automation_triggered.emit(conv_id)

    def _on_add_clicked(self) -> None:
        dlg = _NewAutomationDialog(self.window())
        if dlg.exec() == QDialog.Accepted:
            items = self._load_saved()
            items.append(dlg.result_entry)
            self._save_all(items)
            self._refresh_saved()

    def _on_delete_saved(self, index: int) -> None:
        items = self._load_saved()
        if 0 <= index < len(items):
            items.pop(index)
            self._save_all(items)
            self._refresh_saved()

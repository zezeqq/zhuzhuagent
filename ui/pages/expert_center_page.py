from __future__ import annotations

import json
import os
import subprocess
import sys
import threading

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QDialog, QFormLayout, QFrame, QGridLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QScrollArea, QStackedWidget,
    QTextEdit, QVBoxLayout, QWidget,
)
from ui.dialogs.buddy_message import ask_confirm, show_error, show_info, show_success, show_warning

from db.database import query_all, query_one

EXPERT_CATEGORIES = [
    "全部", "技术工程", "产品设计", "内容创作", "金融投资",
    "数据智能", "法律咨询", "电商运营", "办公效率",
]

EXPERTS = [
    {"name": "高级开发工程师", "provider": "专八哥", "desc": "10年以上全栈经验，精通多种语言和框架，熟悉前后端、架构设计与代码评审。", "tags": ["高级开发", "架构设计", "代码质量"], "category": "技术工程"},
    {"name": "内容创作专家", "provider": "文博客", "desc": "擅长撰写引人入胜的多平台内容，让品牌故事触达目标受众。", "tags": ["内容创作", "品牌故事"], "category": "内容创作"},
    {"name": "数据分析师", "provider": "数据派", "desc": "精通 Python 数据处理、可视化和统计分析，善于从数据中提炼业务洞察。", "tags": ["数据分析", "可视化"], "category": "数据智能"},
    {"name": "投资分析师", "provider": "金融通", "desc": "深入研究宏观经济与行业趋势，提供专业的投资策略和风险评估。", "tags": ["投资分析", "风险评估"], "category": "金融投资"},
    {"name": "法律顾问", "provider": "法务通", "desc": "精通合同法、劳动法和知识产权，为企业提供合规建议和风险防范。", "tags": ["合同审查", "合规咨询"], "category": "法律咨询"},
    {"name": "公路机电专家", "provider": "DNA", "desc": "精通交通监控、收费、通信、供配电、照明和隧道机电系统。", "tags": ["公路机电", "工程标准"], "category": "技术工程"},
    {"name": "投标专家", "provider": "DNA", "desc": "擅长解读招标文件技术要求，组织技术方案和响应内容。", "tags": ["投标技术", "方案编写"], "category": "办公效率"},
    {"name": "测试专家", "provider": "DNA", "desc": "熟悉公路机电工程各系统的测试方法、仪器使用和记录规范。", "tags": ["现场测试", "标准规程"], "category": "技术工程"},
    {"name": "质量管理专家", "provider": "DNA", "desc": "精通质量检验评定标准，熟悉工序、分部、单位工程的检验流程。", "tags": ["质量管理", "检验评定"], "category": "技术工程"},
    {"name": "文档编写专家", "provider": "DNA", "desc": "擅长项目方案、施工组织设计、工程总结和验收资料的撰写。", "tags": ["技术文档", "方案撰写"], "category": "办公效率"},
    {"name": "电商运营专家", "provider": "运营派", "desc": "深耕电商领域，精通流量获取、转化优化和用户运营策略。", "tags": ["电商运营", "流量增长"], "category": "电商运营"},
    {"name": "产品经理", "provider": "产品派", "desc": "擅长需求分析、产品规划和用户体验设计，推动产品从0到1。", "tags": ["需求分析", "产品规划"], "category": "产品设计"},
]

HERO_SCENES = [
    ("内容创作", ["内容创作专家团", "小红书运营专家"]),
    ("投资分析", ["交易分析团队", "股票研究专家"]),
    ("法律咨询", ["法律合规审查员", "资深合同法务专家"]),
    ("小微企业", ["销售教练", "微信公众号运营专家"]),
    ("电商运营", ["中国电商运营专家团"]),
]

from core.skill_catalog import (
    SKILL_CATEGORIES,
    all_catalog_skills,
    catalog_skills_for_category,
    install_success_message,
    is_planned_skill,
    is_skill_installed,
    skill_by_name,
    skill_type_label,
)
from core.remote_catalog import (
    fetch_remote_catalog,
    get_catalog_url,
    list_hot_remote_experts,
    list_hot_remote_skills,
    load_cached_catalog,
    remote_experts_merged_with_local,
)
from agent_runtime.skill_installer import install_from_catalog

CONNECTORS = [
    {"name": "通达信", "desc": "配置本地程序路径后可一键启动", "icon": "📈"},
    {"name": "QQ 邮箱", "desc": "配置本地程序路径后可一键启动", "icon": "✉"},
    {"name": "腾讯文档", "desc": "配置本地程序路径后可一键启动", "icon": "📄"},
    {"name": "腾讯会议", "desc": "配置本地程序路径后可一键启动", "icon": "📹"},
    {"name": "企业微信", "desc": "配置本地程序路径后可一键启动", "icon": "💬"},
    {"name": "飞书", "desc": "配置本地程序路径后可一键启动", "icon": "🐦"},
    {"name": "钉钉", "desc": "配置本地程序路径后可一键启动", "icon": "📌"},
    {"name": "TAPD", "desc": "配置本地程序路径后可一键启动", "icon": "📋"},
]


def _is_process_running(name: str) -> bool:
    """Check if a process with the given name is running (Windows)."""
    try:
        result = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {name}", "/NH"],
            capture_output=True, text=True, timeout=5,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return name.lower() in result.stdout.lower()
    except Exception:
        return False


def _get_installed_skill_names() -> set[str]:
    rows = query_all("SELECT package_name, display_name FROM installed_skill_packages WHERE enabled=1")
    names: set[str] = set()
    for r in rows:
        names.add(r["package_name"].lower().replace(" ", "_"))
        if r.get("display_name"):
            names.add(r["display_name"])
    return names


# ── Expert Card ──────────────────────────────────────────────────────────

class _ExpertCard(QFrame):
    summon = Signal(str, str)

    def __init__(self, expert: dict, parent=None):
        super().__init__(parent)
        self.setObjectName("ExpertCard")
        self._expert = expert
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(6)

        top = QHBoxLayout()
        avatar = QLabel("👤")
        avatar.setObjectName("ExpertIcon")
        top.addWidget(avatar)
        col = QVBoxLayout()
        col.setSpacing(1)
        name = QLabel(expert["name"])
        name.setObjectName("ExpertName")
        col.addWidget(name)
        prov = QLabel(expert.get("provider", ""))
        prov.setObjectName("MutedLabel")
        col.addWidget(prov)
        top.addLayout(col, 1)
        layout.addLayout(top)

        desc = QLabel(expert["desc"])
        desc.setObjectName("ExpertDesc")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        tag_row = QHBoxLayout()
        tag_row.setSpacing(4)
        for tag in expert.get("tags", [])[:3]:
            t = QPushButton(tag)
            t.setObjectName("TagButton")
            t.setFixedHeight(22)
            t.setCursor(Qt.PointingHandCursor)
            tag_row.addWidget(t)
        tag_row.addStretch()
        layout.addLayout(tag_row)

        btn = QPushButton("召唤专家")
        btn.setObjectName("SummonButton")
        btn.setCursor(Qt.PointingHandCursor)
        prompt = expert.get("prompt") or f"你是{expert['name']}。{expert['desc']}"
        btn.clicked.connect(lambda: self.summon.emit(expert["name"], prompt))
        layout.addWidget(btn)


# ── Skill Card ───────────────────────────────────────────────────────────

class _SkillCard(QFrame):
    install_requested = Signal(str)

    def __init__(self, skill: dict, installed: bool = False, *, hot: bool = False, parent=None):
        super().__init__(parent)
        self.setObjectName("HotSkillCard" if hot else "ActionCard")
        self._skill = skill
        self._planned = is_planned_skill(skill)
        if hot:
            self.setFixedHeight(88)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(10)

        icon = QLabel(skill.get("icon", "⚡"))
        icon.setFixedSize(36, 36)
        icon.setAlignment(Qt.AlignCenter)
        icon.setStyleSheet(
            "font-size:18px; background:#1e293b; border-radius:8px;"
        )
        layout.addWidget(icon)

        col = QVBoxLayout()
        col.setSpacing(2)
        title = skill.get("display") or skill["name"]
        n = QLabel(title)
        n.setObjectName("CardTitle")
        n.setStyleSheet("font-size:13px;")
        col.addWidget(n)
        badge_text = skill_type_label(skill)
        if skill.get("hot") or hot:
            badge_text = "🔥 热门 · " + badge_text
        if skill.get("remote"):
            badge_text += " · 远程"
        if skill.get("hot_rank"):
            badge_text += f" · #{skill['hot_rank']}"
        badge = QLabel(badge_text)
        badge.setStyleSheet("font-size:10px; color:#94a3b8;")
        col.addWidget(badge)
        d = QLabel(skill.get("desc", ""))
        d.setObjectName("MutedLabel")
        d.setWordWrap(True)
        col.addWidget(d)
        layout.addLayout(col, 1)

        if self._planned:
            self._btn = QPushButton("规划")
            self._btn.setEnabled(False)
            self._btn.setFixedHeight(28)
        elif installed:
            self._btn = QPushButton("✓")
            self._btn.setEnabled(False)
            self._btn.setStyleSheet("color:#22c55e; font-weight:bold;")
            self._btn.setFixedSize(28, 28)
        else:
            self._btn = QPushButton("+")
            self._btn.setObjectName("InputIconButton")
            self._btn.setFixedSize(28, 28)
            self._btn.setCursor(Qt.PointingHandCursor)
            self._btn.clicked.connect(self._on_click)
        layout.addWidget(self._btn)

    def _on_click(self):
        self.install_requested.emit(self._skill["name"])

    def mark_installed(self):
        self._btn.setText("✓")
        self._btn.setEnabled(False)
        self._btn.setStyleSheet("color:#22c55e; font-weight:bold;")


# ── Connector Card ───────────────────────────────────────────────────────

class _ConnectorCard(QFrame):
    launch_requested = Signal(str)

    def __init__(self, conn: dict, parent=None):
        super().__init__(parent)
        self.setObjectName("ConnectorCard")
        self._conn = conn
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(12)

        icon = QLabel(conn.get("icon", "🔗"))
        icon.setFixedSize(40, 40)
        icon.setAlignment(Qt.AlignCenter)
        icon.setStyleSheet("font-size:22px; background:#1e293b; border-radius:10px;")
        layout.addWidget(icon)

        col = QVBoxLayout()
        col.setSpacing(2)
        n = QLabel(conn["name"])
        n.setObjectName("CardTitle")
        col.addWidget(n)
        d = QLabel(conn["desc"])
        d.setObjectName("MutedLabel")
        d.setWordWrap(True)
        col.addWidget(d)
        layout.addLayout(col, 1)

        self._status_dot = QLabel("●")
        self._status_dot.setFixedSize(16, 16)
        self._status_dot.setAlignment(Qt.AlignCenter)
        self._set_status(False)
        layout.addWidget(self._status_dot)

        self._launch_btn = QPushButton("启动")
        self._launch_btn.setObjectName("SummonButton")
        self._launch_btn.setFixedSize(56, 28)
        self._launch_btn.setCursor(Qt.PointingHandCursor)
        self._launch_btn.clicked.connect(lambda: self.launch_requested.emit(conn["name"]))
        layout.addWidget(self._launch_btn)

    def _set_status(self, connected: bool):
        color = "#22c55e" if connected else "#ef4444"
        self._status_dot.setStyleSheet(f"color:{color}; font-size:10px; background:transparent;")
        self._status_dot.setToolTip("进程已运行" if connected else "未运行")

    def refresh_status(self, running: bool):
        self._set_status(running)
        self._launch_btn.setText("已启动" if running else "启动")


# ── Custom Expert Dialog ─────────────────────────────────────────────────

class _CustomExpertDialog(QDialog):
    def __init__(self, parent=None, experts: list[dict] | None = None):
        super().__init__(parent)
        self.setWindowTitle("我的专家")
        self.setMinimumSize(520, 420)
        self._experts = experts or []
        self._changed = False

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        header = QHBoxLayout()
        header.addWidget(QLabel("自定义专家列表"))
        header.addStretch()
        add_btn = QPushButton("+ 新增专家")
        add_btn.setCursor(Qt.PointingHandCursor)
        add_btn.clicked.connect(self._add_expert)
        header.addWidget(add_btn)
        layout.addLayout(header)

        self._list_widget = QVBoxLayout()
        self._list_container = QWidget()
        self._list_container.setLayout(self._list_widget)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self._list_container)
        layout.addWidget(scroll, 1)

        self._refresh_list()

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

    def _refresh_list(self):
        while self._list_widget.count():
            item = self._list_widget.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not self._experts:
            empty = QLabel('暂无自定义专家，点击 "+ 新增专家" 创建。')
            empty.setStyleSheet("color:#888; padding:20px;")
            empty.setAlignment(Qt.AlignCenter)
            self._list_widget.addWidget(empty)
            return

        for i, expert in enumerate(self._experts):
            row = QFrame()
            row.setStyleSheet("QFrame { border:1px solid #334155; border-radius:6px; padding:8px; margin:2px; }")
            rl = QHBoxLayout(row)
            rl.setContentsMargins(8, 6, 8, 6)

            info = QVBoxLayout()
            name_lbl = QLabel(f"👤 {expert['name']}")
            name_lbl.setStyleSheet("font-weight:bold; font-size:13px;")
            info.addWidget(name_lbl)
            desc_lbl = QLabel(expert.get("desc", ""))
            desc_lbl.setWordWrap(True)
            desc_lbl.setStyleSheet("color:#94a3b8; font-size:11px;")
            info.addWidget(desc_lbl)
            rl.addLayout(info, 1)

            del_btn = QPushButton("删除")
            del_btn.setFixedSize(50, 26)
            del_btn.setCursor(Qt.PointingHandCursor)
            del_btn.clicked.connect(lambda _, idx=i: self._delete_expert(idx))
            rl.addWidget(del_btn)

            self._list_widget.addWidget(row)

        self._list_widget.addStretch()

    def _add_expert(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("新增自定义专家")
        dlg.setMinimumWidth(400)
        form = QFormLayout(dlg)

        name_edit = QLineEdit()
        name_edit.setPlaceholderText("如：Python全栈专家")
        form.addRow("专家名称：", name_edit)

        desc_edit = QLineEdit()
        desc_edit.setPlaceholderText("简要描述专家能力")
        form.addRow("描述：", desc_edit)

        prompt_edit = QTextEdit()
        prompt_edit.setPlaceholderText("你是一位……（详细的系统提示词）")
        prompt_edit.setFixedHeight(100)
        form.addRow("提示词：", prompt_edit)

        category_edit = QLineEdit()
        category_edit.setPlaceholderText("如：技术工程、办公效率")
        form.addRow("分类：", category_edit)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel = QPushButton("取消")
        cancel.clicked.connect(dlg.reject)
        btn_row.addWidget(cancel)
        ok = QPushButton("保存")
        ok.clicked.connect(dlg.accept)
        btn_row.addWidget(ok)
        form.addRow(btn_row)

        if dlg.exec() == QDialog.Accepted:
            name = name_edit.text().strip()
            if not name:
                QMessageBox.warning(self, "提示", "专家名称不能为空。")
                return
            expert = {
                "name": name,
                "desc": desc_edit.text().strip(),
                "prompt": prompt_edit.toPlainText().strip(),
                "category": category_edit.text().strip() or "自定义",
                "provider": "自定义",
                "tags": ["自定义"],
            }
            self._experts.append(expert)
            self._changed = True
            self._save()
            self._refresh_list()

    def _delete_expert(self, idx: int):
        if 0 <= idx < len(self._experts):
            name = self._experts[idx]["name"]
            reply = QMessageBox.question(
                self, "确认删除", f"确定删除专家「{name}」吗？",
                QMessageBox.Yes | QMessageBox.No,
            )
            if reply == QMessageBox.Yes:
                self._experts.pop(idx)
                self._changed = True
                self._save()
                self._refresh_list()

    def _save(self):
        from core.settings_store import set_setting
        set_setting("custom_experts", json.dumps(self._experts, ensure_ascii=False), "json")

    @property
    def experts(self) -> list[dict]:
        return self._experts

    @property
    def changed(self) -> bool:
        return self._changed


# ── URL Install Dialog ───────────────────────────────────────────────────

class _UrlInstallDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("从 URL 安装技能")
        self.setMinimumWidth(420)
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("请输入 Skill 下载地址或 GitHub 仓库地址："))
        self._url_edit = QLineEdit()
        self._url_edit.setPlaceholderText("https://github.com/user/skill-repo")
        layout.addWidget(self._url_edit)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        btn_row.addWidget(cancel)
        ok = QPushButton("安装")
        ok.clicked.connect(self.accept)
        btn_row.addWidget(ok)
        layout.addLayout(btn_row)

    @property
    def url(self) -> str:
        return self._url_edit.text().strip()


# ── Connector Config Dialog ──────────────────────────────────────────────

class _ConnectorConfigDialog(QDialog):
    def __init__(self, connector_name: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"配置启动项 - {connector_name}")
        self.setMinimumWidth(420)

        existing = query_one(
            "SELECT * FROM software_tools WHERE software_name=?",
            (connector_name,),
        )

        layout = QFormLayout(self)

        self._path_edit = QLineEdit()
        self._path_edit.setPlaceholderText("可执行文件路径，如 C:\\Program Files\\...\\app.exe")
        if existing and existing.get("executable_path"):
            self._path_edit.setText(existing["executable_path"])
        layout.addRow("程序路径：", self._path_edit)

        self._args_edit = QLineEdit()
        self._args_edit.setPlaceholderText("启动参数（可选）")
        if existing and existing.get("launch_args"):
            self._args_edit.setText(existing["launch_args"])
        layout.addRow("启动参数：", self._args_edit)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        btn_row.addWidget(cancel)
        ok = QPushButton("保存并启动")
        ok.clicked.connect(self.accept)
        btn_row.addWidget(ok)
        layout.addRow(btn_row)

    @property
    def executable_path(self) -> str:
        return self._path_edit.text().strip()

    @property
    def launch_args(self) -> str:
        return self._args_edit.text().strip()


# ── Filter Bar ───────────────────────────────────────────────────────────

def _filter_bar(categories: list[str], callback) -> QFrame:
    bar = QFrame()
    bar._buttons: list[QPushButton] = []
    layout = QHBoxLayout(bar)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(4)
    for cat in categories:
        btn = QPushButton(cat)
        btn.setObjectName("FilterButton")
        btn.setCheckable(True)
        btn.setChecked(cat == categories[0])
        btn.setCursor(Qt.PointingHandCursor)
        btn.clicked.connect(lambda _, c=cat, b=btn, bar_ref=bar: _on_filter_click(bar_ref, c, callback))
        bar._buttons.append(btn)
        layout.addWidget(btn)
    layout.addStretch()
    return bar


def _on_filter_click(bar: QFrame, category: str, callback):
    for btn in bar._buttons:
        btn.setChecked(btn.text() == category)
    callback(category)


def _skill_matches_query(skill: dict, q: str) -> bool:
    if not q:
        return True
    tags = " ".join(str(t) for t in (skill.get("tags") or []))
    blob = " ".join([
        skill.get("name", ""),
        skill.get("display", ""),
        skill.get("desc", ""),
        skill.get("category", ""),
        tags,
    ]).lower()
    return q in blob


def _clear_grid_layout(layout: QGridLayout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget:
            widget.setParent(None)
            widget.deleteLater()
    QApplication.processEvents()


# ── Main Page ────────────────────────────────────────────────────────────

class ExpertCenterPage(QFrame):
    expert_selected = Signal(str, str)
    skill_installed = Signal(str, str)
    _remote_catalog_done = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("PageContainer")
        self._search_text = ""
        self._expert_filter_cat = "全部"
        self._skill_filter_cat = "全部"
        self._custom_experts: list[dict] = []
        self._skill_cards: dict[str, _SkillCard] = {}
        self._connector_cards: list[_ConnectorCard] = []
        self._installed_skill_names: set[str] = set()
        self._catalog_refresh_busy = False
        self._hot_skill_names: set[str] = set()
        self._remote_catalog_done.connect(self._finish_remote_refresh)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        top_bar = QFrame()
        top_bar.setObjectName("PageTabBar")
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(24, 8, 24, 8)
        top_layout.setSpacing(16)

        self._tab_buttons: list[QPushButton] = []
        for i, (icon, label) in enumerate([("👤", "专家"), ("⚡", "技能"), ("🚀", "快捷启动")]):
            btn = QPushButton(f"{icon} {label}")
            btn.setObjectName("PageTabButton")
            btn.setCheckable(True)
            btn.setChecked(i == 0)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _, idx=i: self._switch_tab(idx))
            self._tab_buttons.append(btn)
            top_layout.addWidget(btn)

        top_layout.addStretch()

        self._search = QLineEdit()
        self._search.setPlaceholderText("搜索名称、描述或标签")
        self._search.setFixedWidth(200)
        self._search.setFixedHeight(30)
        self._search.textChanged.connect(self._on_search_changed)
        top_layout.addWidget(self._search)

        self._action_btn = QPushButton("我的专家")
        self._action_btn.setProperty("variant", "ghost")
        self._action_btn.setCursor(Qt.PointingHandCursor)
        self._action_btn.clicked.connect(self._on_action_button)
        top_layout.addWidget(self._action_btn)

        layout.addWidget(top_bar)

        self._stack = QStackedWidget()
        self._stack.addWidget(self._build_expert_tab())
        self._stack.addWidget(self._build_skill_tab())
        self._stack.addWidget(self._build_connector_tab())
        layout.addWidget(self._stack, 1)

        self._load_custom_experts()
        self._load_installed_skills()
        QTimer.singleShot(600, self._startup_catalog_refresh)

    def _startup_catalog_refresh(self):
        """启动后后台拉远程目录并刷新当前 Tab。"""
        self._run_remote_catalog_fetch(force=False, show_dialog=False)

    def _run_remote_catalog_fetch(self, *, force: bool, show_dialog: bool) -> None:
        if self._catalog_refresh_busy:
            return
        self._catalog_refresh_busy = True
        if show_dialog:
            self._skill_refresh_btn.setEnabled(False)
            self._skill_refresh_btn.setText("刷新中…")

        def work():
            err = None
            try:
                fetch_remote_catalog(force=force)
            except Exception as exc:
                err = exc
            self._remote_catalog_done.emit((err, show_dialog))

        threading.Thread(
            target=work, daemon=True, name="RemoteCatalogFetch",
        ).start()

        if show_dialog:
            QTimer.singleShot(15000, self._catalog_refresh_watchdog)

    def _catalog_refresh_watchdog(self):
        """防止回调丢失时按钮永久卡在「刷新中」。"""
        if not self._catalog_refresh_busy:
            return
        self._catalog_refresh_busy = False
        self._skill_refresh_btn.setEnabled(True)
        self._skill_refresh_btn.setText("从网络刷新")
        self._update_catalog_status_label()
        self._catalog_status.setText(
            self._catalog_status.text() + " · 刷新超时，请重试"
        )

    def _apply_catalog_to_ui(self):
        self._update_catalog_status_label()
        idx = self._stack.currentIndex()
        if idx == 0:
            self._filter_experts(self._expert_filter_cat)
        elif idx == 1:
            self._filter_skills(self._skill_filter_cat)

    # ── Tab switching ────────────────────────────────────────────────────

    def _switch_tab(self, idx: int):
        self._stack.setCurrentIndex(idx)
        for i, btn in enumerate(self._tab_buttons):
            btn.setChecked(i == idx)
        labels = ["我的专家", "添加技能", "添加启动项"]
        self._action_btn.setText(labels[idx])

    def switch_to_tab(self, tab_name: str):
        mapping = {"experts": 0, "skills": 1, "connectors": 2}
        idx = mapping.get(tab_name, 0)
        self._switch_tab(idx)

    # ── Search ───────────────────────────────────────────────────────────

    def _on_search_changed(self, text: str):
        self._search_text = text.strip().lower()
        current = self._stack.currentIndex()
        if current == 0:
            self._filter_experts(self._expert_filter_cat)
        elif current == 1:
            self._filter_skills(self._skill_filter_cat)
        elif current == 2:
            self._rebuild_connector_grid()

    # ── Action button (我的专家 / 添加技能 / 自定义连接器) ────────────────

    def _on_action_button(self):
        current = self._stack.currentIndex()
        if current == 0:
            self._show_my_experts()
        elif current == 1:
            self._install_from_url()
        elif current == 2:
            self._add_custom_connector()

    # ── Expert Tab ───────────────────────────────────────────────────────

    def _build_expert_tab(self) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setObjectName("PageScroll")

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        scene_title = QLabel("精选场景")
        scene_title.setObjectName("SectionTitle")
        layout.addWidget(scene_title)

        scene_row = QHBoxLayout()
        scene_row.setSpacing(12)
        for title, subs in HERO_SCENES:
            card = QFrame()
            card.setObjectName("HeroCard")
            card.setFixedHeight(120)
            card.setMinimumWidth(160)
            c_layout = QVBoxLayout(card)
            c_layout.setContentsMargins(14, 12, 14, 12)
            t = QLabel(title)
            t.setStyleSheet("font-size:16px; font-weight:700; color:white; background:transparent;")
            c_layout.addWidget(t)
            c_layout.addStretch()
            for s in subs[:2]:
                sl = QLabel(f"👤 {s}")
                sl.setStyleSheet("font-size:11px; color:rgba(255,255,255,0.8); background:transparent;")
                c_layout.addWidget(sl)
            scene_row.addWidget(card)
        layout.addLayout(scene_row)

        layout.addWidget(QLabel(""))
        section = QLabel("专家  专家团")
        section.setObjectName("SectionTitle")
        layout.addWidget(section)

        self._expert_grid_widget = QWidget()
        self._expert_grid = QGridLayout(self._expert_grid_widget)
        self._expert_grid.setSpacing(12)
        self._expert_filter_bar = _filter_bar(EXPERT_CATEGORIES, self._filter_experts)
        layout.addWidget(self._expert_filter_bar)
        layout.addWidget(self._expert_grid_widget)
        self._filter_experts("全部")

        layout.addStretch()
        scroll.setWidget(content)
        return scroll

    def _filter_experts(self, category: str):
        self._expert_filter_cat = category
        while self._expert_grid.count():
            item = self._expert_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        all_experts = remote_experts_merged_with_local(list(EXPERTS) + self._custom_experts)

        if category != "全部":
            all_experts = [e for e in all_experts if e.get("category") == category]

        if self._search_text:
            q = self._search_text
            all_experts = [
                e for e in all_experts
                if q in e["name"].lower()
                or q in e.get("desc", "").lower()
                or any(q in tag.lower() for tag in e.get("tags", []))
                or q in e.get("provider", "").lower()
            ]

        for i, e in enumerate(all_experts):
            card = _ExpertCard(e)
            card.summon.connect(self._on_expert_summon)
            self._expert_grid.addWidget(card, i // 4, i % 4)

    def _on_expert_summon(self, name: str, prompt: str):
        for ce in self._custom_experts:
            if ce["name"] == name and ce.get("prompt"):
                prompt = ce["prompt"]
                break
        self.expert_selected.emit(name, prompt)

    # ── Skill Tab ────────────────────────────────────────────────────────

    def _build_skill_tab(self) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setObjectName("PageScroll")

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        sub_tabs = QHBoxLayout()
        sub_tabs.setSpacing(12)
        for text in ["技能市场", "已安装"]:
            btn = QPushButton(text)
            btn.setObjectName("FilterButton")
            btn.setCheckable(True)
            btn.setChecked(text == "技能市场")
            btn.setCursor(Qt.PointingHandCursor)
            sub_tabs.addWidget(btn)
        sub_tabs.addStretch()
        self._skill_refresh_btn = QPushButton("从网络刷新")
        self._skill_refresh_btn.setObjectName("FilterButton")
        self._skill_refresh_btn.setCursor(Qt.PointingHandCursor)
        self._skill_refresh_btn.clicked.connect(self._refresh_remote_catalog)
        sub_tabs.addWidget(self._skill_refresh_btn)
        layout.addLayout(sub_tabs)

        self._catalog_status = QLabel("")
        self._catalog_status.setObjectName("MutedLabel")
        layout.addWidget(self._catalog_status)
        self._update_catalog_status_label()

        self._hot_section_title = QLabel("🔥 网络热门")
        self._hot_section_title.setObjectName("SectionTitle")
        layout.addWidget(self._hot_section_title)

        self._hot_status = QLabel("")
        self._hot_status.setObjectName("MutedLabel")
        layout.addWidget(self._hot_status)

        self._hot_skill_grid_widget = QWidget()
        self._hot_skill_grid = QGridLayout(self._hot_skill_grid_widget)
        self._hot_skill_grid.setSpacing(10)
        self._hot_skill_grid.setContentsMargins(0, 0, 0, 0)
        self._hot_scroll = QScrollArea()
        self._hot_scroll.setWidgetResizable(True)
        self._hot_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._hot_scroll.setMaximumHeight(300)
        self._hot_scroll.setWidget(self._hot_skill_grid_widget)
        self._hot_scroll.setObjectName("PageScroll")
        layout.addWidget(self._hot_scroll)

        rec_title = QLabel("全部技能")
        rec_title.setObjectName("SectionTitle")
        layout.addWidget(rec_title)

        self._skill_filter_bar = _filter_bar(SKILL_CATEGORIES, self._filter_skills)
        layout.addWidget(self._skill_filter_bar)

        self._skill_grid_widget = QWidget()
        self._skill_grid = QGridLayout(self._skill_grid_widget)
        self._skill_grid.setSpacing(10)
        layout.addWidget(self._skill_grid_widget)

        self._refresh_hot_skills_ui()
        self._populate_skill_grid(all_catalog_skills())

        layout.addStretch()
        scroll.setWidget(content)
        return scroll

    def _update_catalog_status_label(self):
        url = get_catalog_url()
        cached = load_cached_catalog() or {}
        n_skills = len(cached.get("skills") or [])
        n_hot = len(cached.get("hot_skills") or [])
        n_experts = len(cached.get("experts") or [])
        updated = cached.get("updated_at") or ""
        ver = cached.get("version") or ""
        err = cached.get("fetch_error") or ""

        if cached.get("source_url") == url and (n_hot or n_skills or n_experts):
            extra = f" · 热门 {n_hot} · 覆盖 {n_skills} · 专家 {n_experts}"
            if ver:
                extra += f" · v{ver}"
            if updated:
                extra += f" · {updated}"
            self._catalog_status.setText(f"远程目录：{url}{extra}")
        elif err:
            self._catalog_status.setText(
                f"远程目录：{url} · 拉取失败（{err}）· 可点「从网络刷新」重试"
            )
        else:
            self._catalog_status.setText(
                f"远程目录：{url} · 正在拉取，请稍候或点「从网络刷新」"
            )

    def _rebuild_hot_grid_container(self) -> None:
        new_w = QWidget()
        new_layout = QGridLayout(new_w)
        new_layout.setSpacing(10)
        new_layout.setContentsMargins(0, 0, 0, 0)
        self._hot_scroll.takeWidget()
        if self._hot_skill_grid_widget:
            self._hot_skill_grid_widget.deleteLater()
        self._hot_skill_grid_widget = new_w
        self._hot_skill_grid = new_layout
        self._hot_scroll.setWidget(new_w)

    def _refresh_hot_skills_ui(self):
        self._rebuild_hot_grid_container()

        show_hot = self._skill_filter_cat == "全部"
        self._hot_section_title.setVisible(show_hot)
        self._hot_status.setVisible(show_hot)
        self._hot_scroll.setVisible(show_hot)
        if not show_hot:
            return

        hot_skills = list_hot_remote_skills()
        if self._search_text:
            hot_skills = [s for s in hot_skills if _skill_matches_query(s, self._search_text)]

        if not hot_skills:
            self._hot_status.setText("暂无远程热门（点「从网络刷新」或检查网络）")
            return

        self._hot_status.setText(
            f"共 {len(hot_skills)} 个热门 Skill · 支持搜索名称/描述/标签 · 点 + 安装后下条 Craft 对话生效"
        )
        hot_names = {s.get("name", "").lower() for s in hot_skills}
        self._hot_skill_names = hot_names

        cols = 2
        for i, s in enumerate(hot_skills):
            installed = is_skill_installed(s, self._installed_skill_names)
            card = _SkillCard(s, installed=installed, hot=True)
            card.install_requested.connect(self._on_skill_install)
            self._skill_cards[s["name"]] = card
            self._hot_skill_grid.addWidget(card, i // cols, i % cols)

    def _refresh_remote_catalog(self):
        self._run_remote_catalog_fetch(force=True, show_dialog=True)

    def _finish_remote_refresh(self, payload):
        if isinstance(payload, tuple):
            err, show_dialog = payload
        else:
            err, show_dialog = payload, True

        self._catalog_refresh_busy = False
        self._skill_refresh_btn.setEnabled(True)
        self._skill_refresh_btn.setText("从网络刷新")
        self._update_catalog_status_label()
        self._filter_experts(self._expert_filter_cat)
        self._filter_skills(self._skill_filter_cat)

        if not show_dialog:
            return
        if err:
            show_error(self, "刷新失败", "无法拉取远程目录。", detail=str(err))
        else:
            cached = load_cached_catalog() or {}
            n_hot = len(cached.get("hot_skills") or [])
            n_skills = len(cached.get("skills") or [])
            n_experts = len(cached.get("experts") or [])
            show_success(
                self,
                "目录已更新",
                f"已从网络同步最新 Skill 目录。",
                detail=(
                    f"🔥 热门 Skill：{n_hot} 个（见上方橙色区域）\n"
                    f"覆盖更新：{n_skills} 个\n"
                    f"远程专家：{n_experts} 个\n\n"
                    f"在搜索框输入关键词（如「投标」「SQL」「小红书」）可快速筛选。"
                ),
            )

    def _populate_skill_grid(self, skills: list[dict]):
        _clear_grid_layout(self._skill_grid)
        hot_names = getattr(self, "_hot_skill_names", set())
        if hot_names and self._skill_filter_cat == "全部" and not self._search_text:
            skills = [s for s in skills if s.get("name", "").lower() not in hot_names]

        for i, s in enumerate(skills):
            pkg_name = s["name"].strip().lower().replace(" ", "_")
            installed = is_skill_installed(s, self._installed_skill_names)
            card = _SkillCard(s, installed=installed)
            card.install_requested.connect(self._on_skill_install)
            self._skill_cards[s["name"]] = card
            self._skill_grid.addWidget(card, i // 4, i % 4)

    def _filter_skills(self, category: str):
        self._skill_filter_cat = category
        filtered = catalog_skills_for_category(category)

        if self._search_text:
            filtered = [s for s in filtered if _skill_matches_query(s, self._search_text)]

        self._refresh_hot_skills_ui()
        self._populate_skill_grid(filtered)

    def _on_skill_install(self, skill_name: str):
        from agent_runtime.tool_executor import load_installed_handlers

        skill_data = skill_by_name(skill_name)
        if not skill_data:
            show_warning(self, "未找到", f"未找到技能「{skill_name}」的信息。")
            return
        if is_planned_skill(skill_data):
            show_info(
                self, "规划中",
                f"「{skill_data.get('display', skill_name)}」尚在规划中，暂不可安装。",
            )
            return

        try:
            result = install_from_catalog(skill_data)
            load_installed_handlers()
            pkg = result.get("package_name", "") or skill_name
            display = skill_data.get("display") or skill_name
            self._installed_skill_names.add(skill_name)
            if pkg:
                self._installed_skill_names.add(pkg.lower())
            self._installed_skill_names.add(display.lower())

            card = self._skill_cards.get(skill_name)
            if card:
                card.mark_installed()
            self._refresh_hot_skills_ui()
            self._filter_skills(self._skill_filter_cat)

            self.skill_installed.emit(pkg, display)
            show_success(
                self,
                "已装配到 Agent",
                f"技能「{display}」安装成功，已写入本地 Skill 目录。",
                detail=(
                    "✓ 下一条 Craft / Plan 对话将自动注入该 Skill 说明\n"
                    "✓ 聊天底栏 Skill 下拉已切换为仅此 Skill\n"
                    "✓ 含工具的 Skill 会注册专用函数\n\n"
                    f"路径：{result.get('install_path', '')}"
                ),
            )
        except Exception as e:
            show_error(self, "安装失败", str(e))

    def _install_from_url(self):
        dlg = _UrlInstallDialog(self)
        if dlg.exec() == QDialog.Accepted and dlg.url:
            from agent_runtime.skill_installer import install_skill_from_url
            try:
                result = install_skill_from_url(dlg.url)
                pkg = result.get("package_name", "")
                display = result.get("manifest", {}).get("display_name", pkg)
                self._installed_skill_names.add(pkg)
                if display:
                    self._installed_skill_names.add(display)
                QMessageBox.information(
                    self, "安装成功",
                    f"技能「{display}」已安装。\n路径：{result.get('install_path', '')}",
                )
            except Exception as e:
                QMessageBox.critical(self, "安装失败", str(e))

    def _load_installed_skills(self):
        try:
            self._installed_skill_names = _get_installed_skill_names()
        except Exception:
            self._installed_skill_names = set()

    # ── Connector Tab ────────────────────────────────────────────────────

    def _build_connector_tab(self) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setObjectName("PageScroll")

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        self._connector_grid_widget = QWidget()
        self._connector_grid = QGridLayout(self._connector_grid_widget)
        self._connector_grid.setSpacing(12)
        layout.addWidget(self._connector_grid_widget)

        self._rebuild_connector_grid()

        layout.addStretch()
        scroll.setWidget(content)
        return scroll

    def _rebuild_connector_grid(self):
        while self._connector_grid.count():
            item = self._connector_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._connector_cards.clear()

        filtered = list(CONNECTORS)
        if self._search_text:
            q = self._search_text
            filtered = [
                c for c in filtered
                if q in c["name"].lower() or q in c.get("desc", "").lower()
            ]

        for i, c in enumerate(filtered):
            card = _ConnectorCard(c)
            card.launch_requested.connect(self._on_connector_launch)
            self._connector_cards.append(card)
            self._connector_grid.addWidget(card, i // 2, i % 2)

        self._refresh_connector_statuses()

    def _on_connector_launch(self, name: str):
        tool = query_one(
            "SELECT * FROM software_tools WHERE software_name=?", (name,),
        )

        if not tool or not tool.get("executable_path"):
            dlg = _ConnectorConfigDialog(name, self)
            if dlg.exec() != QDialog.Accepted:
                return
            exe_path = dlg.executable_path
            if not exe_path:
                QMessageBox.warning(self, "提示", "请输入程序路径。")
                return
            args = dlg.launch_args
            self._save_connector_config(name, exe_path, args)
        else:
            exe_path = tool["executable_path"]
            args = tool.get("launch_args", "")

        self._launch_connector(name, exe_path, args)

    def _save_connector_config(self, name: str, exe_path: str, args: str):
        from db.database import insert, execute as db_execute

        existing = query_one(
            "SELECT id FROM software_tools WHERE software_name=?", (name,),
        )
        if existing:
            db_execute(
                "UPDATE software_tools SET executable_path=?, launch_args=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (exe_path, args, existing["id"]),
            )
        else:
            insert("software_tools", {
                "software_name": name,
                "software_type": "connector",
                "executable_path": exe_path,
                "launch_args": args,
                "enabled": 1,
            })

    def _launch_connector(self, name: str, exe_path: str, args: str):
        if not os.path.isfile(exe_path):
            reply = QMessageBox.question(
                self, "文件不存在",
                f"程序路径不存在：\n{exe_path}\n\n是否重新配置？",
                QMessageBox.Yes | QMessageBox.No,
            )
            if reply == QMessageBox.Yes:
                dlg = _ConnectorConfigDialog(name, self)
                if dlg.exec() == QDialog.Accepted and dlg.executable_path:
                    self._save_connector_config(name, dlg.executable_path, dlg.launch_args)
                    self._launch_connector(name, dlg.executable_path, dlg.launch_args)
            return

        try:
            cmd = [exe_path]
            if args:
                cmd.extend(args.split())
            if sys.platform == "win32":
                os.startfile(exe_path)
            else:
                subprocess.Popen(
                    cmd,
                    start_new_session=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            QTimer.singleShot(2000, self._refresh_connector_statuses)
        except Exception as e:
            QMessageBox.critical(self, "启动失败", f"无法启动 {name}：\n{str(e)}")

    def _refresh_connector_statuses(self):
        for card in self._connector_cards:
            name = card._conn["name"]
            tool = query_one(
                "SELECT executable_path FROM software_tools WHERE software_name=?",
                (name,),
            )
            if tool and tool.get("executable_path"):
                exe_name = os.path.basename(tool["executable_path"])
                running = _is_process_running(exe_name)
            else:
                running = False
            card.refresh_status(running)

    def _add_custom_connector(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("添加启动项")
        dlg.setMinimumWidth(400)
        form = QFormLayout(dlg)

        name_edit = QLineEdit()
        name_edit.setPlaceholderText("启动项名称")
        form.addRow("名称：", name_edit)

        desc_edit = QLineEdit()
        desc_edit.setPlaceholderText("简要描述")
        form.addRow("描述：", desc_edit)

        path_edit = QLineEdit()
        path_edit.setPlaceholderText("可执行文件路径")
        form.addRow("程序路径：", path_edit)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel = QPushButton("取消")
        cancel.clicked.connect(dlg.reject)
        btn_row.addWidget(cancel)
        ok = QPushButton("保存")
        ok.clicked.connect(dlg.accept)
        btn_row.addWidget(ok)
        form.addRow(btn_row)

        if dlg.exec() == QDialog.Accepted:
            name = name_edit.text().strip()
            if not name:
                QMessageBox.warning(self, "提示", "启动项名称不能为空。")
                return
            exe_path = path_edit.text().strip()
            self._save_connector_config(name, exe_path, "")
            QMessageBox.information(self, "保存成功", f"启动项「{name}」已保存。")

    # ── Custom Experts (我的专家) ────────────────────────────────────────

    def _load_custom_experts(self):
        try:
            from core.settings_store import get_setting
            raw = get_setting("custom_experts", "[]")
            self._custom_experts = json.loads(raw) if raw else []
        except Exception:
            self._custom_experts = []

    def _show_my_experts(self):
        self._load_custom_experts()
        dlg = _CustomExpertDialog(self, list(self._custom_experts))
        dlg.exec()
        if dlg.changed:
            self._custom_experts = dlg.experts
            self._filter_experts(self._expert_filter_cat)

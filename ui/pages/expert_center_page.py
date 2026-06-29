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
    QTextEdit, QVBoxLayout, QWidget, QMessageBox,
)
from ui.dialogs.buddy_message import ask_confirm, show_error, show_info, show_success, show_warning

from db.database import query_all, query_one

EXPERT_CATEGORIES = [
    "全部", "技术工程", "产品设计", "内容创作", "金融投资",
    "数据智能", "法律咨询", "电商运营", "办公效率", "小微企业",
]

EXPERT_KIND_FILTERS = ["全部", "专家", "专家团"]

from core.expert_catalog import (
    FEATURED_SCENES,
    load_recent_experts,
    marketplace_items,
    missing_recommended_skills,
    recommended_skill_items,
    record_recent_expert,
)

from core.skill_catalog import (
    SKILL_CATEGORIES,
    catalog_market_stats,
    catalog_skills_for_category,
    is_planned_skill,
    is_skill_installed,
    skill_by_name,
    skill_type_label,
)
from core.remote_catalog import (
    fetch_remote_catalog,
    get_catalog_url,
    get_catalog_urls,
    load_cached_catalog,
)
from core.skill_discovery import (
    explain_search_expansion,
    fetch_trending_github_skills,
    find_similar_in_catalog,
    load_trending_cache,
    search_github_skills,
)
from core.skill_catalog import all_catalog_skills
from agent_runtime.skill_installer import (
    describe_github_install_compat,
    install_from_catalog,
    install_skill_from_url,
)
from ui.dialogs.skill_preview_dialog import SkillPreviewDialog
from ui.dialogs.expert_preview_dialog import ExpertPreviewDialog
from ui.widgets.skill_paged_browser import SkillPagedBrowser

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
    preview_requested = Signal(dict)

    def __init__(self, expert: dict, parent=None):
        super().__init__(parent)
        self.setObjectName("ExpertCard")
        self._expert = expert
        is_team = expert.get("kind") == "team"
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(6)

        top = QHBoxLayout()
        avatar = QLabel("👥" if is_team else "👤")
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

        members = expert.get("members") or []
        if members:
            m_lbl = QLabel("成员：" + "、".join(str(m) for m in members[:4]))
            m_lbl.setObjectName("MutedLabel")
            m_lbl.setWordWrap(True)
            layout.addWidget(m_lbl)

        tag_row = QHBoxLayout()
        tag_row.setSpacing(4)
        if is_team:
            t_team = QPushButton("真并行")
            t_team.setObjectName("TagButton")
            t_team.setProperty("tone", "parallel")
            t_team.setFixedHeight(24)
            t_team.setEnabled(False)
            tag_row.addWidget(t_team)
        badge = "专家团" if is_team else "单专家"
        t0 = QPushButton(badge)
        t0.setObjectName("TagButton")
        t0.setFixedHeight(22)
        t0.setEnabled(False)
        tag_row.addWidget(t0)
        n_skills = len(recommended_skill_items(expert))
        if n_skills:
            t_sk = QPushButton(f"Skill×{n_skills}")
            t_sk.setObjectName("TagButton")
            t_sk.setProperty("tone", "skill")
            t_sk.setFixedHeight(24)
            t_sk.setEnabled(False)
            tag_row.addWidget(t_sk)
        for tag in expert.get("tags", [])[:2]:
            t = QPushButton(tag)
            t.setObjectName("TagButton")
            t.setFixedHeight(22)
            t.setCursor(Qt.PointingHandCursor)
            tag_row.addWidget(t)
        tag_row.addStretch()
        layout.addLayout(tag_row)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)
        preview_btn = QPushButton("预览")
        preview_btn.setFixedHeight(28)
        preview_btn.setCursor(Qt.PointingHandCursor)
        preview_btn.clicked.connect(lambda: self.preview_requested.emit(self._expert))
        btn_row.addWidget(preview_btn)
        btn = QPushButton("召唤专家团（并行）" if is_team else "召唤专家")
        btn.setObjectName("SummonButton")
        btn.setCursor(Qt.PointingHandCursor)
        btn.clicked.connect(lambda: self.preview_requested.emit(self._expert))
        btn_row.addWidget(btn)
        layout.addLayout(btn_row)


# ── Skill Card ───────────────────────────────────────────────────────────

class _SkillCard(QFrame):
    install_requested = Signal(str)
    preview_requested = Signal(dict)

    def __init__(self, skill: dict, installed: bool = False, *, hot: bool = False, parent=None):
        super().__init__(parent)
        self.setObjectName("HotSkillCard" if hot else "ActionCard")
        self._skill = skill
        self._planned = is_planned_skill(skill)
        self.setCursor(Qt.PointingHandCursor)
        if hot:
            self.setFixedHeight(88)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(10)

        icon = QLabel(skill.get("icon", "⚡"))
        icon.setObjectName("CardIconBadge")
        icon.setFixedSize(40, 40)
        icon.setAlignment(Qt.AlignCenter)
        layout.addWidget(icon)

        col = QVBoxLayout()
        col.setSpacing(3)
        title = skill.get("display") or skill["name"]
        n = QLabel(title)
        n.setObjectName("CardTitle")
        col.addWidget(n)
        badge_text = skill_type_label(skill)
        if skill.get("hot") or hot:
            badge_text = "🔥 热门 · " + badge_text
        if skill.get("discovered"):
            badge_text += " · GitHub 实时"
        if skill.get("trending"):
            badge_text += " · 网络热门"
        if skill.get("similar"):
            badge_text += " · 目录相似"
        if skill.get("bundled"):
            badge_text += " · 随应用附带"
        elif skill.get("remote") and not skill.get("discovered"):
            badge_text += " · 远程目录"
        if skill.get("hot_rank"):
            badge_text += f" · #{skill['hot_rank']}"
        if skill.get("stars"):
            badge_text += f" · ⭐{skill['stars']}"
        badge = QLabel(badge_text)
        badge.setObjectName("SkillCardBadge")
        col.addWidget(badge)
        d = QLabel(skill.get("desc", ""))
        d.setObjectName("MutedLabel")
        d.setWordWrap(True)
        col.addWidget(d)
        layout.addLayout(col, 1)

        btn_col = QHBoxLayout()
        btn_col.setSpacing(6)
        if not self._planned:
            preview_btn = QPushButton("预览")
            preview_btn.setFixedHeight(28)
            preview_btn.setCursor(Qt.PointingHandCursor)
            preview_btn.clicked.connect(lambda: self.preview_requested.emit(self._skill))
            btn_col.addWidget(preview_btn)

        if self._planned:
            self._btn = QPushButton("占位")
            self._btn.setObjectName("PlannedMark")
            self._btn.setEnabled(False)
            self._btn.setFixedHeight(28)
        elif installed:
            self._btn = QPushButton("✓")
            self._btn.setObjectName("InstalledMark")
            self._btn.setEnabled(False)
            self._btn.setFixedSize(30, 30)
        else:
            self._btn = QPushButton("+")
            self._btn.setObjectName("InputIconButton")
            self._btn.setFixedSize(28, 28)
            self._btn.setCursor(Qt.PointingHandCursor)
            self._btn.clicked.connect(self._on_click)
        btn_col.addWidget(self._btn)
        layout.addLayout(btn_col)

    def mouseDoubleClickEvent(self, event):
        self.preview_requested.emit(self._skill)
        super().mouseDoubleClickEvent(event)

    def _on_click(self):
        self.install_requested.emit(self._skill["name"])

    def mark_installed(self):
        self._btn.setText("✓")
        self._btn.setObjectName("InstalledMark")
        self._btn.setEnabled(False)


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
        icon.setObjectName("ConnectorCardIcon")
        icon.setFixedSize(44, 44)
        icon.setAlignment(Qt.AlignCenter)
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
        self._status_dot.setObjectName("StatusDot")
        self._status_dot.setProperty("status", "connected" if connected else "disconnected")
        self._status_dot.style().unpolish(self._status_dot)
        self._status_dot.style().polish(self._status_dot)
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
            empty.setObjectName("MutedLabel")
            empty.setAlignment(Qt.AlignCenter)
            self._list_widget.addWidget(empty)
            return

        for i, expert in enumerate(self._experts):
            row = QFrame()
            row.setObjectName("CustomExpertRow")
            rl = QHBoxLayout(row)
            rl.setContentsMargins(12, 8, 12, 8)

            info = QVBoxLayout()
            name_lbl = QLabel(f"👤 {expert['name']}")
            name_lbl.setObjectName("CustomExpertName")
            info.addWidget(name_lbl)
            desc_lbl = QLabel(expert.get("desc", ""))
            desc_lbl.setObjectName("MutedLabel")
            desc_lbl.setWordWrap(True)
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
    _discovery_done = Signal(object)
    _trending_done = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("PageContainer")
        self._search_text = ""
        self._expert_filter_cat = "全部"
        self._expert_kind_filter = "全部"
        self._skill_filter_cat = "全部"
        self._skill_sub_tab = "market"
        self._custom_experts: list[dict] = []
        self._last_summoned_item: dict | None = None
        self._skill_cards: dict[str, _SkillCard] = {}
        self._connector_cards: list[_ConnectorCard] = []
        self._installed_skill_names: set[str] = set()
        self._extra_skills: dict[str, dict] = {}
        self._trending_skills: list[dict] = []
        self._last_discovery: dict = {"query": "", "similar": [], "discovered": []}
        self._catalog_refresh_busy = False
        self._discovery_busy = False
        self._trending_busy = False
        self._remote_catalog_done.connect(self._finish_remote_refresh)
        self._discovery_done.connect(self._finish_discovery)
        self._trending_done.connect(self._finish_trending)

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
        self._search.setPlaceholderText("搜索专家、专家团或标签")
        self._search.setFixedWidth(260)
        self._search.setFixedHeight(30)
        self._search.textChanged.connect(self._on_search_changed)
        self._search.returnPressed.connect(self._on_search_enter)
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
        self._catalog_bootstrapped = False

    def _ensure_startup_catalog(self) -> None:
        if self._catalog_bootstrapped:
            return
        self._catalog_bootstrapped = True
        QTimer.singleShot(300, self._startup_catalog_refresh)

    def _startup_catalog_refresh(self):
        """启动后后台拉远程目录并刷新当前 Tab。"""
        self._run_remote_catalog_fetch(force=False, show_dialog=False)
        QTimer.singleShot(400, lambda: self._ensure_trending_loaded(force=False))

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
        placeholders = [
            "搜索专家、专家团或标签",
            "搜索 Skill；中文会自动译英再联网发现",
            "搜索快捷启动项",
        ]
        self._search.setPlaceholderText(placeholders[idx])
        if idx == 1:
            self._ensure_trending_loaded(force=False)
            if self._skill_sub_tab == "installed":
                self._refresh_installed_skills_panel()

    def switch_to_tab(self, tab_name: str):
        mapping = {"experts": 0, "skills": 1, "connectors": 2}
        idx = mapping.get(tab_name, 0)
        self._switch_tab(idx)

    # ── Search ───────────────────────────────────────────────────────────

    def _on_search_changed(self, text: str):
        self._search_text = text.strip().lower()
        if not self._search_text:
            self._last_discovery = {"query": "", "similar": [], "discovered": []}
        current = self._stack.currentIndex()
        if current == 0:
            self._filter_experts(self._expert_filter_cat)
        elif current == 1:
            self._filter_skills(self._skill_filter_cat)
        elif current == 2:
            self._rebuild_connector_grid()

    def _on_search_enter(self):
        if self._stack.currentIndex() == 1 and self._search_text:
            self._run_online_discovery()

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
        self._expert_scroll = scroll

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        scene_title = QLabel("精选场景")
        scene_title.setObjectName("SectionTitle")
        layout.addWidget(scene_title)

        scene_hint = QLabel("点击场景卡片筛选对应分类与专家团（WorkBuddy 式入口）")
        scene_hint.setObjectName("MutedLabel")
        layout.addWidget(scene_hint)

        scene_row = QHBoxLayout()
        scene_row.setSpacing(12)
        self._hero_cards: list[QFrame] = []
        for scene in FEATURED_SCENES:
            card = QFrame()
            card.setObjectName("HeroCard")
            card.setFixedHeight(120)
            card.setMinimumWidth(160)
            card.setCursor(Qt.PointingHandCursor)
            title = scene["title"]
            card.setProperty("scene_category", scene.get("category", ""))
            card.setProperty("scene_team", scene.get("team", ""))
            card.mousePressEvent = lambda ev, sc=scene: self._on_scene_selected(sc)  # type: ignore[method-assign]
            c_layout = QVBoxLayout(card)
            c_layout.setContentsMargins(14, 12, 14, 12)
            t = QLabel(title)
            t.setObjectName("HeroCardTitle")
            c_layout.addWidget(t)
            team_lbl = QLabel(f"👥 {scene.get('team', '')}")
            team_lbl.setObjectName("HeroCardTeam")
            c_layout.addWidget(team_lbl)
            c_layout.addStretch()
            for s in (scene.get("highlights") or [])[:2]:
                sl = QLabel(f"👤 {s}")
                sl.setObjectName("HeroCardHighlight")
                c_layout.addWidget(sl)
            scene_row.addWidget(card)
            self._hero_cards.append(card)
        layout.addLayout(scene_row)

        self._recent_experts_bar = QFrame()
        recent_layout = QHBoxLayout(self._recent_experts_bar)
        recent_layout.setContentsMargins(0, 0, 0, 0)
        recent_layout.setSpacing(6)
        layout.addWidget(self._recent_experts_bar)
        self._refresh_recent_experts_bar()

        layout.addWidget(QLabel(""))
        section = QLabel("专家  ·  专家团")
        section.setObjectName("SectionTitle")
        layout.addWidget(section)

        kind_hint = QLabel(
            "单专家 = 明确单点任务；专家团 = 真并行（多成员同时分析 + 团长汇总）。"
            "向下滚动可看到专家团卡片，或点上方筛选「专家团」。"
        )
        kind_hint.setObjectName("MutedLabel")
        kind_hint.setWordWrap(True)
        layout.addWidget(kind_hint)

        self._expert_kind_filter_bar = _filter_bar(EXPERT_KIND_FILTERS, self._filter_expert_kind)
        layout.addWidget(self._expert_kind_filter_bar)

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

    def _refresh_recent_experts_bar(self) -> None:
        while self._recent_experts_bar.layout().count():
            item = self._recent_experts_bar.layout().takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        recent = load_recent_experts()
        if not recent:
            self._recent_experts_bar.setVisible(False)
            return
        self._recent_experts_bar.setVisible(True)
        row = self._recent_experts_bar.layout()
        lbl = QLabel("最近召唤：")
        lbl.setObjectName("MutedLabel")
        row.addWidget(lbl)
        all_items = {x["name"]: x for x in marketplace_items(custom_experts=self._custom_experts)}
        for name in recent[:6]:
            item = all_items.get(name)
            if not item:
                continue
            btn = QPushButton(name)
            btn.setObjectName("FilterButton")
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _, it=item: self._on_expert_preview(it))
            row.addWidget(btn)
        row.addStretch()

    def _on_scene_selected(self, scene: dict) -> None:
        category = scene.get("category") or "全部"
        self._expert_kind_filter = "专家团"
        for btn in self._expert_kind_filter_bar._buttons:
            btn.setChecked(btn.text() == "专家团")
        self._filter_experts(category)
        if getattr(self, "_expert_scroll", None):
            self._expert_scroll.verticalScrollBar().setValue(
                self._expert_grid_widget.y()
            )

    def _filter_expert_kind(self, kind: str) -> None:
        self._expert_kind_filter = kind
        self._filter_experts(self._expert_filter_cat)

    def _filter_experts(self, category: str):
        self._expert_filter_cat = category
        while self._expert_grid.count():
            item = self._expert_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        all_items = marketplace_items(
            custom_experts=self._custom_experts,
            kind_filter=self._expert_kind_filter,
            category=category,
            query=self._search_text,
        )

        if not all_items:
            empty = QLabel("暂无匹配的专家或专家团。")
            empty.setObjectName("MutedLabel")
            self._expert_grid.addWidget(empty, 0, 0, 1, 4)
            return

        for i, e in enumerate(all_items):
            card = _ExpertCard(e)
            card.preview_requested.connect(self._on_expert_preview)
            self._expert_grid.addWidget(card, i // 4, i % 4)

    def _on_expert_preview(self, item: dict) -> None:
        from core.skill_discovery import fetch_github_skills_for_expert

        try:
            threading.Thread(
                target=lambda: fetch_github_skills_for_expert(item, limit=8, force=False),
                daemon=True,
                name="PreviewDomainPrefetch",
            ).start()
        except Exception:
            pass

        dlg = ExpertPreviewDialog(
            item,
            custom_experts=self._custom_experts,
            installed_skill_names=self._installed_skill_names,
            parent=self,
        )
        dlg.install_skills_requested.connect(
            lambda skills, d=dlg: self._install_recommended_skills(skills, d)
        )
        dlg.summon_requested.connect(self._on_expert_summon_confirmed)
        dlg.exec()

    def _install_recommended_skills(
        self, skills: list[dict], dlg: ExpertPreviewDialog | None = None,
    ) -> None:
        from agent_runtime.tool_executor import load_installed_handlers
        from agent_runtime.skill_installer import install_skill_from_url

        if not skills:
            return
        installed_labels: list[str] = []
        errors: list[str] = []
        for skill in skills:
            if is_skill_installed(skill, self._installed_skill_names):
                continue
            try:
                if skill.get("install_url"):
                    result = install_skill_from_url(str(skill["install_url"]))
                    pkg = result.get("package_name", "") or skill.get("name", "")
                    display = result.get("manifest", {}).get("display_name") or skill.get("display") or pkg
                else:
                    result = install_from_catalog(skill)
                    pkg = skill.get("name", "")
                    display = skill.get("display") or pkg
                self._installed_skill_names.add(str(pkg).lower())
                self._installed_skill_names.add(str(display).lower())
                src = skill.get("source_kind") or ("github" if skill.get("discovered") else "official")
                label = f"{display}（{src}）"
                installed_labels.append(label)
            except Exception as exc:
                errors.append(f"{skill.get('display', skill.get('name'))}: {exc}")
        if installed_labels:
            load_installed_handlers()
            self._filter_skills(self._skill_filter_cat)
        if dlg:
            dlg.refresh_skill_rows(self._installed_skill_names)
        if installed_labels:
            show_success(
                self,
                "推荐 Skill 已安装",
                f"已安装 {len(installed_labels)} 个：{', '.join(installed_labels)}",
                detail="可在技能页「已安装」中启用，或在对话底栏切换 Skill。",
            )
        if errors:
            show_warning(self, "部分安装失败", "\n".join(errors))

    def _on_expert_summon_confirmed(self, item: dict, prompt: str) -> None:
        name = item.get("name", "")
        self._last_summoned_item = item
        record_recent_expert(name)
        self._refresh_recent_experts_bar()
        missing = missing_recommended_skills(item, installed_names=self._installed_skill_names)
        if missing:
            show_info(
                self,
                "推荐 Skill 未全部安装",
                f"「{name}」有 {len(missing)} 个推荐 Skill 尚未安装。\n"
                "可在预览里一键安装；不安装也可继续召唤。",
            )
        self.expert_selected.emit(name, prompt)

    def _on_expert_summon(self, name: str, prompt: str):
        record_recent_expert(name)
        self._refresh_recent_experts_bar()
        self.expert_selected.emit(name, prompt)

    # ── Skill Tab ────────────────────────────────────────────────────────

    def _build_skill_tab(self) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setObjectName("PageScroll")

        outer = QWidget()
        outer_layout = QVBoxLayout(outer)
        outer_layout.setContentsMargins(24, 20, 24, 20)
        outer_layout.setSpacing(12)

        sub_tabs = QHBoxLayout()
        sub_tabs.setSpacing(12)
        self._skill_sub_buttons: list[QPushButton] = []
        for key, text in [("market", "技能市场"), ("installed", "已安装")]:
            btn = QPushButton(text)
            btn.setObjectName("FilterButton")
            btn.setCheckable(True)
            btn.setChecked(key == "market")
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _, k=key: self._switch_skill_sub_tab(k))
            self._skill_sub_buttons.append(btn)
            sub_tabs.addWidget(btn)
        sub_tabs.addStretch()
        self._skill_refresh_btn = QPushButton("从网络刷新")
        self._skill_refresh_btn.setObjectName("FilterButton")
        self._skill_refresh_btn.setCursor(Qt.PointingHandCursor)
        self._skill_refresh_btn.clicked.connect(self._refresh_remote_catalog)
        sub_tabs.addWidget(self._skill_refresh_btn)
        self._online_discover_btn = QPushButton("联网搜索")
        self._online_discover_btn.setObjectName("FilterButton")
        self._online_discover_btn.setCursor(Qt.PointingHandCursor)
        self._online_discover_btn.clicked.connect(self._run_online_discovery)
        sub_tabs.addWidget(self._online_discover_btn)
        outer_layout.addLayout(sub_tabs)

        self._skill_sub_stack = QStackedWidget()
        self._skill_sub_stack.addWidget(self._build_skill_market_panel())
        self._skill_sub_stack.addWidget(self._build_skill_installed_panel())
        outer_layout.addWidget(self._skill_sub_stack, 1)

        scroll.setWidget(outer)
        return scroll

    def _switch_skill_sub_tab(self, key: str) -> None:
        self._skill_sub_tab = key
        for btn in self._skill_sub_buttons:
            btn.setChecked(
                (btn.text() == "技能市场" and key == "market")
                or (btn.text() == "已安装" and key == "installed")
            )
        self._skill_sub_stack.setCurrentIndex(0 if key == "market" else 1)
        market_mode = key == "market"
        self._skill_refresh_btn.setVisible(market_mode)
        self._online_discover_btn.setVisible(market_mode)
        if key == "installed":
            self._refresh_installed_skills_panel()

    def _build_skill_market_panel(self) -> QWidget:
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        self._catalog_status = QLabel("")
        self._catalog_status.setObjectName("MutedLabel")
        layout.addWidget(self._catalog_status)
        self._discovery_status = QLabel("")
        self._discovery_status.setObjectName("MutedLabel")
        layout.addWidget(self._discovery_status)
        self._update_catalog_status_label()

        self._discovery_block = QWidget()
        discovery_layout = QVBoxLayout(self._discovery_block)
        discovery_layout.setContentsMargins(0, 0, 0, 0)
        discovery_layout.setSpacing(8)
        self._discovery_title = QLabel("🌐 网络热门 Skill（GitHub 实时 · 加载中…）")
        self._discovery_title.setObjectName("SectionTitle")
        discovery_layout.addWidget(self._discovery_title)
        self._discovery_hint = QLabel(
            "打开技能页自动从 GitHub 拉取高星 Agent/Skill 仓库（最多 100 个）。"
            "在本页上下滚动即可浏览热门列表与下方官方目录。"
        )
        self._discovery_hint.setObjectName("MutedLabel")
        self._discovery_hint.setWordWrap(True)
        discovery_layout.addWidget(self._discovery_hint)
        self._discovery_browser = SkillPagedBrowser(page_size=12, parent=self._discovery_block)
        self._discovery_browser.install_requested.connect(self._on_skill_install)
        self._discovery_browser.preview_requested.connect(self._on_skill_preview)
        discovery_layout.addWidget(self._discovery_browser)
        layout.addWidget(self._discovery_block)

        market_title = QLabel("📋 官方 Skill 目录（随应用附带）")
        market_title.setObjectName("SectionTitle")
        layout.addWidget(market_title)

        self._catalog_hint = QLabel(
            "以下为 Buddy 内置精选 Skill（config/catalog.json），非 GitHub 热门列表。"
        )
        self._catalog_hint.setObjectName("MutedLabel")
        self._catalog_hint.setWordWrap(True)
        layout.addWidget(self._catalog_hint)

        self._skill_filter_bar = _filter_bar(SKILL_CATEGORIES, self._filter_skills)
        layout.addWidget(self._skill_filter_bar)

        self._skill_empty_label = QLabel("")
        self._skill_empty_label.setObjectName("MutedLabel")
        self._skill_empty_label.setWordWrap(True)
        layout.addWidget(self._skill_empty_label)

        self._skill_browser = SkillPagedBrowser(page_size=12, parent=content)
        self._skill_browser.install_requested.connect(self._on_skill_install)
        self._skill_browser.preview_requested.connect(self._on_skill_preview)
        layout.addWidget(self._skill_browser)

        self._filter_skills("全部")
        layout.addStretch()
        return content

    def _build_skill_installed_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        title = QLabel("已安装 Skill")
        title.setObjectName("SectionTitle")
        layout.addWidget(title)

        hint = QLabel(
            "WorkBuddy 式「已安装」视图：启用/关闭后，下一条 Craft/Plan 对话是否注入该 Skill。"
            "完整编辑请用右上角「添加技能」旁的 Skill 管理或设置页。"
        )
        hint.setObjectName("MutedLabel")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self._installed_skills_host = QWidget()
        self._installed_skills_layout = QVBoxLayout(self._installed_skills_host)
        self._installed_skills_layout.setContentsMargins(0, 0, 0, 0)
        self._installed_skills_layout.setSpacing(8)
        layout.addWidget(self._installed_skills_host)
        layout.addStretch()
        return panel

    def _refresh_installed_skills_panel(self) -> None:
        from db.database import execute, query_all

        while self._installed_skills_layout.count():
            item = self._installed_skills_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        rows = query_all(
            "SELECT id, package_name, display_name, enabled, install_path "
            "FROM installed_skill_packages ORDER BY enabled DESC, id DESC"
        )
        if not rows:
            empty = QLabel("暂无已安装 Skill。请切换到「技能市场」浏览并安装。")
            empty.setObjectName("MutedLabel")
            empty.setWordWrap(True)
            self._installed_skills_layout.addWidget(empty)
            return

        for row in rows:
            frame = QFrame()
            frame.setObjectName("ActionCard")
            row_layout = QHBoxLayout(frame)
            row_layout.setContentsMargins(12, 10, 12, 10)
            col = QVBoxLayout()
            name = row.get("display_name") or row.get("package_name")
            col.addWidget(QLabel(name))
            path_lbl = QLabel(str(row.get("install_path") or ""))
            path_lbl.setObjectName("MutedLabel")
            path_lbl.setWordWrap(True)
            col.addWidget(path_lbl)
            row_layout.addLayout(col, 1)

            enabled = bool(row.get("enabled"))
            toggle = QPushButton("已启用" if enabled else "已关闭")
            toggle.setCursor(Qt.PointingHandCursor)
            pkg_id = row["id"]

            def _flip(pid=pkg_id, btn=toggle):
                turn_on = btn.text() != "已启用"
                execute(
                    "UPDATE installed_skill_packages SET enabled=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                    (1 if turn_on else 0, pid),
                )
                btn.setText("已启用" if turn_on else "已关闭")
                from agent_runtime.tool_executor import load_installed_handlers
                load_installed_handlers()
                self._load_installed_skills()

            toggle.clicked.connect(_flip)
            row_layout.addWidget(toggle)

            use_btn = QPushButton("在对话中使用")
            use_btn.setObjectName("SummonButton")
            use_btn.setCursor(Qt.PointingHandCursor)
            pkg_name = row.get("package_name") or ""
            use_btn.clicked.connect(
                lambda _, p=pkg_name, d=name: self._use_installed_skill(p, d)
            )
            row_layout.addWidget(use_btn)
            self._installed_skills_layout.addWidget(frame)

    def _use_installed_skill(self, package_name: str, display_name: str) -> None:
        from agent_runtime.tool_executor import load_installed_handlers
        load_installed_handlers()
        self.skill_installed.emit(package_name, display_name)

    def _update_catalog_status_label(self):
        urls = get_catalog_urls()
        url_display = get_catalog_url()
        cached = load_cached_catalog() or {}
        stats = catalog_market_stats()
        n_experts = len(cached.get("experts") or [])
        updated = cached.get("updated_at") or ""
        ver = cached.get("version") or ""
        err = cached.get("fetch_error") or ""
        cache_key = "|".join(urls)
        cached_key = "|".join(cached.get("source_urls") or []) or cached.get("source_url") or ""

        if cached_key == cache_key and (stats["raw"] or n_experts or stats["visible"]):
            extra = (
                f" · 市场 {stats['visible']} 个"
                f"（远程原始 {stats['raw']}，已隐藏占位 {stats['hidden_stubs']}）"
            )
            if stats["bundled"]:
                extra += f" · 随应用附带 {stats['bundled']}"
            if stats.get("remote_visible"):
                extra += f" · 远程目录 {stats['remote_visible']}"
            if len(urls) > 1:
                extra += f" · {len(urls)} 个源"
            if ver:
                extra += f" · v{ver}"
            if updated:
                extra += f" · {updated}"
            self._catalog_status.setText(f"远程目录：{url_display}{extra}")
        elif err:
            self._catalog_status.setText(
                f"远程目录：{url_display} · 部分拉取失败（{err}）· 可点「从网络刷新」重试"
            )
        else:
            self._catalog_status.setText(
                f"远程目录：{url_display} · 市场 {stats['visible']} 个 Skill · 正在拉取…"
            )

    def _make_skill_card(self, skill: dict, installed: bool) -> _SkillCard:
        is_hot = bool(skill.get("hot_rank") or skill.get("hot"))
        return _SkillCard(skill, installed=installed, hot=is_hot)

    def _fill_skill_browser(self, browser: SkillPagedBrowser, skills: list[dict]) -> dict[str, _SkillCard]:
        browser.set_skills(
            skills,
            card_factory=self._make_skill_card,
            is_installed=lambda s: is_skill_installed(s, self._installed_skill_names),
        )
        browser.setVisible(bool(skills))
        return browser.cards()  # type: ignore[return-value]

    def _populate_skill_grid(self, catalog_skills: list[dict], discovered_skills: list[dict]):
        self._skill_cards.clear()

        # 网络热门区（始终展示，加载中可为空）
        self._discovery_block.setVisible(True)
        if discovered_skills:
            self._discovery_title.setText(
                f"🌐 网络热门 Skill（GitHub 实时 · {len(discovered_skills)} 个）"
            )
            self._skill_cards.update(self._fill_skill_browser(self._discovery_browser, discovered_skills))
        else:
            self._discovery_title.setText("🌐 网络热门 Skill（GitHub 实时 · 加载中…）")
            self._fill_skill_browser(self._discovery_browser, [])

        if not catalog_skills:
            self._skill_empty_label.setText("官方目录暂无 Skill。")
            self._skill_empty_label.setVisible(True)
            self._fill_skill_browser(self._skill_browser, [])
            return

        self._skill_empty_label.setVisible(False)
        self._skill_cards.update(self._fill_skill_browser(self._skill_browser, catalog_skills))

    def _resolve_skill(self, name: str) -> dict | None:
        return skill_by_name(name) or self._extra_skills.get(name)

    def _filter_skills(self, category: str):
        self._skill_filter_cat = category
        catalog = catalog_skills_for_category(category)
        if self._search_text:
            catalog = [s for s in catalog if _skill_matches_query(s, self._search_text)]

        if self._search_text and self._last_discovery.get("query") == self._search_text:
            seen = {s.get("name") for s in catalog}
            for s in self._last_discovery.get("similar") or []:
                if s.get("name") in seen:
                    continue
                if category != "全部" and s.get("category") != category:
                    continue
                catalog.append(s)
                seen.add(s.get("name"))

        discovered: list[dict] = []
        if self._search_text and self._last_discovery.get("query") == self._search_text:
            discovered = list(self._last_discovery.get("discovered") or [])
        else:
            discovered = list(self._trending_skills)

        self._populate_skill_grid(catalog, discovered)

    def _ensure_trending_loaded(self, *, force: bool = False) -> None:
        if self._trending_busy:
            return
        if self._trending_skills and not force:
            self._filter_skills(self._skill_filter_cat)
            return
        if not force:
            cached = load_trending_cache()
            if cached and cached.get("skills"):
                self._trending_skills = list(cached["skills"])
                for s in self._trending_skills:
                    self._extra_skills[s["name"]] = s
                self._discovery_status.setText(
                    f"已加载 GitHub 热门 Skill {len(self._trending_skills)} 个（缓存）"
                )
                self._filter_skills(self._skill_filter_cat)
                return

        self._trending_busy = True
        self._discovery_status.setText("正在从 GitHub 拉取热门 Skill（最多 100 个）…")

        def work():
            err = None
            skills: list[dict] = []
            try:
                skills = fetch_trending_github_skills(limit=100, force=force)
            except Exception as exc:
                err = exc
            self._trending_done.emit((err, skills))

        threading.Thread(target=work, daemon=True, name="TrendingSkillsFetch").start()

    def _finish_trending(self, payload):
        err, skills = payload
        self._trending_busy = False
        if err:
            self._discovery_status.setText(f"热门 Skill 加载失败：{err}")
            if not self._trending_skills:
                show_warning(self, "热门 Skill", f"无法从 GitHub 拉取热门列表：{err}")
        else:
            self._trending_skills = skills
            for s in skills:
                self._extra_skills[s["name"]] = s
            self._discovery_status.setText(
                f"已加载 GitHub 热门 Skill {len(skills)} 个 · 上下滚动浏览"
            )
        if not self._search_text or self._last_discovery.get("query") != self._search_text:
            self._filter_skills(self._skill_filter_cat)

    def _run_online_discovery(self):
        q = self._search_text
        if not q:
            show_info(self, "请输入关键词", "在搜索框输入关键词后按回车，或点「联网搜索」。")
            return
        if self._discovery_busy:
            return
        self._discovery_busy = True
        self._online_discover_btn.setEnabled(False)
        self._online_discover_btn.setText("搜索中…")
        self._discovery_status.setText(f"正在联网搜索「{q}」…")

        def work():
            err = None
            similar: list[dict] = []
            discovered: list[dict] = []
            try:
                catalog = all_catalog_skills()
                similar = find_similar_in_catalog(q, catalog)
                discovered = search_github_skills(q, limit=100)
            except Exception as exc:
                err = exc
            self._discovery_done.emit((err, q, similar, discovered))

        threading.Thread(target=work, daemon=True, name="SkillDiscovery").start()

    def _finish_discovery(self, payload):
        err, q, similar, discovered = payload
        self._discovery_busy = False
        self._online_discover_btn.setEnabled(True)
        self._online_discover_btn.setText("联网搜索")

        for s in discovered:
            self._extra_skills[s["name"]] = s

        self._last_discovery = {
            "query": q.strip().lower(),
            "similar": similar,
            "discovered": discovered,
        }

        if err:
            self._discovery_status.setText(f"联网搜索失败：{err}")
            show_warning(self, "联网搜索失败", str(err))
        else:
            expand_hint = explain_search_expansion(q)
            self._discovery_status.setText(
                f"「{q}」：目录内 {len(similar)} 个相似 · GitHub {len(discovered)} 个（最多 100，分页浏览）"
                + (f" · {expand_hint}" if expand_hint else "")
            )
        self._filter_skills(self._skill_filter_cat)

    def _on_skill_preview(self, skill: dict):
        installed = is_skill_installed(skill, self._installed_skill_names)
        dlg = SkillPreviewDialog(skill, installed=installed, parent=self)
        dlg.install_requested.connect(self._install_skill_data)
        dlg.exec()

    def _refresh_remote_catalog(self):
        self._run_remote_catalog_fetch(force=True, show_dialog=True)
        self._ensure_trending_loaded(force=True)

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
            stats = catalog_market_stats()
            cached = load_cached_catalog() or {}
            n_experts = len(cached.get("experts") or [])
            ver = cached.get("version") or "?"
            detail = (
                f"市场可安装 Skill：{stats['visible']} 个\n"
                f"远程原始条目：{stats['raw']} 个\n"
                f"已隐藏占位：{stats['hidden_stubs']} 个\n"
                f"随应用附带：{stats['bundled']} 个（config/catalog.json）\n"
                f"远程目录有效：{stats.get('remote_visible', 0)} 个\n"
                f"远程专家：{n_experts} 个 · catalog v{ver}\n\n"
            )
            if stats["visible"] <= 2:
                detail += (
                    "上方「官方目录」含应用自带 Skill；「联网发现」需搜索后才会出现 GitHub 实时结果。"
                )
            else:
                detail += "在搜索框输入关键词可筛选；需要新 Skill 请用「联网搜索」。"
            show_success(
                self,
                "目录已更新",
                "已从网络同步 Skill 目录。",
                detail=detail,
            )

    def _on_skill_install(self, skill_name: str):
        skill_data = self._resolve_skill(skill_name)
        if not skill_data:
            show_warning(self, "未找到", f"未找到技能「{skill_name}」的信息。")
            return
        self._install_skill_data(skill_data)

    def _install_skill_data(self, skill_data: dict):
        from agent_runtime.tool_executor import load_installed_handlers

        skill_name = skill_data.get("name", "")
        if is_planned_skill(skill_data):
            show_info(
                self, "占位 Skill",
                f"「{skill_data.get('display', skill_name)}」仅为目录占位（说明过短），不可安装。\n"
                "请使用「联网搜索」查找完整 Skill 包，或等待 catalog 更新。",
            )
            return

        try:
            if skill_data.get("install_url"):
                result = install_skill_from_url(skill_data["install_url"])
            else:
                result = install_from_catalog(skill_data)
            load_installed_handlers()
            pkg = result.get("package_name", "") or skill_name
            display = skill_data.get("display") or skill_name
            self._installed_skill_names.add(skill_name)
            if pkg:
                self._installed_skill_names.add(pkg.lower())
            self._installed_skill_names.add(display.lower())
            for extra in result.get("packages") or []:
                self._installed_skill_names.add(str(extra).lower())

            card = self._skill_cards.get(skill_name)
            if card:
                card.mark_installed()
            elif self._skill_browser:
                self._skill_browser.mark_installed(skill_name)
            if getattr(self, "_discovery_browser", None):
                self._discovery_browser.mark_installed(skill_name)

            batch_n = result.get("batch_installed") or 0
            install_mode = result.get("install_mode") or ""
            if batch_n > 1:
                pkg_list = ", ".join(result.get("packages") or [])
                success_title = f"已批量安装 {batch_n} 个 Skill"
                success_msg = f"从「{display}」仓库识别并安装了 {batch_n} 个子 Skill。"
                success_detail = (
                    "✓ 每个子 Skill 的说明文档已写入本地目录\n"
                    "✓ 聊天底栏 Skill 下拉可切换使用\n"
                    "✓ 仓库内的 scripts/hooks 不会自动执行\n\n"
                    f"已安装：{pkg_list}\n"
                    f"首个路径：{result.get('install_path', '')}"
                )
            elif install_mode == "repo_fallback":
                success_title = "已安装（简易模式）"
                success_msg = f"「{display}」未找到 Skill 说明文档，已用 README/描述生成简易 Skill。"
                success_detail = (
                    "效果可能有限；建议优先安装含 skills/ 或 .claude/skills/ 子目录的仓库。\n\n"
                    f"路径：{result.get('install_path', '')}"
                )
            else:
                success_title = "已装配到 Agent"
                success_msg = f"技能「{display}」安装成功，已写入本地 Skill 目录。"
                success_detail = (
                    "✓ 下一条 Craft / Plan 对话将自动注入该 Skill 说明\n"
                    "✓ 聊天底栏 Skill 下拉已切换为仅此 Skill\n"
                    "✓ 含工具的 Skill 会注册专用函数\n\n"
                    f"路径：{result.get('install_path', '')}"
                )

            self._filter_skills(self._skill_filter_cat)

            self.skill_installed.emit(pkg, display)
            show_success(
                self,
                success_title,
                success_msg,
                detail=success_detail,
            )
            if self._skill_sub_tab == "installed":
                self._refresh_installed_skills_panel()
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
                for extra in result.get("packages") or []:
                    self._installed_skill_names.add(str(extra).lower())
                batch_n = result.get("batch_installed") or 0
                if batch_n > 1:
                    msg = (
                        f"已从仓库批量安装 {batch_n} 个 Skill。\n"
                        f"已安装：{', '.join(result.get('packages') or [])}\n"
                        f"首个路径：{result.get('install_path', '')}"
                    )
                elif result.get("install_mode") == "repo_fallback":
                    msg = (
                        f"未找到 Skill 说明文档，已简易安装「{display}」。\n"
                        f"路径：{result.get('install_path', '')}"
                    )
                else:
                    msg = f"技能「{display}」已安装。\n路径：{result.get('install_path', '')}"
                QMessageBox.information(self, "安装成功", msg)
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

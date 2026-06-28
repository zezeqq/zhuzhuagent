"""专家 / 专家团召唤前预览对话框。"""

from __future__ import annotations

import threading

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit,
    QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from core.expert_catalog import (
    companion_skills_for_expert,
    expert_domain_search_hint,
    resolve_summon_prompt,
    skill_source_label,
)
from core.skill_discovery import explain_search_expansion, fetch_github_skills_for_expert, search_github_skills


class ExpertPreviewDialog(QDialog):
    summon_requested = Signal(dict, str)
    install_skills_requested = Signal(list)
    _domain_loaded = Signal(object)
    _search_loaded = Signal(object)

    def __init__(
        self,
        item: dict,
        *,
        custom_experts: list[dict] | None = None,
        installed_skill_names: set[str] | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self._item = item
        self._custom_experts = custom_experts or []
        self._installed = installed_skill_names or set()
        self._domain_github_skills: list[dict] = []
        self._domain_query = expert_domain_search_hint(item)
        self._domain_busy = False
        self._search_busy = False
        self._search_results: list[dict] = []

        is_team = item.get("kind") == "team"
        title_label = "专家团" if is_team else "专家"
        self.setObjectName("BuddyMessageDialog")
        self.setWindowTitle(f"{title_label}预览 — {item.get('name', '')}")
        self.setMinimumSize(620, 640)

        self._domain_loaded.connect(self._on_domain_loaded)
        self._search_loaded.connect(self._on_search_loaded)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        card = QFrame()
        card.setObjectName("BuddyMessageCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(10)

        mode_banner = QLabel(
            "👥 专家团 · 真并行：发送任务后多路调用成员，再由团长汇总。"
            if is_team
            else "👤 单专家：注入角色提示；下方可安装官方或 GitHub Skill 增强能力。"
        )
        mode_banner.setObjectName("ExpertPreviewBanner")
        mode_banner.setWordWrap(True)
        layout.addWidget(mode_banner)

        title = QLabel(item.get("name", ""))
        title.setObjectName("BuddyMessageTitle")
        layout.addWidget(title)

        meta_parts = []
        if item.get("category"):
            meta_parts.append(item["category"])
        meta_parts.append("专家团" if is_team else "单专家")
        if item.get("provider"):
            meta_parts.append(item["provider"])
        meta = QLabel(" · ".join(meta_parts))
        meta.setObjectName("MutedLabel")
        meta.setWordWrap(True)
        layout.addWidget(meta)

        desc = QLabel(item.get("desc", ""))
        desc.setWordWrap(True)
        layout.addWidget(desc)

        members = item.get("members") or []
        if members:
            layout.addWidget(QLabel("团队成员：" + "、".join(str(m) for m in members)))

        skill_scroll = QScrollArea()
        skill_scroll.setWidgetResizable(True)
        skill_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        skill_scroll.setMaximumHeight(300)
        skill_scroll.setObjectName("PageScroll")

        skill_content = QWidget()
        skill_outer = QVBoxLayout(skill_content)
        skill_outer.setContentsMargins(0, 0, 0, 0)
        skill_outer.setSpacing(8)

        self._skill_host = QWidget()
        self._skill_layout = QVBoxLayout(self._skill_host)
        self._skill_layout.setContentsMargins(0, 0, 0, 0)
        self._skill_layout.setSpacing(8)
        skill_outer.addWidget(self._skill_host)

        search_title = QLabel("自行搜索 GitHub Skill")
        search_title.setObjectName("SectionTitle")
        skill_outer.addWidget(search_title)

        search_row = QHBoxLayout()
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText(
            f"如 {expert_domain_search_hint(item)[:36]}… 或输入自定义关键词"
        )
        self._search_input.returnPressed.connect(self._run_skill_search)
        search_row.addWidget(self._search_input, 1)
        search_btn = QPushButton("搜索")
        search_btn.setProperty("variant", "ghost")
        search_btn.setCursor(Qt.PointingHandCursor)
        search_btn.clicked.connect(self._run_skill_search)
        search_row.addWidget(search_btn)
        skill_outer.addLayout(search_row)

        self._search_hint = QLabel("")
        self._search_hint.setObjectName("MutedLabel")
        self._search_hint.setWordWrap(True)
        skill_outer.addWidget(self._search_hint)

        self._search_results_host = QWidget()
        self._search_results_layout = QVBoxLayout(self._search_results_host)
        self._search_results_layout.setContentsMargins(0, 0, 0, 0)
        self._search_results_layout.setSpacing(6)
        skill_outer.addWidget(self._search_results_host)

        skill_scroll.setWidget(skill_content)
        layout.addWidget(skill_scroll)

        self._skill_groups: dict[str, list[dict]] = {}
        self._render_skill_rows()

        hint = QLabel("角色提示（专家团并行阶段不调用工具，仅分析与汇总）：")
        hint.setObjectName("MutedLabel")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        body = QPlainTextEdit()
        body.setReadOnly(True)
        body.setPlainText(resolve_summon_prompt(item, self._custom_experts).strip())
        body.setObjectName("PreviewText")
        body.setMinimumHeight(120)
        layout.addWidget(body, 1)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        close_btn = QPushButton("关闭")
        close_btn.setProperty("variant", "ghost")
        close_btn.clicked.connect(self.reject)
        btn_row.addWidget(close_btn)
        summon_btn = QPushButton("召唤专家团并进入对话" if is_team else "召唤专家并进入对话")
        summon_btn.setProperty("variant", "primary")
        summon_btn.clicked.connect(self._on_summon)
        btn_row.addWidget(summon_btn)
        layout.addLayout(btn_row)

        root.addWidget(card)
        self._start_domain_fetch()

    def _start_domain_fetch(self) -> None:
        if self._domain_busy:
            return
        self._domain_busy = True
        item = self._item

        def work():
            err = None
            query = ""
            skills: list[dict] = []
            try:
                query, skills = fetch_github_skills_for_expert(item, limit=8, force=False)
            except Exception as exc:
                err = exc
            self._domain_loaded.emit((err, query, skills))

        threading.Thread(target=work, daemon=True, name="ExpertDomainSkills").start()

    def _on_domain_loaded(self, payload) -> None:
        err, query, skills = payload
        self._domain_busy = False
        if query:
            self._domain_query = query
        if skills:
            self._domain_github_skills = list(skills)
            self._render_skill_rows()
        elif err:
            self._render_skill_rows(domain_status=f"方向热门加载失败：{err}")

    def _run_skill_search(self) -> None:
        q = self._search_input.text().strip()
        if not q:
            self._search_hint.setText("请输入关键词后再搜索。")
            return
        if self._search_busy:
            return
        self._search_busy = True
        self._search_hint.setText(f"正在搜索 GitHub…（{explain_search_expansion(q)}）")
        self._clear_layout(self._search_results_layout)

        def work():
            err = None
            skills: list[dict] = []
            try:
                skills = search_github_skills(q, limit=12)
            except Exception as exc:
                err = exc
            self._search_loaded.emit((err, q, skills))

        threading.Thread(target=work, daemon=True, name="ExpertSkillSearch").start()

    def _on_search_loaded(self, payload) -> None:
        err, query, skills = payload
        self._search_busy = False
        self._clear_layout(self._search_results_layout)
        if err:
            self._search_hint.setText(f"搜索失败：{err}")
            return
        self._search_results = list(skills)
        self._search_hint.setText(
            f"「{query}」找到 {len(skills)} 个结果 · {explain_search_expansion(query)}"
        )
        if not skills:
            empty = QLabel("未找到匹配的 GitHub Skill，可换英文关键词或更具体的领域词。")
            empty.setObjectName("MutedLabel")
            empty.setWordWrap(True)
            self._search_results_layout.addWidget(empty)
            return
        for sk in skills:
            row = dict(sk)
            from core.skill_catalog import is_skill_installed
            row["source_kind"] = "github"
            row["installed"] = is_skill_installed(sk, self._installed)
            self._append_skill_row(self._search_results_layout, row)

    def _render_skill_rows(self, *, domain_status: str = "") -> None:
        while self._skill_layout.count():
            item = self._skill_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                self._clear_layout(item.layout())

        self._skill_groups = companion_skills_for_expert(
            self._item,
            installed_names=self._installed,
            domain_github_skills=self._domain_github_skills or None,
        )

        domain_hint = self._domain_query or expert_domain_search_hint(self._item)
        sections = [
            ("official", "官方配套（config/catalog.json · 随应用附带）"),
            ("pinned", "专家指定 GitHub（recommended_skills 内 install_url）"),
            ("remote", "远程目录（catalog 远程源）"),
            ("github", f"GitHub 方向热门（按「{domain_hint}」联网匹配）"),
        ]

        any_skill = False
        for key, section_title in sections:
            rows = self._skill_groups.get(key) or []
            if key == "github" and self._domain_busy and not rows:
                loading = QLabel(f"{section_title}\n正在按工作方向从 GitHub 搜索…")
                loading.setObjectName("MutedLabel")
                loading.setWordWrap(True)
                self._skill_layout.addWidget(loading)
                continue
            if key == "github" and domain_status and not rows:
                note = QLabel(f"{section_title}\n{domain_status}")
                note.setObjectName("MutedLabel")
                note.setWordWrap(True)
                self._skill_layout.addWidget(note)
                continue
            if not rows:
                continue
            any_skill = True
            sec = QLabel(section_title)
            sec.setObjectName("SectionTitle")
            sec.setWordWrap(True)
            self._skill_layout.addWidget(sec)

            for sk in rows:
                self._append_skill_row(self._skill_layout, sk)

            missing = [s for s in rows if not s.get("installed")]
            if missing:
                batch = QPushButton(f"安装本组全部（{len(missing)} 个）")
                batch.setProperty("variant", "ghost")
                batch.setCursor(Qt.PointingHandCursor)
                batch.clicked.connect(lambda _, m=missing: self._install_batch(m))
                self._skill_layout.addWidget(batch)

        if not any_skill and not self._domain_busy:
            note = QLabel(
                "暂无自动匹配的配套 Skill。可使用下方搜索框在 GitHub 查找并安装，"
                "或配置远程 catalog / recommended_skills。"
            )
            note.setObjectName("MutedLabel")
            note.setWordWrap(True)
            self._skill_layout.addWidget(note)
        elif any_skill:
            tip = QLabel(
                "「方向热门」根据专家分类、标签与职责在 GitHub 联网搜索；"
                "也可在下方自行搜索并选取安装。"
            )
            tip.setObjectName("MutedLabel")
            tip.setWordWrap(True)
            self._skill_layout.addWidget(tip)

    def _append_skill_row(self, parent_layout: QVBoxLayout, sk: dict) -> None:
        row = QHBoxLayout()
        label = sk.get("display") or sk.get("name", "")
        src = skill_source_label(sk)
        stars = f" ⭐{sk['stars']}" if sk.get("stars") else ""
        status = "✓ 已安装" if sk.get("installed") else "未安装"
        row.addWidget(QLabel(f"{label}{stars}  · {src}  · {status}"), 1)
        if not sk.get("installed"):
            btn = QPushButton("安装")
            btn.setFixedHeight(26)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _, s=sk: self._install_one(s))
            row.addWidget(btn)
        parent_layout.addLayout(row)

    def _install_one(self, skill: dict) -> None:
        self.install_skills_requested.emit([skill])

    def _install_batch(self, skills: list[dict]) -> None:
        self.install_skills_requested.emit(list(skills))

    def refresh_skill_rows(self, installed_names: set[str]) -> None:
        self._installed = installed_names
        self._render_skill_rows()
        if self._search_results:
            self._clear_layout(self._search_results_layout)
            tagged = []
            for sk in self._search_results:
                row = dict(sk)
                from core.skill_catalog import is_skill_installed
                row["installed"] = is_skill_installed(sk, installed_names)
                row["source_kind"] = "github"
                tagged.append(row)
            self._search_results = tagged
            for sk in tagged:
                self._append_skill_row(self._search_results_layout, sk)

    @staticmethod
    def _clear_layout(layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                ExpertPreviewDialog._clear_layout(item.layout())

    def _on_summon(self) -> None:
        prompt = resolve_summon_prompt(self._item, self._custom_experts)
        self.summon_requested.emit(self._item, prompt)
        self.accept()

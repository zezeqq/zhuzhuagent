from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMenu,
    QPushButton, QScrollArea, QSizePolicy, QTextEdit, QVBoxLayout, QWidget,
)

from db.database import delete, execute, insert, query_all


TEMPLATES = [
    ("📋", "产品需求全流程", "从需求采集、PRD 到研发测试验收"),
    ("📊", "市场调研与竞品分析", "深度调研、竞品拆解、报告评审"),
    ("📚", "团队知识库", "持续沉淀 SOP、经验和 FAQ"),
    ("🚀", "项目交付", "管理客户需求、计划、风险和验收"),
    ("🐛", "Bug 跟踪/测试验收", "持续跟踪 Bug，统一测试用例和验收"),
]

TEMPLATE_INSTRUCTIONS: dict[str, str] = {
    "产品需求全流程": (
        "本项目遵循产品需求全流程管理规范。\n"
        "1. 需求采集：收集用户反馈与业务需求，整理成需求池\n"
        "2. PRD 编写：输出完整的产品需求文档，包含功能说明、交互流程、验收标准\n"
        "3. 研发跟进：拆解技术任务，跟踪开发进度\n"
        "4. 测试验收：编写测试用例，执行测试，汇总验收报告"
    ),
    "市场调研与竞品分析": (
        "本项目聚焦市场调研与竞品分析。\n"
        "1. 行业概览：梳理目标市场规模、趋势与政策环境\n"
        "2. 竞品拆解：从产品功能、定价、用户评价等维度对标竞品\n"
        "3. 用户洞察：整理目标用户画像与核心需求\n"
        "4. 报告评审：输出结构化调研报告，提出策略建议"
    ),
    "团队知识库": (
        "本项目用于建设和维护团队知识库。\n"
        "1. SOP 沉淀：整理标准作业流程文档\n"
        "2. 经验记录：记录项目经验教训和最佳实践\n"
        "3. FAQ 汇总：收集常见问题与解答，持续更新\n"
        "4. 知识检索：支持关键词搜索和分类浏览"
    ),
    "项目交付": (
        "本项目用于管理项目交付全过程。\n"
        "1. 需求确认：与客户确认需求范围与验收标准\n"
        "2. 计划制定：制定里程碑和交付计划，分配资源\n"
        "3. 风险管理：识别项目风险，制定应对策略\n"
        "4. 验收交付：组织验收演示，输出交付物清单和完工报告"
    ),
    "Bug 跟踪/测试验收": (
        "本项目用于 Bug 跟踪和测试验收管理。\n"
        "1. Bug 记录：统一 Bug 提交格式（标题、步骤、期望、实际、截图）\n"
        "2. 状态跟踪：管理 Bug 生命周期（新建→确认→修复→验证→关闭）\n"
        "3. 测试用例：编写和维护测试用例集\n"
        "4. 验收报告：汇总测试通过率、遗留问题和上线建议"
    ),
}


class _ProjectCard(QFrame):
    clicked = Signal(int)
    delete_requested = Signal(int)

    def __init__(self, project: dict, parent=None):
        super().__init__(parent)
        self.setObjectName("ProjectCard")
        self.setCursor(Qt.PointingHandCursor)
        self._pid = project["id"]
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(6)

        top = QHBoxLayout()
        icon = QLabel("📁")
        icon.setFixedWidth(28)
        icon.setStyleSheet("font-size:20px; background:transparent;")
        top.addWidget(icon)
        name = QLabel(project.get("project_name", "未命名"))
        name.setObjectName("ProjectCardName")
        top.addWidget(name, 1)

        if project.get("is_current"):
            badge = QLabel("当前")
            badge.setStyleSheet(
                "background:#2563eb; color:white; font-size:11px; "
                "padding:2px 8px; border-radius:4px;"
            )
            top.addWidget(badge)

        layout.addLayout(top)

        created = project.get("created_at", "")[:10]
        sub = QLabel(f"添加于 {created}" if created else "")
        sub.setObjectName("MutedLabel")
        layout.addWidget(sub)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self._pid)
        super().mouseReleaseEvent(event)

    def _show_context_menu(self, pos):
        menu = QMenu(self)
        delete_action = QAction("删除", self)
        delete_action.triggered.connect(lambda: self.delete_requested.emit(self._pid))
        menu.addAction(delete_action)
        menu.exec(self.mapToGlobal(pos))


class _TemplateCard(QFrame):
    clicked = Signal(str)

    def __init__(self, icon: str, title: str, desc: str, parent=None):
        super().__init__(parent)
        self.setObjectName("ActionCard")
        self.setCursor(Qt.PointingHandCursor)
        self._title = title

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)

        ic = QLabel(icon)
        ic.setFixedWidth(28)
        ic.setStyleSheet("font-size:18px; background:transparent;")
        layout.addWidget(ic)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        t = QLabel(title)
        t.setObjectName("CardTitle")
        t.setStyleSheet("font-size:13px;")
        text_col.addWidget(t)
        d = QLabel(desc)
        d.setObjectName("MutedLabel")
        d.setWordWrap(True)
        text_col.addWidget(d)
        layout.addLayout(text_col, 1)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self._title)
        super().mouseReleaseEvent(event)


class NewProjectDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("新建项目")
        self.setFixedSize(520, 480)
        self.setObjectName("SettingsDialog")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        layout.addWidget(QLabel("项目名称"))
        self._name_input = QLineEdit()
        self._name_input.setPlaceholderText("请输入项目名称")
        layout.addWidget(self._name_input)

        layout.addWidget(QLabel("指令"))
        self._desc_input = QTextEdit()
        self._desc_input.setPlaceholderText(
            "提供当前项目的背景信息和规范，让 Agent 的回复更精准、更符合要求。\n"
            "比如：项目目标、团队习惯、风格偏好、输出约束等"
        )
        self._desc_input.setFixedHeight(140)
        layout.addWidget(self._desc_input)

        for label_text in ["快捷启动（可选）", "专家（可选）", "技能（可选）"]:
            row = QHBoxLayout()
            row.addWidget(QLabel(label_text))
            row.addStretch()
            add_btn = QPushButton("+ 添加")
            add_btn.setProperty("variant", "ghost")
            add_btn.setCursor(Qt.PointingHandCursor)
            row.addWidget(add_btn)
            layout.addLayout(row)

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
        ok.clicked.connect(self._create)
        btn_row.addWidget(ok)
        layout.addLayout(btn_row)

    def _create(self):
        name = self._name_input.text().strip()
        if not name:
            return
        desc = self._desc_input.toPlainText().strip()
        insert("projects", {
            "project_name": name,
            "project_description": desc,
            "is_current": 0,
        })
        self.accept()


class ProjectPage(QFrame):
    project_selected = Signal(int)
    project_activated = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("PageContainer")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setObjectName("PageScroll")

        content = QWidget()
        self._content_layout = QVBoxLayout(content)
        self._content_layout.setContentsMargins(40, 32, 40, 32)
        self._content_layout.setSpacing(24)

        self._build_header()
        self._build_my_projects()
        self._build_templates()
        self._content_layout.addStretch()

        scroll.setWidget(content)
        layout.addWidget(scroll)

    def _build_header(self):
        title = QLabel("项目")
        title.setObjectName("PageTitle")
        self._content_layout.addWidget(title)

        sub = QLabel("多人协同，打造超级团队")
        sub.setObjectName("PageSubtitle")
        self._content_layout.addWidget(sub)

        btn = QPushButton("＋  新建项目")
        btn.setProperty("variant", "primary")
        btn.setCursor(Qt.PointingHandCursor)
        btn.setFixedWidth(140)
        btn.clicked.connect(self._new_project)
        self._content_layout.addWidget(btn)

    def _build_my_projects(self):
        header = QHBoxLayout()
        title = QLabel("我的项目")
        title.setObjectName("SectionTitle")
        header.addWidget(title)
        header.addStretch()
        self._search = QLineEdit()
        self._search.setPlaceholderText("搜索项目")
        self._search.setFixedWidth(160)
        self._search.setFixedHeight(30)
        self._search.textChanged.connect(self._refresh_projects)
        header.addWidget(self._search)
        self._content_layout.addLayout(header)

        self._project_grid_widget = QWidget()
        self._project_grid = QGridLayout(self._project_grid_widget)
        self._project_grid.setSpacing(12)
        self._content_layout.addWidget(self._project_grid_widget)
        self._refresh_projects()

    def _build_templates(self):
        title = QLabel("从模版创建")
        title.setObjectName("SectionTitle")
        self._content_layout.addWidget(title)

        grid_w = QWidget()
        grid = QGridLayout(grid_w)
        grid.setSpacing(12)
        for i, (icon, name, desc) in enumerate(TEMPLATES):
            card = _TemplateCard(icon, name, desc)
            card.clicked.connect(self._on_template_clicked)
            grid.addWidget(card, i // 3, i % 3)
        self._content_layout.addWidget(grid_w)

    def _refresh_projects(self):
        while self._project_grid.count():
            item = self._project_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        keyword = self._search.text().strip() if hasattr(self, "_search") else ""
        if keyword:
            projects = query_all(
                "SELECT * FROM projects WHERE project_name LIKE ? ORDER BY is_current DESC, id DESC",
                (f"%{keyword}%",),
            )
        else:
            projects = query_all("SELECT * FROM projects ORDER BY is_current DESC, id DESC")

        for i, p in enumerate(projects):
            card = _ProjectCard(p)
            card.clicked.connect(self._on_project_clicked)
            card.delete_requested.connect(self._on_delete_project)
            self._project_grid.addWidget(card, i // 3, i % 3)

    def _on_project_clicked(self, project_id: int) -> None:
        execute("UPDATE projects SET is_current=0", ())
        execute("UPDATE projects SET is_current=1 WHERE id=?", (project_id,))
        self._refresh_projects()
        self.project_activated.emit(project_id)

    def _on_delete_project(self, project_id: int) -> None:
        delete("projects", project_id)
        execute("DELETE FROM files WHERE project_id=?", (project_id,))
        execute("DELETE FROM file_chunks WHERE project_id=?", (project_id,))
        self._refresh_projects()

    def _new_project(self):
        dlg = NewProjectDialog(self.window())
        if dlg.exec() == QDialog.Accepted:
            self._refresh_projects()

    def _on_template_clicked(self, name: str):
        dlg = NewProjectDialog(self.window())
        dlg._name_input.setText(name)
        instructions = TEMPLATE_INSTRUCTIONS.get(name, "")
        if instructions:
            dlg._desc_input.setPlainText(instructions)
        if dlg.exec() == QDialog.Accepted:
            self._refresh_projects()

    def refresh(self):
        self._refresh_projects()

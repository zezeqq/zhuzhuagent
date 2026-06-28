from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QScrollArea, QTabWidget, QTextEdit, QVBoxLayout, QWidget,
)


EXPERTS = [
    {"name": "公路机电专家", "icon": "🛣", "category": "工程", "desc": "精通交通监控、收费、通信、供配电、照明和隧道机电系统", "domain": "公路机电", "prompt": "你是一位资深的公路机电工程专家，精通高速公路和国省干线的监控、收费、通信、供配电、照明以及隧道机电系统的设计、施工、调试和运维。"},
    {"name": "投标专家", "icon": "📋", "category": "工程", "desc": "擅长解读招标文件技术要求，组织技术方案和响应内容", "domain": "投标管理", "prompt": "你是一位经验丰富的投标技术响应专家，擅长解读招标文件中的技术要求、评分标准，组织技术方案响应和偏离表编制。"},
    {"name": "测试专家", "icon": "🔧", "category": "工程", "desc": "熟悉公路机电工程各系统的测试方法、仪器使用和记录规范", "domain": "现场测试", "prompt": "你是一位现场测试专家，熟悉公路机电工程各系统的测试方法、仪器使用和记录规范，能指导现场测试工作。"},
    {"name": "质量专家", "icon": "✅", "category": "工程", "desc": "精通质量检验评定标准，熟悉检验流程和评定方法", "domain": "质量管理", "prompt": "你是一位工程质量管理专家，精通公路工程质量检验评定标准，熟悉检验流程、评定方法和资料编制。"},
    {"name": "Python 开发", "icon": "🐍", "category": "开发", "desc": "精通自动化脚本、数据处理、Web开发", "domain": "Python", "prompt": "你是一位Python全栈开发专家，精通自动化脚本、数据处理、Web框架（Flask/Django/FastAPI）、爬虫和桌面应用开发。"},
    {"name": "前端开发", "icon": "🌐", "category": "开发", "desc": "精通HTML/CSS/JS、Vue/React、移动端适配", "domain": "前端", "prompt": "你是一位前端开发专家，精通HTML/CSS/JavaScript、Vue/React框架、响应式布局和移动端适配。"},
    {"name": "数据分析师", "icon": "📊", "category": "数据", "desc": "擅长数据清洗、统计分析、可视化图表", "domain": "数据分析", "prompt": "你是一位数据分析专家，擅长使用Python进行数据清洗、统计分析、可视化图表制作和报告撰写。"},
    {"name": "文档专家", "icon": "📝", "category": "办公", "desc": "擅长项目方案、施工组织设计、工程总结和验收资料的撰写", "domain": "文档撰写", "prompt": "你是一位工程技术文档编写专家，擅长项目方案、施工组织设计、工程总结和验收资料的撰写。"},
    {"name": "PPT 设计", "icon": "🎨", "category": "办公", "desc": "擅长制作专业汇报演示文稿，逻辑清晰、视觉美观", "domain": "PPT制作", "prompt": "你是一位PPT设计专家，擅长制作专业汇报演示文稿，注重逻辑清晰、视觉美观和信息层次。"},
    {"name": "法务顾问", "icon": "⚖", "category": "法务", "desc": "熟悉合同审查、风险评估、法律条款解读", "domain": "法务", "prompt": "你是一位法务顾问，熟悉合同审查、风险评估、法律条款解读，能为工程项目提供法律支持。"},
    {"name": "财务顾问", "icon": "💰", "category": "财务", "desc": "擅长预算编制、成本分析、财务报表解读", "domain": "财务", "prompt": "你是一位财务顾问，擅长工程项目的预算编制、成本分析、财务报表解读和资金管理。"},
    {"name": "AI 助手", "icon": "🤖", "category": "通用", "desc": "通用智能助手，什么都能聊", "domain": "通用", "prompt": ""},
]


class ExpertDialog(QDialog):
    expert_selected = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("专家中心")
        self.setMinimumSize(820, 580)
        self.setObjectName("SettingsDialog")

        self._my_experts: list[dict] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QFrame()
        header.setObjectName("SkillHeader")
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(24, 16, 24, 16)
        title = QLabel("专家中心")
        title.setObjectName("SettingsSection")
        h_layout.addWidget(title)
        h_layout.addStretch()
        close_btn = QPushButton("✕")
        close_btn.setProperty("variant", "ghost")
        close_btn.setFixedSize(32, 32)
        close_btn.clicked.connect(self.close)
        h_layout.addWidget(close_btn)
        layout.addWidget(header)

        self._tabs = QTabWidget()
        self._tabs.setObjectName("SkillTabs")
        self._tabs.addTab(self._center_tab(), "专家中心")
        self._tabs.addTab(self._my_experts_tab(), "我的专家")
        layout.addWidget(self._tabs, 1)

    def _center_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        filter_row = QHBoxLayout()
        filter_row.setSpacing(6)
        self._cat_btns: dict[str, QPushButton] = {}
        categories = ["全部", "工程", "开发", "数据", "办公", "法务", "财务", "通用"]
        for cat in categories:
            btn = QPushButton(cat)
            btn.setObjectName("FilterButton")
            btn.setCheckable(True)
            btn.setChecked(cat == "全部")
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _, c=cat: self._filter_experts(c))
            self._cat_btns[cat] = btn
            filter_row.addWidget(btn)
        filter_row.addStretch()
        layout.addLayout(filter_row)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setObjectName("ArtifactScroll")
        self._grid_container = QWidget()
        self._grid_layout = QGridLayout(self._grid_container)
        self._grid_layout.setContentsMargins(0, 0, 0, 0)
        self._grid_layout.setSpacing(12)
        scroll.setWidget(self._grid_container)
        layout.addWidget(scroll, 1)

        self._render_experts("全部")
        return page

    def _render_experts(self, category: str) -> None:
        while self._grid_layout.count():
            item = self._grid_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        experts = EXPERTS if category == "全部" else [e for e in EXPERTS if e["category"] == category]
        for idx, expert in enumerate(experts):
            card = self._expert_card(expert)
            self._grid_layout.addWidget(card, idx // 3, idx % 3)
        for col in range(3):
            self._grid_layout.setColumnStretch(col, 1)

    def _expert_card(self, expert: dict) -> QFrame:
        card = QFrame()
        card.setObjectName("ActionCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(6)

        top = QHBoxLayout()
        icon_label = QLabel(expert["icon"])
        icon_label.setFixedWidth(28)
        icon_label.setStyleSheet("font-size: 20px;")
        top.addWidget(icon_label)
        name_label = QLabel(expert["name"])
        name_label.setObjectName("CardTitle")
        top.addWidget(name_label, 1)
        layout.addLayout(top)

        desc_label = QLabel(expert["desc"])
        desc_label.setObjectName("MutedLabel")
        desc_label.setWordWrap(True)
        layout.addWidget(desc_label)

        tag_row = QHBoxLayout()
        tag_row.setSpacing(6)
        domain_tag = QLabel(expert["domain"])
        domain_tag.setObjectName("FilterButton")
        domain_tag.setStyleSheet("padding: 2px 8px; font-size: 11px;")
        tag_row.addWidget(domain_tag)
        tag_row.addStretch()
        layout.addLayout(tag_row)

        summon_btn = QPushButton("召唤专家")
        summon_btn.setProperty("variant", "primary")
        summon_btn.setCursor(Qt.PointingHandCursor)
        summon_btn.setFixedHeight(30)
        summon_btn.clicked.connect(lambda: self._summon(expert["name"], expert["prompt"]))
        layout.addWidget(summon_btn)
        return card

    def _summon(self, name: str, prompt: str) -> None:
        self.expert_selected.emit(name, prompt)
        self.close()

    def _filter_experts(self, category: str) -> None:
        for cat, btn in self._cat_btns.items():
            btn.setChecked(cat == category)
        self._render_experts(category)

    def _my_experts_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        create_btn = QPushButton("＋ 创建专家")
        create_btn.setProperty("variant", "primary")
        create_btn.setCursor(Qt.PointingHandCursor)
        create_btn.clicked.connect(self._show_create_form)
        toolbar.addWidget(create_btn)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        self._my_list_scroll = QScrollArea()
        self._my_list_scroll.setWidgetResizable(True)
        self._my_list_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._my_list_scroll.setObjectName("ArtifactScroll")
        self._my_list_container = QWidget()
        self._my_list_layout = QVBoxLayout(self._my_list_container)
        self._my_list_layout.setContentsMargins(0, 0, 0, 0)
        self._my_list_layout.setSpacing(8)
        self._my_list_layout.addStretch()
        self._my_list_scroll.setWidget(self._my_list_container)
        layout.addWidget(self._my_list_scroll, 1)

        self._create_section = QFrame()
        self._create_section.setObjectName("ActionCard")
        self._create_section.setVisible(False)
        form_layout = QVBoxLayout(self._create_section)
        form_layout.setContentsMargins(16, 14, 16, 14)
        form_layout.setSpacing(10)

        section_title = QLabel("创建自定义专家")
        section_title.setObjectName("SettingsSection")
        form_layout.addWidget(section_title)

        self._expert_name_input = QLineEdit()
        self._expert_name_input.setPlaceholderText("专家名称")
        self._expert_name_input.setMinimumHeight(34)
        form_layout.addWidget(self._expert_name_input)

        self._expert_desc_input = QLineEdit()
        self._expert_desc_input.setPlaceholderText("简短描述")
        self._expert_desc_input.setMinimumHeight(34)
        form_layout.addWidget(self._expert_desc_input)

        prompt_label = QLabel("系统提示词")
        prompt_label.setObjectName("MutedLabel")
        form_layout.addWidget(prompt_label)

        self._expert_prompt_input = QTextEdit()
        self._expert_prompt_input.setPlaceholderText("输入专家的系统提示词（System Prompt），定义该专家的角色、能力和行为…")
        self._expert_prompt_input.setMinimumHeight(120)
        form_layout.addWidget(self._expert_prompt_input)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        cancel_btn = QPushButton("取消")
        cancel_btn.setProperty("variant", "ghost")
        cancel_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn.clicked.connect(lambda: self._create_section.setVisible(False))
        btn_row.addWidget(cancel_btn)
        save_btn = QPushButton("保存专家")
        save_btn.setProperty("variant", "primary")
        save_btn.setCursor(Qt.PointingHandCursor)
        save_btn.clicked.connect(self._save_expert)
        btn_row.addWidget(save_btn)
        btn_row.addStretch()
        form_layout.addLayout(btn_row)

        layout.addWidget(self._create_section)
        self._refresh_my_experts()
        return page

    def _show_create_form(self) -> None:
        self._create_section.setVisible(True)
        self._expert_name_input.clear()
        self._expert_desc_input.clear()
        self._expert_prompt_input.clear()
        self._expert_name_input.setFocus()

    def _save_expert(self) -> None:
        name = self._expert_name_input.text().strip()
        desc = self._expert_desc_input.text().strip()
        prompt = self._expert_prompt_input.toPlainText().strip()
        if not name:
            return
        expert = {"name": name, "icon": "🧑‍💼", "category": "自定义", "desc": desc or name, "domain": "自定义", "prompt": prompt}
        self._my_experts.append(expert)
        self._create_section.setVisible(False)
        self._refresh_my_experts()

    def _refresh_my_experts(self) -> None:
        while self._my_list_layout.count() > 1:
            item = self._my_list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        if not self._my_experts:
            empty = QLabel("还没有自定义专家，点击「创建专家」开始。")
            empty.setObjectName("MutedLabel")
            empty.setAlignment(Qt.AlignCenter)
            self._my_list_layout.insertWidget(0, empty)
            return
        for idx, expert in enumerate(self._my_experts):
            card = QFrame()
            card.setObjectName("ActionCard")
            c_layout = QHBoxLayout(card)
            c_layout.setContentsMargins(14, 10, 14, 10)
            c_layout.setSpacing(10)
            icon_label = QLabel(expert["icon"])
            icon_label.setFixedWidth(28)
            c_layout.addWidget(icon_label)
            info_col = QVBoxLayout()
            info_col.setSpacing(2)
            name_label = QLabel(expert["name"])
            name_label.setObjectName("CardTitle")
            desc_label = QLabel(expert["desc"])
            desc_label.setObjectName("MutedLabel")
            info_col.addWidget(name_label)
            info_col.addWidget(desc_label)
            c_layout.addLayout(info_col, 1)
            summon_btn = QPushButton("召唤")
            summon_btn.setProperty("variant", "secondary")
            summon_btn.setCursor(Qt.PointingHandCursor)
            summon_btn.setFixedHeight(28)
            summon_btn.clicked.connect(lambda _, e=expert: self._summon(e["name"], e["prompt"]))
            c_layout.addWidget(summon_btn)
            self._my_list_layout.insertWidget(self._my_list_layout.count() - 1, card)

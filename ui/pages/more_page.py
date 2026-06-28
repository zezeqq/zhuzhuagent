from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel,
    QPushButton, QScrollArea, QVBoxLayout, QWidget,
)


RESOURCE_ITEMS = [
    ("📚", "资料库", "导入本地文档并建立向量索引，供 Agent 本地检索引用"),
]

INSPIRATION_PROMPTS = [
    ("💡", "头脑风暴", "帮我围绕一个主题进行头脑风暴，生成 10 个创意点子"),
    ("✍️", "写作灵感", "给我一个有趣的写作题目和大纲，包含开头引子"),
    ("🎨", "设计灵感", "推荐 5 个当下流行的 UI 设计趋势和案例"),
    ("📊", "数据洞察", "帮我分析一组数据可能隐藏的业务规律"),
    ("🚀", "产品创意", "为一个新产品生成 MVP 功能清单和优先级"),
    ("📝", "周报模板", "帮我生成本周工作周报，按项目分类"),
]


class _ResourceCard(QFrame):
    clicked = Signal(str)

    def __init__(self, icon: str, title: str, desc: str, parent=None):
        super().__init__(parent)
        self.setObjectName("ActionCard")
        self.setCursor(Qt.PointingHandCursor)
        self._title = title

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(12)

        ic = QLabel(icon)
        ic.setFixedSize(40, 40)
        ic.setAlignment(Qt.AlignCenter)
        ic.setStyleSheet("font-size:22px; background:#1e293b; border-radius:10px;")
        layout.addWidget(ic)

        col = QVBoxLayout()
        col.setSpacing(2)
        t = QLabel(title)
        t.setObjectName("CardTitle")
        col.addWidget(t)
        d = QLabel(desc)
        d.setObjectName("MutedLabel")
        d.setWordWrap(True)
        col.addWidget(d)
        layout.addLayout(col, 1)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self._title)
        super().mouseReleaseEvent(event)


class _InspirationCard(QFrame):
    prompt_selected = Signal(str)

    def __init__(self, icon: str, title: str, prompt: str, parent=None):
        super().__init__(parent)
        self.setObjectName("ActionCard")
        self.setCursor(Qt.PointingHandCursor)
        self._prompt = prompt

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(6)

        top = QHBoxLayout()
        ic = QLabel(icon)
        ic.setStyleSheet("font-size:18px; background:transparent;")
        top.addWidget(ic)
        t = QLabel(title)
        t.setObjectName("CardTitle")
        t.setStyleSheet("font-size:13px;")
        top.addWidget(t)
        top.addStretch()
        layout.addLayout(top)

        d = QLabel(prompt)
        d.setObjectName("MutedLabel")
        d.setWordWrap(True)
        layout.addWidget(d)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.prompt_selected.emit(self._prompt)
        super().mouseReleaseEvent(event)


class MorePage(QFrame):
    prompt_selected = Signal(str)
    open_settings_page = Signal(str)

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
        layout = QVBoxLayout(content)
        layout.setContentsMargins(40, 32, 40, 32)
        layout.setSpacing(24)

        title = QLabel("更多")
        title.setObjectName("PageTitle")
        layout.addWidget(title)

        self._res_title = QLabel("资料库")
        self._res_title.setObjectName("SectionTitle")
        layout.addWidget(self._res_title)

        res_grid = QWidget()
        rg = QHBoxLayout(res_grid)
        rg.setSpacing(12)
        for icon, name, desc in RESOURCE_ITEMS:
            card = _ResourceCard(icon, name, desc)
            card.clicked.connect(self._on_resource_clicked)
            rg.addWidget(card)
        open_btn = QPushButton("管理资料库…")
        open_btn.setProperty("variant", "secondary")
        open_btn.setCursor(Qt.PointingHandCursor)
        open_btn.clicked.connect(self._open_library)
        rg.addWidget(open_btn)
        rg.addStretch()
        layout.addWidget(res_grid)

        self._insp_title = QLabel("灵感")
        self._insp_title.setObjectName("SectionTitle")
        layout.addWidget(self._insp_title)

        insp_grid = QWidget()
        ig = QGridLayout(insp_grid)
        ig.setSpacing(12)
        for i, (icon, name, prompt) in enumerate(INSPIRATION_PROMPTS):
            card = _InspirationCard(icon, name, prompt)
            card.prompt_selected.connect(self.prompt_selected.emit)
            ig.addWidget(card, i // 3, i % 3)
        layout.addWidget(insp_grid)

        layout.addStretch()
        scroll.setWidget(content)
        outer.addWidget(scroll)

    def scroll_to_section(self, section: str) -> None:
        target = self._res_title if section == "resources" else self._insp_title
        target.parent().parent().ensureWidgetVisible(target)

    def _on_resource_clicked(self, title: str) -> None:
        self._open_library()

    def _open_library(self) -> None:
        from ui.dialogs.library_dialog import LibraryDialog
        LibraryDialog(self.window()).exec()

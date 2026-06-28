"""Skill 列表网格 — 随外层页面垂直滚动，不拦截滚轮。"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QGridLayout, QLabel, QVBoxLayout, QWidget

COLS = 2


class SkillPagedBrowser(QFrame):
    """双列 Skill 卡片网格；滚动交给外层 QScrollArea。"""

    install_requested = Signal(str)
    preview_requested = Signal(dict)

    def __init__(self, *, page_size: int = 12, parent=None):
        super().__init__(parent)
        # page_size 保留参数以兼容旧调用，不再分页
        self._page_size = page_size
        self._skills: list[dict] = []
        self._card_factory: Callable[[dict, bool], QFrame] | None = None
        self._cards: dict[str, QFrame] = {}
        self._is_installed: Callable[[dict], bool] = lambda _s: False

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)

        self._grid_host = QWidget()
        self._grid = QGridLayout(self._grid_host)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(10)
        root.addWidget(self._grid_host)

        self._count_label = QLabel("")
        self._count_label.setObjectName("MutedLabel")
        self._count_label.setAlignment(Qt.AlignRight)
        root.addWidget(self._count_label)

    def cards(self) -> dict[str, QFrame]:
        return self._cards

    def set_skills(
        self,
        skills: list[dict],
        *,
        card_factory: Callable[[dict, bool], QFrame],
        is_installed: Callable[[dict], bool] | None = None,
    ) -> None:
        self._skills = list(skills)
        self._card_factory = card_factory
        self._is_installed = is_installed or (lambda _s: False)
        self._cards.clear()
        self._rebuild_grid()

    def mark_installed(self, skill_name: str) -> None:
        card = self._cards.get(skill_name)
        if card and hasattr(card, "mark_installed"):
            card.mark_installed()

    def _clear_grid(self) -> None:
        while self._grid.count():
            item = self._grid.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def _rebuild_grid(self) -> None:
        self._clear_grid()

        if not self._skills or not self._card_factory:
            self._count_label.setText("")
            return

        for i, skill in enumerate(self._skills):
            installed = self._is_installed(skill)
            card = self._card_factory(skill, installed)
            name = skill.get("name", "")
            if name:
                self._cards[name] = card
            if hasattr(card, "install_requested"):
                card.install_requested.connect(self.install_requested.emit)
            if hasattr(card, "preview_requested"):
                card.preview_requested.connect(self.preview_requested.emit)
            self._grid.addWidget(card, i // COLS, i % COLS)

        n = len(self._skills)
        self._count_label.setText(f"共 {n} 个 · 上下滚动浏览")

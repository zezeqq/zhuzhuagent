from __future__ import annotations

import os
import subprocess
import sys

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton,
    QScrollArea, QVBoxLayout, QWidget,
)

from core.conversation_manager import (
    conversation_task_info, delete_conversation, list_conversations, search_conversations,
)
from core.app_identity import APP_NAME, APP_VERSION
from core.settings_store import get_setting
from ui.widgets.batch_action_bar import BatchActionBar
from ui.widgets.avatar_button import AvatarButton


class TaskCard(QFrame):
    clicked = Signal(int)
    delete_requested = Signal(int)
    check_changed = Signal(int, bool)

    def __init__(self, conversation: dict, parent=None):
        super().__init__(parent)
        self.setObjectName("TaskCard")
        self.setCursor(Qt.PointingHandCursor)
        self.conv_id = conversation["id"]
        self._selected = False
        self._multi_mode = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(8)

        self._check = QCheckBox()
        self._check.setObjectName("TaskCardCheck")
        self._check.setVisible(False)
        self._check.stateChanged.connect(self._emit_check_changed)
        layout.addWidget(self._check)

        mode = conversation.get("mode", "craft")
        mode_icons = {"ask": "💬", "craft": "⚡", "plan": "📋"}
        icon = QLabel(mode_icons.get(mode, "⚡"))
        icon.setFixedWidth(18)
        icon.setStyleSheet("background:transparent;")
        layout.addWidget(icon)

        col = QVBoxLayout()
        col.setSpacing(1)
        title = QLabel(conversation.get("title", "新任务"))
        title.setObjectName("TaskCardTitle")
        title.setWordWrap(False)
        col.addWidget(title)
        time_text = conversation.get("updated_at", "")[:16] if conversation.get("updated_at") else ""
        if time_text:
            time_label = QLabel(time_text)
            time_label.setObjectName("TaskCardTime")
            col.addWidget(time_label)
        layout.addLayout(col, 1)

        info = conversation_task_info(self.conv_id)
        if info:
            status = info.get("status", "")
            badge_map = {"completed": "✓", "running": "◉", "failed": "✕"}
            icon_text = badge_map.get(status, "")
            if icon_text:
                badge = QLabel(icon_text)
                badge.setObjectName("TaskBadge")
                badge.setProperty("tone", status)
                layout.addWidget(badge)

    def set_multi_select_mode(self, enabled: bool) -> None:
        self._multi_mode = enabled
        self._check.setVisible(enabled)
        if not enabled:
            self._check.setChecked(False)

    def set_checked(self, checked: bool) -> None:
        self._check.blockSignals(True)
        self._check.setChecked(checked)
        self._check.blockSignals(False)

    def is_checked(self) -> bool:
        return self._check.isChecked()

    def _emit_check_changed(self, state: int) -> None:
        self.check_changed.emit(self.conv_id, state == Qt.CheckState.Checked)

    def set_selected(self, selected: bool) -> None:
        self._selected = selected
        self.setProperty("selected", "true" if selected else "false")
        self.style().unpolish(self)
        self.style().polish(self)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self._multi_mode:
                widget = self.childAt(event.pos())
                if isinstance(widget, QCheckBox):
                    super().mouseReleaseEvent(event)
                    return
                self._check.setChecked(not self._check.isChecked())
            else:
                self.clicked.emit(self.conv_id)
        super().mouseReleaseEvent(event)

    def contextMenuEvent(self, event):
        from PySide6.QtWidgets import QMenu
        menu = QMenu(self)
        menu.addAction("📌 置顶")
        menu.addAction("✏️ 重命名")
        menu.addSeparator()
        delete_action = menu.addAction("🗑️ 删除")
        action = menu.exec(event.globalPos())
        if action == delete_action:
            self.delete_requested.emit(self.conv_id)


class _NavItem(QFrame):
    clicked = Signal()

    def __init__(self, icon: str, label: str, sub_links: list[tuple[str, str]] | None = None, parent=None):
        super().__init__(parent)
        self.setObjectName("SidebarNavItem")
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(40)
        self._key = label
        self._selected = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 10, 0)
        layout.setSpacing(8)

        ic = QLabel(icon)
        ic.setFixedWidth(18)
        ic.setStyleSheet("background:transparent; font-size:13px;")
        layout.addWidget(ic)

        lbl = QLabel(label)
        lbl.setObjectName("NavItemLabel")
        self._label_widget = lbl
        layout.addWidget(lbl, 1)

        if sub_links:
            for sub_text, sub_key in sub_links:
                sub = QPushButton(sub_text)
                sub.setObjectName("NavSubLink")
                sub.setCursor(Qt.PointingHandCursor)
                sub.setProperty("sub_key", sub_key)
                layout.addWidget(sub)

    def set_label(self, text: str) -> None:
        if hasattr(self, "_label_widget"):
            self._label_widget.setText(text)

    def set_selected(self, selected: bool):
        self._selected = selected
        self.setProperty("selected", "true" if selected else "false")
        self.style().unpolish(self)
        self.style().polish(self)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)


class _CollapsibleSection(QFrame):
    def __init__(self, title: str, count: int = 0, parent=None):
        super().__init__(parent)
        self.setObjectName("CollapsibleSection")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QFrame()
        header.setCursor(Qt.PointingHandCursor)
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(14, 6, 14, 6)
        h_layout.setSpacing(4)
        self._arrow = QLabel("▾")
        self._arrow.setFixedWidth(12)
        self._arrow.setStyleSheet("color:#6b7280; background:transparent; font-size:10px;")
        h_layout.addWidget(self._arrow)
        lbl = QLabel(f"{title}")
        lbl.setObjectName("SidebarSectionTitle")
        self._title_label = lbl
        h_layout.addWidget(lbl)
        if count:
            cnt = QLabel(f"({count})")
            cnt.setStyleSheet("color:#6b7280; background:transparent; font-size:11px;")
            h_layout.addWidget(cnt)
        h_layout.addStretch()
        layout.addWidget(header)
        header.mouseReleaseEvent = lambda e: self._toggle()

        self._body = QWidget()
        self._body_layout = QVBoxLayout(self._body)
        self._body_layout.setContentsMargins(0, 0, 0, 0)
        self._body_layout.setSpacing(2)
        layout.addWidget(self._body, 1)
        self._collapsed = False

    @property
    def body_layout(self):
        return self._body_layout

    def set_title(self, title: str) -> None:
        if hasattr(self, "_title_label"):
            self._title_label.setText(title)

    def _toggle(self):
        self._collapsed = not self._collapsed
        self._body.setVisible(not self._collapsed)
        self._arrow.setText("▸" if self._collapsed else "▾")


class TaskSidebar(QFrame):
    conversation_selected = Signal(int)
    new_task_requested = Signal()
    settings_requested = Signal()
    page_changed = Signal(str)
    sub_page_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("TaskSidebar")
        self.setFixedWidth(308)
        self._current_id: int | None = None
        self._cards: dict[int, TaskCard] = {}
        self._nav_items: dict[str, _NavItem] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QFrame()
        header.setObjectName("SidebarHeader")
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(18, 14, 14, 12)
        h_layout.setSpacing(6)
        brand_col = QVBoxLayout()
        brand_col.setSpacing(0)
        self._brand_name = QLabel(APP_NAME)
        self._brand_name.setObjectName("BrandName")
        version = QLabel(APP_VERSION)
        version.setObjectName("BrandVersion")
        brand_col.addWidget(self._brand_name)
        brand_col.addWidget(version)
        h_layout.addLayout(brand_col, 1)
        for icon, tip in [("🔍", "搜索"), ("🔽", "筛选")]:
            btn = QPushButton(icon)
            btn.setObjectName("SidebarIconButton")
            btn.setFixedSize(28, 28)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setToolTip(tip)
            if icon == "🔍":
                btn.clicked.connect(self._toggle_search)
            h_layout.addWidget(btn)
        layout.addWidget(header)

        self._search_wrapper = QFrame()
        sw = QVBoxLayout(self._search_wrapper)
        sw.setContentsMargins(12, 2, 12, 4)
        self._search = QLineEdit()
        self._search.setObjectName("SidebarSearch")
        self._search.setPlaceholderText("搜索任务…")
        self._search.setFixedHeight(34)
        self._search.textChanged.connect(self._on_search)
        sw.addWidget(self._search)
        self._search_wrapper.setVisible(False)
        layout.addWidget(self._search_wrapper)

        new_wrap = QFrame()
        nw = QVBoxLayout(new_wrap)
        nw.setContentsMargins(14, 8, 14, 8)
        new_btn = QPushButton("＋  新建任务")
        new_btn.setObjectName("NewTaskButton")
        new_btn.setCursor(Qt.PointingHandCursor)
        new_btn.setFixedHeight(42)
        new_btn.clicked.connect(self.new_task_requested.emit)
        nw.addWidget(new_btn)
        layout.addWidget(new_wrap)

        nav = QFrame()
        nav.setObjectName("SidebarNav")
        nav_layout = QVBoxLayout(nav)
        nav_layout.setContentsMargins(8, 8, 8, 8)
        nav_layout.setSpacing(2)

        nav_defs = [
            ("💬", "助理", "assistant", None),
            ("📁", "项目", "project", None),
            ("👤", "专家", "expert", [("技能", "skills"), ("MCP", "mcp"), ("快捷启动", "connectors")]),
            ("🤖", "自动化", "automation", None),
            ("📚", "更多", "more", [("资料库", "resources"), ("灵感", "inspiration")]),
        ]
        for icon, label, key, subs in nav_defs:
            item = _NavItem(icon, label, subs)
            item.clicked.connect(lambda k=key: self._on_nav_clicked(k))
            if subs:
                for child in item.findChildren(QPushButton, "NavSubLink"):
                    sub_key = child.property("sub_key")
                    child.clicked.connect(lambda _, sk=sub_key: self.sub_page_requested.emit(sk))
            self._nav_items[key] = item
            nav_layout.addWidget(item)

        self._nav_items["assistant"].set_selected(True)
        layout.addWidget(nav)

        self._task_section = _CollapsibleSection("任务", 0)
        task_body = self._task_section.body_layout

        task_tools = QFrame()
        task_tools.setObjectName("TaskListTools")
        tt_layout = QHBoxLayout(task_tools)
        tt_layout.setContentsMargins(10, 2, 10, 2)
        tt_layout.setSpacing(6)
        self._multi_btn = QPushButton("☑ 多选")
        self._multi_btn.setObjectName("TaskMultiSelectButton")
        self._multi_btn.setCheckable(True)
        self._multi_btn.setCursor(Qt.PointingHandCursor)
        self._multi_btn.setProperty("variant", "ghost")
        self._multi_btn.toggled.connect(self._toggle_multi_select)
        tt_layout.addWidget(self._multi_btn)
        tt_layout.addStretch()
        task_body.addWidget(task_tools)

        self._task_batch_bar = BatchActionBar()
        self._task_batch_bar.setVisible(False)
        self._task_batch_bar.select_all_clicked.connect(self._task_select_all)
        self._task_batch_bar.clear_clicked.connect(self._task_clear_selection)
        self._task_batch_bar.open_clicked.connect(self._task_batch_open)
        self._task_batch_bar.delete_clicked.connect(self._task_batch_delete)
        task_body.addWidget(self._task_batch_bar)

        scroll = QScrollArea()
        scroll.setObjectName("TaskListScroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._list_widget = QWidget()
        self._list_layout = QVBoxLayout(self._list_widget)
        self._list_layout.setContentsMargins(6, 0, 6, 0)
        self._list_layout.setSpacing(2)
        self._list_layout.addStretch()
        scroll.setWidget(self._list_widget)
        task_body.addWidget(scroll, 1)

        layout.addWidget(self._task_section, 1)

        bottom = QFrame()
        bottom.setObjectName("SidebarBottom")
        b_layout = QHBoxLayout(bottom)
        b_layout.setContentsMargins(12, 8, 12, 10)
        b_layout.setSpacing(8)
        self._avatar_btn = AvatarButton()
        self._avatar_btn.clicked_avatar.connect(self._show_profile)
        user_label = QLabel("🐷🐷Buddy 用户")
        user_label.setObjectName("SidebarUserName")
        self._user_label = user_label
        b_layout.addWidget(self._avatar_btn)
        b_layout.addWidget(user_label, 1)
        for icon, tip, slot in [
            ("🔔", "通知", None),
            ("⚙", "设置", self.settings_requested.emit),
        ]:
            btn = QPushButton(icon)
            btn.setObjectName("SidebarIconButton")
            btn.setFixedSize(28, 28)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setToolTip(tip)
            if slot:
                btn.clicked.connect(slot)
            b_layout.addWidget(btn)
        layout.addWidget(bottom)

        self._current_filter = "all"
        self._nav_defs = nav_defs
        self._new_task_btn = new_btn
        self._search_input = self._search
        self._task_section_ref = self._task_section
        self._multi_select_mode = False
        self.refresh()

    def set_user_name(self, name: str) -> None:
        if hasattr(self, "_user_label"):
            self._user_label.setText(name)
        avatar_path = get_setting("user_avatar_path", "")
        fallback = "🐷"
        self._avatar_btn.set_avatar(avatar_path, fallback)

    def refresh_avatar(self) -> None:
        user = get_setting("user_name", "").strip() or "🐷🐷Buddy 用户"
        self.set_user_name(user)

    def retranslate_ui(self) -> None:
        from ui.i18n import t

        if hasattr(self, "_brand_name"):
            self._brand_name.setText(APP_NAME)
        if hasattr(self, "_new_task_btn"):
            self._new_task_btn.setText(t("new_task"))
        if hasattr(self, "_search_input"):
            self._search_input.setPlaceholderText(t("search_tasks"))
        if hasattr(self, "_task_section_ref"):
            self._task_section_ref.set_title(t("task_section"))
        nav_keys = {
            "assistant": "nav_assistant",
            "project": "nav_project",
            "expert": "nav_expert",
            "automation": "nav_automation",
            "more": "nav_more",
        }
        for key, i18n_key in nav_keys.items():
            item = self._nav_items.get(key)
            if item and hasattr(item, "set_label"):
                item.set_label(t(i18n_key))

    def _on_nav_clicked(self, key: str):
        self.highlight_nav(key)
        self.page_changed.emit(key)

    def highlight_nav(self, key: str):
        for k, item in self._nav_items.items():
            item.set_selected(k == key)

    def _toggle_search(self):
        vis = not self._search_wrapper.isVisible()
        self._search_wrapper.setVisible(vis)
        if vis:
            self._search.setFocus()

    def refresh(self) -> None:
        keyword = self._search.text().strip() if self._search_wrapper.isVisible() else ""
        conversations = search_conversations(keyword) if keyword else list_conversations()

        self._cards.clear()
        while self._list_layout.count() > 1:
            item = self._list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for conv in conversations:
            card = TaskCard(conv)
            card.set_multi_select_mode(self._multi_select_mode)
            card.clicked.connect(self._on_card_clicked)
            card.delete_requested.connect(self._on_delete)
            card.check_changed.connect(self._on_task_check_changed)
            if self._current_id and conv["id"] == self._current_id:
                card.set_selected(True)
            self._cards[conv["id"]] = card
            self._list_layout.insertWidget(self._list_layout.count() - 1, card)
        self._update_task_batch_bar()

    def _toggle_multi_select(self, enabled: bool) -> None:
        self._multi_select_mode = enabled
        self._multi_btn.setText("完成" if enabled else "☑ 多选")
        self._task_batch_bar.setVisible(enabled)
        for card in self._cards.values():
            card.set_multi_select_mode(enabled)
        if not enabled:
            self._update_task_batch_bar()

    def _on_task_check_changed(self, _conv_id: int, _checked: bool) -> None:
        self._update_task_batch_bar()

    def _update_task_batch_bar(self) -> None:
        count = sum(1 for c in self._cards.values() if c.is_checked())
        self._task_batch_bar.set_count(count)

    def _task_select_all(self) -> None:
        for card in self._cards.values():
            card.set_checked(True)
        self._update_task_batch_bar()

    def _task_clear_selection(self) -> None:
        for card in self._cards.values():
            card.set_checked(False)
        self._update_task_batch_bar()

    def _task_checked_ids(self) -> list[int]:
        return [cid for cid, card in self._cards.items() if card.is_checked()]

    def _task_batch_open(self) -> None:
        ids = self._task_checked_ids()
        if not ids:
            return
        self._on_card_clicked(ids[0])

    def _task_batch_delete(self) -> None:
        ids = self._task_checked_ids()
        if not ids:
            return
        reply = QMessageBox.question(
            self,
            "确认删除",
            f"确定删除选中的 {len(ids)} 个任务吗？\n对话记录将无法恢复。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        for cid in ids:
            delete_conversation(cid)
            if self._current_id == cid:
                self._current_id = None
        self.refresh()
        if self._multi_select_mode:
            self._update_task_batch_bar()

    def select_conversation(self, conv_id: int) -> None:
        self._current_id = conv_id
        for cid, card in self._cards.items():
            card.set_selected(cid == conv_id)

    def _on_card_clicked(self, conv_id: int) -> None:
        self.select_conversation(conv_id)
        self.conversation_selected.emit(conv_id)

    def _on_delete(self, conv_id: int) -> None:
        delete_conversation(conv_id)
        if self._current_id == conv_id:
            self._current_id = None
        self.refresh()

    def _show_profile(self) -> None:
        from ui.widgets.user_profile_popup import UserProfilePopup
        popup = UserProfilePopup(self)
        popup.settings_requested.connect(self.settings_requested.emit)
        popup.avatar_changed.connect(self.refresh_avatar)
        popup.theme_changed.connect(self._on_theme_changed)
        pos = self._avatar_btn.mapToGlobal(self._avatar_btn.rect().topLeft())
        popup.move(pos.x(), pos.y() - popup.sizeHint().height() - 8)
        popup.show()

    def _on_search(self) -> None:
        self.refresh()

    def _on_theme_changed(self, key: str) -> None:
        from PySide6.QtWidgets import QApplication
        from core.settings_store import set_setting
        from core.settings_runtime import apply_app_settings

        theme = "浅色" if key == "light" else "深色"
        set_setting("theme", theme)
        app = QApplication.instance()
        window = self.window()
        if app and window:
            apply_app_settings(app, window)

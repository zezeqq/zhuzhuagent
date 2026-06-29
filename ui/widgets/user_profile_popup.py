from __future__ import annotations

import shutil
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog, QFrame, QHBoxLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout,
)

from core.settings_store import get_setting, set_setting
from ui.widgets.avatar_button import AvatarButton
from ui.theme import APP_VERSION
from utils.path_utils import data_dir


class UserProfilePopup(QFrame):
    settings_requested = Signal()
    theme_changed = Signal(str)
    avatar_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("UserProfilePopup")
        self.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint)
        self.setFixedWidth(260)
        self.setAttribute(Qt.WA_StyledBackground, True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        name_row = QHBoxLayout()
        name_row.setSpacing(10)
        self._avatar = AvatarButton()
        self._avatar.setFixedSize(46, 46)
        self._avatar.set_avatar(get_setting("user_avatar_path", ""), "🐷")
        self._avatar.clicked_avatar.connect(self._choose_avatar)
        name_row.addWidget(self._avatar)

        name_col = QVBoxLayout()
        name_col.setSpacing(2)
        name = QLabel(get_setting("user_name", "").strip() or "🐷🐷Buddy 用户")
        name.setStyleSheet("font-size:15px; font-weight:700; color:#F3F4F7; background:transparent;")
        name_col.addWidget(name)
        avatar_hint = QLabel("点击头像可更换")
        avatar_hint.setObjectName("MutedLabel")
        name_col.addWidget(avatar_hint)
        name_row.addLayout(name_col)
        name_row.addStretch()
        layout.addLayout(name_row)

        ver = QLabel(f"版本 {APP_VERSION}")
        ver.setObjectName("MutedLabel")
        layout.addWidget(ver)

        self._add_separator(layout)

        for icon, text, slot, close_after in [
            ("🖼", "更换头像", self._choose_avatar, False),
            ("↺", "恢复默认头像", self._reset_avatar, False),
            ("⚙", "设置", lambda: self.settings_requested.emit(), True),
            ("❓", "帮助与反馈", self._show_help, False),
            ("🔄", "检查更新", self._show_update_hint, False),
        ]:
            btn = QPushButton(f"  {icon}  {text}")
            btn.setObjectName("ProfileMenuItem")
            btn.setCursor(Qt.PointingHandCursor)
            if slot:
                btn.clicked.connect(slot)
                if close_after:
                    btn.clicked.connect(self.close)
            layout.addWidget(btn)

        self._add_separator(layout)

        theme_row = QHBoxLayout()
        theme_row.setSpacing(4)
        theme_label = QLabel("🎨  外观")
        theme_label.setStyleSheet("color:#9ca3af; background:transparent; font-size:13px;")
        theme_row.addWidget(theme_label)
        theme_row.addStretch()
        current_theme = get_setting("theme", "深色")
        for label, key in [("浅色", "light"), ("深色", "dark")]:
            btn = QPushButton(label)
            btn.setObjectName("ThemeToggle")
            btn.setCheckable(True)
            btn.setChecked((key == "dark" and current_theme != "浅色") or (key == "light" and current_theme == "浅色"))
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFixedSize(48, 26)
            btn.clicked.connect(lambda _, k=key: self._change_theme(k))
            theme_row.addWidget(btn)
        layout.addLayout(theme_row)

    def _add_separator(self, layout):
        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background-color:#374151;")
        layout.addWidget(sep)

    def _choose_avatar(self) -> None:
        parent_widget = self.parentWidget()
        parent = parent_widget.window() if parent_widget else self
        self.close()
        path, _ = QFileDialog.getOpenFileName(
            parent,
            "选择头像",
            "",
            "图片文件 (*.png *.jpg *.jpeg *.webp *.bmp);;所有文件 (*.*)",
        )
        if not path:
            return
        avatar_dir = data_dir() / "avatar"
        avatar_dir.mkdir(parents=True, exist_ok=True)
        suffix = Path(path).suffix.lower() or ".png"
        target = avatar_dir / f"user_avatar{suffix}"
        try:
            for old in avatar_dir.glob("user_avatar.*"):
                if old != target:
                    old.unlink(missing_ok=True)
            shutil.copy2(path, target)
        except OSError:
            return
        set_setting("user_avatar_path", str(target))
        self._avatar.set_avatar(str(target), "🐷")
        self.avatar_changed.emit()

    def _reset_avatar(self) -> None:
        set_setting("user_avatar_path", "")
        self._avatar.set_avatar("", "🐷")
        self.avatar_changed.emit()
        self.close()

    def _show_help(self) -> None:
        parent_widget = self.parentWidget()
        parent = parent_widget.window() if parent_widget else self
        self.close()
        QMessageBox.information(parent, "帮助与反馈", "可在 设置 → 帮助与反馈 中查看使用帮助和反馈入口。")

    def _show_update_hint(self) -> None:
        parent_widget = self.parentWidget()
        parent = parent_widget.window() if parent_widget else self
        self.close()
        QMessageBox.information(parent, "检查更新", "已启用启动时自动检查 Skill 更新。应用更新入口后续可接入发布源。")

    def _change_theme(self, key: str) -> None:
        self.theme_changed.emit(key)
        self.close()

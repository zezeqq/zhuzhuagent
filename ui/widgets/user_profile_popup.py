from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout,
)

from ui.theme import APP_VERSION


class UserProfilePopup(QFrame):
    settings_requested = Signal()
    theme_changed = Signal(str)

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
        name_row.setSpacing(6)
        name = QLabel("DNA 用户")
        name.setStyleSheet("font-size:15px; font-weight:700; color:white; background:transparent;")
        name_row.addWidget(name)
        name_row.addStretch()
        layout.addLayout(name_row)

        ver = QLabel(f"版本 {APP_VERSION}")
        ver.setObjectName("MutedLabel")
        layout.addWidget(ver)

        self._add_separator(layout)

        for icon, text, slot in [
            ("⚙", "设置", lambda: self.settings_requested.emit()),
            ("❓", "帮助与反馈", None),
            ("🔄", "检查更新", None),
        ]:
            btn = QPushButton(f"  {icon}  {text}")
            btn.setObjectName("ProfileMenuItem")
            btn.setCursor(Qt.PointingHandCursor)
            if slot:
                btn.clicked.connect(slot)
                btn.clicked.connect(self.close)
            layout.addWidget(btn)

        self._add_separator(layout)

        theme_row = QHBoxLayout()
        theme_row.setSpacing(4)
        theme_label = QLabel("🎨  外观")
        theme_label.setStyleSheet("color:#9ca3af; background:transparent; font-size:13px;")
        theme_row.addWidget(theme_label)
        theme_row.addStretch()
        for label, key in [("浅色", "light"), ("深色", "dark")]:
            btn = QPushButton(label)
            btn.setObjectName("ThemeToggle")
            btn.setCheckable(True)
            btn.setChecked(key == "dark")
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFixedSize(48, 26)
            btn.clicked.connect(lambda _, k=key: self.theme_changed.emit(k))
            theme_row.addWidget(btn)
        layout.addLayout(theme_row)

    def _add_separator(self, layout):
        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background-color:#374151;")
        layout.addWidget(sep)

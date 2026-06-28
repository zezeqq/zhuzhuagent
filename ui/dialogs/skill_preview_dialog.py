"""Skill 安装前预览对话框。"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QFrame, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout,
)

from agent_runtime.skill_installer import describe_github_install_compat


class SkillPreviewDialog(QDialog):
    install_requested = Signal(dict)

    def __init__(self, skill: dict, *, installed: bool = False, parent=None):
        super().__init__(parent)
        self._skill = skill
        self._installed = installed
        self.setObjectName("BuddyMessageDialog")
        self.setWindowTitle(f"Skill 预览 — {skill.get('display') or skill.get('name')}")
        self.setMinimumSize(560, 480)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        card = QFrame()
        card.setObjectName("BuddyMessageCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(10)

        title = QLabel(skill.get("display") or skill.get("name", ""))
        title.setObjectName("BuddyMessageTitle")
        layout.addWidget(title)

        meta_parts = []
        if skill.get("category"):
            meta_parts.append(skill["category"])
        if skill.get("skill_type"):
            meta_parts.append(skill["skill_type"])
        tags = skill.get("tags") or []
        if tags:
            meta_parts.append("标签: " + ", ".join(str(t) for t in tags[:8]))
        if skill.get("discovered"):
            meta_parts.append("联网发现")
        if skill.get("stars"):
            meta_parts.append(f"⭐ {skill['stars']}")
        meta = QLabel(" · ".join(meta_parts))
        meta.setObjectName("MutedLabel")
        meta.setWordWrap(True)
        layout.addWidget(meta)

        desc = QLabel(skill.get("desc", ""))
        desc.setWordWrap(True)
        layout.addWidget(desc)

        if skill.get("discovered") or skill.get("trending") or skill.get("install_url"):
            compat = QLabel(describe_github_install_compat(skill.get("source_url") or skill.get("install_url") or ""))
            compat.setObjectName("MutedLabel")
            compat.setWordWrap(True)
            compat.setStyleSheet("padding:8px; background:rgba(59,130,246,0.08); border-radius:6px;")
            layout.addWidget(compat)

        mcp = skill.get("recommended_mcp") or []
        if mcp:
            layout.addWidget(QLabel("推荐 MCP：" + ", ".join(str(x) for x in mcp)))

        hint = QLabel("以下内容将注入 Craft/Plan 对话的 Agent 系统提示（安装后生效）：")
        hint.setObjectName("MutedLabel")
        layout.addWidget(hint)

        body = QPlainTextEdit()
        body.setReadOnly(True)
        body.setPlainText((skill.get("skill_md") or skill.get("desc") or "").strip())
        body.setObjectName("PreviewText")
        layout.addWidget(body, 1)

        if skill.get("source_url"):
            src = QLabel(f"来源：{skill['source_url']}")
            src.setObjectName("MutedLabel")
            src.setWordWrap(True)
            src.setTextInteractionFlags(Qt.TextSelectableByMouse)
            layout.addWidget(src)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        close_btn = QPushButton("关闭")
        close_btn.setProperty("variant", "ghost")
        close_btn.clicked.connect(self.reject)
        btn_row.addWidget(close_btn)
        if not installed:
            install_btn = QPushButton("安装并装配")
            install_btn.setProperty("variant", "primary")
            install_btn.clicked.connect(self._on_install)
            btn_row.addWidget(install_btn)
        else:
            ok = QLabel("✓ 已安装")
            ok.setStyleSheet("color:#22c55e; font-weight:600;")
            btn_row.addWidget(ok)
        layout.addLayout(btn_row)

        root.addWidget(card)

    def _on_install(self):
        self.install_requested.emit(self._skill)
        self.accept()

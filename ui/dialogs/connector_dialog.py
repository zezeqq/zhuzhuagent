from __future__ import annotations

import json

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from agent_runtime.software_connector import launch_software
from core.settings_store import get_setting, set_setting
from db.database import query_all


class ConnectorDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Quick Launch & MCP")
        self.setMinimumSize(720, 520)
        self.setObjectName("SettingsDialog")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QLabel("Quick Launch & MCP")
        header.setObjectName("SettingsSection")
        header.setContentsMargins(24, 20, 24, 12)
        root.addWidget(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 8, 24, 24)
        layout.setSpacing(20)

        layout.addWidget(self._section("Configured apps"))
        self._sw_container = QVBoxLayout()
        self._sw_container.setSpacing(6)
        layout.addLayout(self._sw_container)
        self._refresh_software()

        layout.addWidget(self._section("MCP Servers"))
        mcp_hint = QLabel(
            "MCP connects external tool servers to the Agent (Craft/Plan). "
            "Configure JSON, test connection, then use mcp__ tools in chat."
        )
        mcp_hint.setObjectName("MutedLabel")
        mcp_hint.setWordWrap(True)
        layout.addWidget(mcp_hint)
        mcp_open = QPushButton("Open MCP configuration…")
        mcp_open.setProperty("variant", "primary")
        mcp_open.setFixedWidth(220)
        mcp_open.clicked.connect(self._open_mcp)
        layout.addWidget(mcp_open)

        layout.addWidget(self._section("Custom launch items"))
        custom_hint = QLabel("Add a custom command-line launcher (name + command).")
        custom_hint.setObjectName("MutedLabel")
        custom_hint.setWordWrap(True)
        layout.addWidget(custom_hint)

        form = QFormLayout()
        form.setSpacing(8)
        self._custom_name = QLineEdit()
        self._custom_name.setPlaceholderText("Display name")
        self._custom_cmd = QLineEdit()
        self._custom_cmd.setPlaceholderText("e.g. python -m my_server")
        form.addRow("Name", self._custom_name)
        form.addRow("Command", self._custom_cmd)
        layout.addLayout(form)

        add_custom = QPushButton("Add launch item")
        add_custom.setProperty("variant", "secondary")
        add_custom.setFixedWidth(160)
        add_custom.clicked.connect(self._add_custom_connector)
        layout.addWidget(add_custom)

        layout.addStretch()
        scroll.setWidget(content)
        root.addWidget(scroll, 1)

    @staticmethod
    def _section(title: str) -> QLabel:
        label = QLabel(title)
        label.setObjectName("SettingsSection")
        return label

    def _open_mcp(self) -> None:
        from ui.dialogs.mcp_dialog import MCPDialog
        MCPDialog(self).exec()

    def _refresh_software(self) -> None:
        while self._sw_container.count():
            item = self._sw_container.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        tools = query_all("SELECT * FROM software_tools WHERE enabled=1")
        if not tools:
            empty = QLabel("No launch items yet. Add them under Expert → Quick Launch.")
            empty.setObjectName("MutedLabel")
            self._sw_container.addWidget(empty)
            return

        for sw in tools:
            card = QWidget()
            card.setObjectName("ConnectorCard")
            card.setFixedHeight(48)
            row = QHBoxLayout(card)
            row.setContentsMargins(12, 6, 12, 6)
            row.setSpacing(10)

            is_connected = bool(sw.get("executable_path"))
            dot = QLabel("●")
            dot.setObjectName("StatusDot")
            dot.setProperty("status", "connected" if is_connected else "disconnected")
            dot.setFixedWidth(14)
            row.addWidget(dot)

            name = QLabel(sw.get("software_name", ""))
            name.setMinimumWidth(120)
            row.addWidget(name)

            path_label = QLabel(sw.get("executable_path", ""))
            path_label.setObjectName("MutedLabel")
            row.addWidget(path_label, 1)

            launch_btn = QPushButton("Launch")
            launch_btn.setProperty("variant", "pill")
            launch_btn.setFixedWidth(64)
            sid = sw["id"]
            launch_btn.clicked.connect(lambda checked=False, _id=sid: self._do_launch(_id))
            row.addWidget(launch_btn)

            self._sw_container.addWidget(card)

    def _do_launch(self, software_id: int) -> None:
        try:
            launch_software(software_id)
        except Exception:
            pass

    def _add_custom_connector(self) -> None:
        name = self._custom_name.text().strip()
        cmd = self._custom_cmd.text().strip()
        if not name or not cmd:
            return
        existing = get_setting("custom_connectors", "[]")
        try:
            connectors = json.loads(existing)
        except (json.JSONDecodeError, TypeError):
            connectors = []
        connectors.append({"name": name, "command": cmd})
        set_setting("custom_connectors", json.dumps(connectors, ensure_ascii=False))
        self._custom_name.clear()
        self._custom_cmd.clear()

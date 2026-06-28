"""MCP server configuration — presets gallery + custom servers + advanced JSON."""

from __future__ import annotations

import json
import re
import threading

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QFileDialog, QFormLayout, QFrame, QHBoxLayout, QLabel,
    QLineEdit, QMessageBox, QPlainTextEdit, QPushButton, QScrollArea, QTabWidget,
    QVBoxLayout, QWidget,
)

from agent_runtime.mcp_client import (
    load_mcp_config,
    mcp_manager,
    refresh_mcp_tools,
    save_mcp_config,
)
from agent_runtime.mcp_presets import (
    build_entry_from_preset,
    catalog_preset_ids,
    extract_field_values_from_entry,
    load_preset_catalog,
    merge_config_with_presets,
    resolve_placeholders,
)

_SERVER_NAME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_-]{0,31}$")


class _PresetCard(QFrame):
    def __init__(self, preset: dict, entry: dict | None = None, parent=None):
        super().__init__(parent)
        self.setObjectName("ActionCard")
        self._preset = preset
        self._field_widgets: dict[str, QLineEdit] = {}

        entry = entry or {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        top = QHBoxLayout()
        title = QLabel(preset.get("name", preset.get("id", "")))
        title.setObjectName("CardTitle")
        top.addWidget(title)
        cat = QLabel(preset.get("category", ""))
        cat.setObjectName("MutedLabel")
        cat.setStyleSheet("font-size:11px;")
        top.addWidget(cat)
        top.addStretch()
        self._enabled = QCheckBox("Enabled")
        self._enabled.setChecked(bool(entry.get("enabled", preset.get("default_enabled"))))
        top.addWidget(self._enabled)
        layout.addLayout(top)

        desc = QLabel(preset.get("description", ""))
        desc.setObjectName("MutedLabel")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        req = preset.get("requires") or []
        if req:
            req_lbl = QLabel("Requires: " + ", ".join(req))
            req_lbl.setObjectName("MutedLabel")
            req_lbl.setStyleSheet("font-size:11px; color:#f59e0b;")
            layout.addWidget(req_lbl)

        field_values = extract_field_values_from_entry(preset, entry)
        for field in preset.get("fields") or []:
            kind = field.get("kind", "")
            label = field.get("label", "")
            if kind in ("path", "secret"):
                row = QHBoxLayout()
                row.addWidget(QLabel(label))
                edit = QLineEdit()
                if kind == "secret":
                    edit.setEchoMode(QLineEdit.Password)
                    key = f"env:{field.get('env_key', '')}"
                    edit.setPlaceholderText(field.get("placeholder", ""))
                else:
                    key = f"arg:{field.get('arg_index', -1)}"
                    edit.setPlaceholderText(resolve_placeholders(str(field.get("default", ""))))
                edit.setText(field_values.get(key, ""))
                self._field_widgets[key] = edit
                row.addWidget(edit, 1)
                if kind == "path" and field.get("browse"):
                    browse = QPushButton("…")
                    browse.setFixedWidth(32)
                    browse.setProperty("variant", "ghost")
                    browse.clicked.connect(lambda _, e=edit, b=field.get("browse"): self._browse(e, b))
                    row.addWidget(browse)
                layout.addLayout(row)

    @property
    def preset_id(self) -> str:
        return str(self._preset.get("id", ""))

    def _browse(self, edit: QLineEdit, browse_type: str) -> None:
        if browse_type == "dir":
            path = QFileDialog.getExistingDirectory(self, "Select directory")
        else:
            path, _ = QFileDialog.getOpenFileName(self, "Select file")
        if path:
            edit.setText(path)

    def to_entry(self) -> dict:
        field_values = {k: w.text().strip() for k, w in self._field_widgets.items()}
        return build_entry_from_preset(
            self._preset,
            enabled=self._enabled.isChecked(),
            field_values=field_values,
        )


class _CustomServerCard(QFrame):
    def __init__(self, name: str = "", entry: dict | None = None, parent=None):
        super().__init__(parent)
        self.setObjectName("SettingsListCard")
        entry = entry or {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        top = QHBoxLayout()
        self._enabled = QCheckBox("Enabled")
        self._enabled.setChecked(bool(entry.get("enabled", True)))
        top.addWidget(self._enabled)
        top.addStretch()
        self._remove_btn = QPushButton("Remove")
        self._remove_btn.setProperty("variant", "ghost")
        self._remove_btn.setStyleSheet("color:#ef4444;")
        top.addWidget(self._remove_btn)
        layout.addLayout(top)

        form = QFormLayout()
        form.setSpacing(6)
        self._name = QLineEdit(name)
        self._name.setPlaceholderText("my_server (letters, numbers, underscore)")
        form.addRow("Server ID", self._name)

        self._command = QLineEdit(entry.get("command", ""))
        self._command.setPlaceholderText("npx / uvx / python")
        form.addRow("Command", self._command)

        self._args = QLineEdit(" ".join(str(a) for a in (entry.get("args") or [])))
        self._args.setPlaceholderText("-y @scope/package arg1 arg2")
        form.addRow("Args", self._args)

        self._url = QLineEdit(entry.get("url", ""))
        self._url.setPlaceholderText("Optional remote URL (leave empty for stdio)")
        form.addRow("URL", self._url)

        self._transport = QLineEdit(entry.get("transport", "sse"))
        self._transport.setPlaceholderText("sse or streamable-http")
        form.addRow("Transport", self._transport)

        self._env = QPlainTextEdit()
        env_lines = []
        for k, v in (entry.get("env") or {}).items():
            env_lines.append(f"{k}={v}")
        self._env.setPlainText("\n".join(env_lines))
        self._env.setFixedHeight(56)
        self._env.setPlaceholderText("KEY=value (one per line)")
        form.addRow("Env", self._env)

        layout.addLayout(form)

    def server_name(self) -> str:
        return self._name.text().strip()

    def to_entry(self) -> dict | None:
        name = self.server_name()
        if not name:
            return None
        if not _SERVER_NAME_RE.match(name):
            return None
        args = [a for a in self._args.text().strip().split() if a]
        env: dict[str, str] = {}
        for line in self._env.toPlainText().splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
        entry: dict = {
            "_custom": True,
            "enabled": self._enabled.isChecked(),
            "command": self._command.text().strip(),
            "args": args,
            "env": env,
        }
        url = self._url.text().strip()
        if url:
            entry["url"] = url
            entry["transport"] = self._transport.text().strip() or "sse"
        return entry


class MCPDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("MCP Servers")
        self.setObjectName("SettingsDialog")
        self.setMinimumSize(860, 620)

        self._preset_cards: list[_PresetCard] = []
        self._custom_cards: list[_CustomServerCard] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)

        hint = QLabel(
            "Recommended MCP servers are pre-configured below. Enable what you need, fill API keys, "
            "then Test & Save. Add your own servers under the Custom tab."
        )
        hint.setObjectName("MutedLabel")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self._status = QLabel("")
        self._status.setObjectName("MutedLabel")
        self._status.setWordWrap(True)
        layout.addWidget(self._status)

        self._tabs = QTabWidget()
        self._tabs.addTab(self._build_presets_tab(), "Recommended")
        self._tabs.addTab(self._build_custom_tab(), "Custom")
        self._tabs.addTab(self._build_json_tab(), "Advanced JSON")
        self._tabs.currentChanged.connect(self._on_tab_changed)
        self._last_tab = 0
        layout.addWidget(self._tabs, 1)

        btn_row = QHBoxLayout()
        test_btn = QPushButton("Test & reload")
        test_btn.setProperty("variant", "secondary")
        test_btn.clicked.connect(self._test_reload)
        btn_row.addWidget(test_btn)
        btn_row.addStretch()
        cancel = QPushButton("Cancel")
        cancel.setProperty("variant", "ghost")
        cancel.clicked.connect(self.reject)
        btn_row.addWidget(cancel)
        save = QPushButton("Save")
        save.setProperty("variant", "primary")
        save.clicked.connect(self._save)
        btn_row.addWidget(save)
        layout.addLayout(btn_row)

        self._load_from_settings()
        self._refresh_status()

    def _build_presets_tab(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        inner = QWidget()
        self._presets_layout = QVBoxLayout(inner)
        self._presets_layout.setContentsMargins(4, 4, 4, 4)
        self._presets_layout.setSpacing(10)
        self._presets_layout.addStretch()
        scroll.setWidget(inner)
        return scroll

    def _build_custom_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(8)

        hint = QLabel(
            "Add any MCP server by command (stdio) or URL (SSE / streamable-http). "
            "Server ID becomes the mcp__ID__tool prefix in Craft/Plan mode."
        )
        hint.setObjectName("MutedLabel")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        add_btn = QPushButton("+ Add custom server")
        add_btn.setProperty("variant", "primary")
        add_btn.setFixedWidth(180)
        add_btn.clicked.connect(lambda: self._add_custom_card())
        layout.addWidget(add_btn)

        custom_scroll = QScrollArea()
        custom_scroll.setWidgetResizable(True)
        custom_scroll.setFrameShape(QScrollArea.NoFrame)
        self._custom_container = QWidget()
        self._custom_layout = QVBoxLayout(self._custom_container)
        self._custom_layout.setContentsMargins(0, 0, 0, 0)
        self._custom_layout.setSpacing(10)
        self._custom_layout.addStretch()
        custom_scroll.setWidget(self._custom_container)
        layout.addWidget(custom_scroll, 1)
        return page

    def _build_json_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 4, 4, 4)
        note = QLabel("Power users: edit raw JSON. Switching back from this tab applies changes to Recommended/Custom.")
        note.setObjectName("MutedLabel")
        note.setWordWrap(True)
        layout.addWidget(note)
        self._json_editor = QPlainTextEdit()
        self._json_editor.setObjectName("LogViewer")
        layout.addWidget(self._json_editor, 1)
        return page

    def _clear_layout(self, layout: QVBoxLayout, keep_stretch: bool = True) -> None:
        while layout.count() > (1 if keep_stretch else 0):
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _load_from_settings(self) -> None:
        self._populate_from_config(load_mcp_config())

    def _populate_from_config(self, config: dict) -> None:
        servers = config.get("mcpServers") or {}
        preset_ids = catalog_preset_ids()

        self._preset_cards.clear()
        self._clear_layout(self._presets_layout)
        for preset in load_preset_catalog():
            pid = preset.get("id", "")
            card = _PresetCard(preset, servers.get(pid))
            self._preset_cards.append(card)
            self._presets_layout.insertWidget(self._presets_layout.count() - 1, card)

        self._custom_cards.clear()
        self._clear_layout(self._custom_layout)
        for name, entry in servers.items():
            if name in preset_ids:
                continue
            if isinstance(entry, dict):
                self._add_custom_card(name, entry)

        self._json_editor.setPlainText(json.dumps(config, ensure_ascii=False, indent=2))

    def _add_custom_card(self, name: str = "", entry: dict | None = None) -> None:
        card = _CustomServerCard(name, entry)
        card._remove_btn.clicked.connect(lambda: self._remove_custom_card(card))
        self._custom_cards.append(card)
        self._custom_layout.insertWidget(self._custom_layout.count() - 1, card)

    def _remove_custom_card(self, card: _CustomServerCard) -> None:
        if card in self._custom_cards:
            self._custom_cards.remove(card)
        card.deleteLater()

    def _collect_config(self) -> dict | None:
        if self._tabs.currentIndex() == 2:
            return self._parse_json_editor()

        servers: dict = {}
        for card in self._preset_cards:
            servers[card.preset_id] = card.to_entry()

        names_seen: set[str] = set()
        for card in self._custom_cards:
            entry = card.to_entry()
            name = card.server_name()
            if not entry:
                QMessageBox.warning(self, "Custom server", "Each custom server needs a valid ID (a-z, 0-9, _).")
                return None
            if not _SERVER_NAME_RE.match(name):
                QMessageBox.warning(
                    self, "Custom server",
                    f"Invalid server ID '{name}'. Use letters, numbers, underscore; start with a letter.",
                )
                return None
            if name in names_seen or name in catalog_preset_ids():
                QMessageBox.warning(self, "Custom server", f"Duplicate or reserved server ID: {name}")
                return None
            names_seen.add(name)
            servers[name] = entry

        return {"mcpServers": servers}

    def _parse_json_editor(self) -> dict | None:
        text = self._json_editor.toPlainText().strip()
        if not text:
            return {"mcpServers": {}}
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            QMessageBox.warning(self, "Invalid JSON", str(exc))
            return None
        if not isinstance(data, dict):
            QMessageBox.warning(self, "Invalid JSON", "Root must be an object.")
            return None
        if "mcpServers" not in data:
            data = {"mcpServers": data}
        return merge_config_with_presets(data)

    def _on_tab_changed(self, index: int) -> None:
        prev = self._last_tab
        self._last_tab = index
        if index == 2:
            cfg = self._collect_config()
            if cfg:
                self._json_editor.setPlainText(json.dumps(cfg, ensure_ascii=False, indent=2))
        elif prev == 2 and index in (0, 1):
            parsed = self._parse_json_editor()
            if parsed:
                self._populate_from_config(parsed)

    def _refresh_status(self) -> None:
        self._status.setText("\n".join(mcp_manager.get_status_lines()))

    def _apply_config(self, config: dict, *, show_message: bool = False) -> None:
        save_mcp_config(config)
        msg = refresh_mcp_tools()
        lines = mcp_manager.get_status_lines()
        self._status.setText(msg + "\n" + "\n".join(lines))
        if show_message:
            QMessageBox.information(self, "MCP", msg)

    def _test_reload(self) -> None:
        config = self._collect_config()
        if config is None:
            return
        self._status.setText("Connecting…")

        def work():
            save_mcp_config(config)
            msg = refresh_mcp_tools()
            lines = mcp_manager.get_status_lines()
            self._status.setText(msg + "\n" + "\n".join(lines))

        threading.Thread(target=work, daemon=True).start()

    def _save(self) -> None:
        config = self._collect_config()
        if config is None:
            return
        self._apply_config(config, show_message=True)
        self.accept()


def open_mcp_dialog(parent=None) -> None:
    MCPDialog(parent).exec()

"""Mainstream MCP preset catalog and config merge helpers."""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any

_PRESETS_CACHE: list[dict] | None = None

_PLACEHOLDER_RE = re.compile(r"\{\{(\w+)\}\}")


def _config_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "config"


def load_preset_catalog() -> list[dict]:
    global _PRESETS_CACHE
    if _PRESETS_CACHE is not None:
        return _PRESETS_CACHE
    path = _config_dir() / "mcp_presets.json"
    if not path.is_file():
        _PRESETS_CACHE = []
        return _PRESETS_CACHE
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        _PRESETS_CACHE = list(data.get("presets") or [])
    except Exception:
        _PRESETS_CACHE = []
    return _PRESETS_CACHE


def preset_by_id(preset_id: str) -> dict | None:
    for p in load_preset_catalog():
        if p.get("id") == preset_id:
            return p
    return None


def resolve_placeholders(value: str) -> str:
    from utils.path_utils import data_dir, exports_dir, uploads_dir

    mapping = {
        "EXPORTS_DIR": str(exports_dir()),
        "UPLOADS_DIR": str(uploads_dir()),
        "DATA_DIR": str(data_dir()),
        "SQLITE_PATH": str(data_dir() / "database.sqlite"),
        "PROJECT_ROOT": str(Path(__file__).resolve().parents[1]),
    }

    def repl(match: re.Match) -> str:
        key = match.group(1)
        return mapping.get(key, match.group(0))

    return _PLACEHOLDER_RE.sub(repl, value)


def _resolve_in_obj(obj: Any) -> Any:
    if isinstance(obj, str):
        return resolve_placeholders(obj)
    if isinstance(obj, list):
        return [_resolve_in_obj(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _resolve_in_obj(v) for k, v in obj.items()}
    return obj


def build_entry_from_preset(preset: dict, *, enabled: bool | None = None, field_values: dict | None = None) -> dict:
    """Build one mcpServers entry from a catalog preset + UI field overrides."""
    field_values = field_values or {}
    entry: dict[str, Any] = {
        "_preset": preset["id"],
        "enabled": preset.get("default_enabled", False) if enabled is None else enabled,
        "command": preset.get("command", ""),
        "args": copy.deepcopy(preset.get("args") or []),
        "env": copy.deepcopy(preset.get("env") or {}),
    }
    if preset.get("url"):
        entry["url"] = preset["url"]
    if preset.get("transport"):
        entry["transport"] = preset["transport"]
    if preset.get("cwd"):
        entry["cwd"] = preset["cwd"]

    for field in preset.get("fields") or []:
        kind = field.get("kind", "")
        if kind == "path" and field.get("target") == "arg":
            idx = int(field.get("arg_index", -1))
            key = f"arg:{field.get('arg_index', -1)}"
            val = field_values.get(key) or field.get("default") or ""
            val = resolve_placeholders(str(val))
            if entry["args"]:
                if idx < 0:
                    entry["args"][idx] = val
                elif 0 <= idx < len(entry["args"]):
                    entry["args"][idx] = val
        elif kind == "secret" and field.get("target") == "env":
            env_key = field.get("env_key", "")
            if env_key:
                entry["env"][env_key] = field_values.get(f"env:{env_key}", entry["env"].get(env_key, ""))

    entry = _resolve_in_obj(entry)
    return entry


def build_default_mcp_config() -> dict:
    servers: dict[str, Any] = {}
    for preset in load_preset_catalog():
        pid = preset.get("id")
        if not pid:
            continue
        servers[pid] = build_entry_from_preset(preset)
    return {"mcpServers": servers}


def extract_field_values_from_entry(preset: dict, entry: dict) -> dict[str, str]:
    values: dict[str, str] = {}
    for field in preset.get("fields") or []:
        if field.get("kind") == "path" and field.get("target") == "arg":
            idx = int(field.get("arg_index", -1))
            args = entry.get("args") or []
            if args:
                try:
                    values[f"arg:{idx}"] = str(args[idx])
                except IndexError:
                    pass
        elif field.get("kind") == "secret" and field.get("target") == "env":
            env_key = field.get("env_key", "")
            if env_key:
                values[f"env:{env_key}"] = str((entry.get("env") or {}).get(env_key, ""))
    return values


def merge_config_with_presets(saved: dict | None) -> dict:
    """Ensure all catalog presets exist; saved values override defaults."""
    base = build_default_mcp_config()
    servers = base.get("mcpServers", {})
    saved = saved or {}
    saved_servers = saved.get("mcpServers") or {}

    for pid, entry in saved_servers.items():
        if not isinstance(entry, dict):
            continue
        if entry.get("_custom"):
            servers[pid] = copy.deepcopy(entry)
            continue
        preset = preset_by_id(entry.get("_preset") or pid)
        if preset:
            merged = build_entry_from_preset(
                preset,
                enabled=entry.get("enabled", False),
                field_values=extract_field_values_from_entry(preset, entry),
            )
            merged["command"] = entry.get("command", merged.get("command", ""))
            merged["args"] = copy.deepcopy(entry.get("args", merged.get("args", [])))
            merged["env"] = {**merged.get("env", {}), **(entry.get("env") or {})}
            if entry.get("url"):
                merged["url"] = entry["url"]
            if entry.get("transport"):
                merged["transport"] = entry["transport"]
            if entry.get("cwd"):
                merged["cwd"] = entry["cwd"]
            servers[pid] = merged
        else:
            servers[pid] = copy.deepcopy(entry)

    return {"mcpServers": servers}


def strip_meta_keys(entry: dict) -> dict:
    """Remove UI-only keys before connecting."""
    out = copy.deepcopy(entry)
    out.pop("_preset", None)
    out.pop("_custom", None)
    return out


def catalog_preset_ids() -> set[str]:
    return {p["id"] for p in load_preset_catalog() if p.get("id")}


def list_custom_server_names(config: dict) -> list[str]:
    names: list[str] = []
    for name, entry in (config.get("mcpServers") or {}).items():
        if isinstance(entry, dict) and entry.get("_custom"):
            names.append(name)
    return names

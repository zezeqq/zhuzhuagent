"""启动时将 DeepSeek 模型升级为 V4 Pro 推荐配置。"""

from __future__ import annotations

from core.model_profiles import DEEPSEEK_V4_PRO_PROFILE, enrich_model_config
from db.database import execute, insert, query_all, query_one, update


def ensure_deepseek_v4_default() -> None:
    """若已有 DeepSeek 配置则升级为 V4 Pro；否则插入模板（保留 API Key）。"""
    rows = query_all(
        "SELECT * FROM models WHERE lower(provider_name) LIKE '%deepseek%' "
        "OR lower(model_name) LIKE '%deepseek%' ORDER BY is_default DESC, enabled DESC, id DESC"
    )
    profile = dict(DEEPSEEK_V4_PRO_PROFILE)
    has_default = bool(query_one("SELECT id FROM models WHERE is_default=1 AND enabled=1 LIMIT 1"))

    if rows:
        primary = rows[0]
        patch = {
            "provider_name": profile["provider_name"],
            "api_base": profile["api_base"],
            "model_name": profile["model_name"],
            "temperature": profile["temperature"],
            "max_tokens": profile["max_tokens"],
            "context_window": profile["context_window"],
            "thinking_enabled": profile["thinking_enabled"],
            "reasoning_effort": profile["reasoning_effort"],
            "remark": profile["remark"],
            "enabled": 1,
        }
        if not primary.get("api_key"):
            patch.pop("enabled", None)
        update("models", int(primary["id"]), patch)
        if primary.get("api_key"):
            try:
                from core.settings_store import get_setting, set_setting
                if get_setting("context_window_tokens", "128000") in ("128000", "", "128000.0"):
                    set_setting("context_window_tokens", "1000000", "string")
            except Exception:
                pass
        if not has_default:
            execute("UPDATE models SET is_default=0")
            execute("UPDATE models SET is_default=1 WHERE id=?", (primary["id"],))
        return

    data = enrich_model_config({
        **profile,
        "api_key": "",
        "enabled": 0,
        "is_default": 0 if has_default else 1,
    }) or profile
    insert("models", {
        "provider_name": data["provider_name"],
        "provider_type": data.get("provider_type", "openai_compatible"),
        "api_base": data["api_base"],
        "api_key": "",
        "model_name": data["model_name"],
        "temperature": data.get("temperature", 1.0),
        "max_tokens": data.get("max_tokens", 8192),
        "context_window": data.get("context_window", 1_000_000),
        "thinking_enabled": data.get("thinking_enabled", 1),
        "reasoning_effort": data.get("reasoning_effort", "max"),
        "enabled": 0,
        "is_default": 0 if has_default else 1,
        "remark": data.get("remark", profile["remark"]),
    })

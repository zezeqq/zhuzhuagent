"""已知模型的推荐参数（DeepSeek V4 Pro 等）。"""

from __future__ import annotations

from typing import Any

DEEPSEEK_V4_PRO_PROFILE: dict[str, Any] = {
    "provider_name": "DeepSeek",
    "provider_type": "openai_compatible",
    "api_base": "https://api.deepseek.com",
    "model_name": "deepseek-v4-pro",
    "temperature": 1.0,
    "max_tokens": 8192,
    "context_window": 1_000_000,
    "thinking_enabled": 1,
    "reasoning_effort": "max",
    "remark": "DeepSeek V4 Pro · 1M 上下文 · Agent Thinking（max）",
}


def _normalize_name(model_name: str) -> str:
    return (model_name or "").strip().lower()


def match_model_profile(model_name: str) -> dict[str, Any] | None:
    name = _normalize_name(model_name)
    if not name:
        return None
    if name in ("deepseek-v4-pro", "deepseek-v4-pro-max"):
        return dict(DEEPSEEK_V4_PRO_PROFILE)
    if name == "deepseek-v4-flash":
        p = dict(DEEPSEEK_V4_PRO_PROFILE)
        p.update({
            "model_name": "deepseek-v4-flash",
            "reasoning_effort": "high",
            "remark": "DeepSeek V4 Flash · 1M 上下文 · Thinking（high）",
        })
        return p
    if name in ("deepseek-chat", "deepseek-reasoner"):
        p = dict(DEEPSEEK_V4_PRO_PROFILE)
        p.update({
            "model_name": model_name,
            "reasoning_effort": "high",
            "remark": "DeepSeek 旧 ID（将路由至 V4），建议改为 deepseek-v4-pro",
        })
        return p
    return None


def is_deepseek_v4(model: dict | None) -> bool:
    name = _normalize_name((model or {}).get("model_name", ""))
    return (
        "deepseek-v4" in name
        or name in ("deepseek-chat", "deepseek-reasoner")
    )


def is_vision_capable(model: dict | None) -> bool:
    if not model:
        return True
    if model.get("supports_vision") is False:
        return False
    return not is_deepseek_v4(model)


def enrich_model_config(model: dict | None) -> dict | None:
    """合并模型档案默认值，保留用户已填写的 API Key 等。"""
    if not model:
        return model
    out = dict(model)
    profile = match_model_profile(out.get("model_name", ""))
    if profile:
        for key, value in profile.items():
            if key == "model_name":
                continue
            current = out.get(key)
            if current in (None, "", 0) and value not in (None, ""):
                out[key] = value
    if is_deepseek_v4(out):
        out.setdefault("thinking_enabled", 1)
        out.setdefault("reasoning_effort", "max")
        out.setdefault("context_window", 1_000_000)
        out.setdefault("max_tokens", 8192)
        out.setdefault("temperature", 1.0)
    return out


def resolve_tool_max_tokens(model: dict | None) -> int:
    mt = (model or {}).get("max_tokens") or 8192
    try:
        return max(1024, min(int(mt), 32_768))
    except (TypeError, ValueError):
        return 8192

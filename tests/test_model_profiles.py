"""DeepSeek V4 Pro 模型档案与 API 参数。"""

from __future__ import annotations

from core.model_client import ModelClient
from core.model_profiles import enrich_model_config, is_deepseek_v4, match_model_profile


def test_deepseek_v4_profile():
    profile = match_model_profile("deepseek-v4-pro")
    assert profile is not None
    assert profile["context_window"] == 1_000_000
    assert profile["reasoning_effort"] == "max"


def test_enrich_preserves_api_key():
    enriched = enrich_model_config({
        "model_name": "deepseek-v4-pro",
        "api_key": "sk-test",
        "api_base": "https://api.deepseek.com",
    })
    assert enriched["api_key"] == "sk-test"
    assert enriched["context_window"] == 1_000_000
    assert enriched["thinking_enabled"] == 1


def test_deepseek_payload_includes_thinking():
    payload = ModelClient._payload(
        [{"role": "user", "content": "hi"}],
        "deepseek-v4-pro",
        enrich_model_config({"model_name": "deepseek-v4-pro", "thinking_enabled": 1}),
        None,
        8192,
        False,
    )
    assert payload["thinking"] == {"type": "enabled"}
    assert payload["reasoning_effort"] == "max"
    assert "temperature" not in payload


def test_non_deepseek_keeps_temperature():
    payload = ModelClient._payload(
        [{"role": "user", "content": "hi"}],
        "gpt-4o-mini",
        {"model_name": "gpt-4o-mini", "temperature": 0.5},
        None,
        2000,
        False,
    )
    assert payload["temperature"] == 0.5
    assert "thinking" not in payload


def test_is_deepseek_v4_legacy_ids():
    assert is_deepseek_v4({"model_name": "deepseek-chat"})

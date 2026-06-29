"""工具权限与风险等级。"""

from __future__ import annotations

from agent_runtime.permissions import describe_risk, get_risk_level, requires_confirmation


def test_office_tools_are_low_risk():
    assert get_risk_level("office_word_create") == "low"
    assert get_risk_level("office_ppt_create") == "low"
    assert get_risk_level("library_search") == "low"


def test_high_risk_requires_confirmation(app_tmp, monkeypatch):
    monkeypatch.setattr("core.settings_store.get_bool", lambda key, default=False: {
        "confirm_dangerous_ops": True,
        "auto_execute_low_risk": False,
    }.get(key, default))
    assert requires_confirmation("file_delete") is True
    assert requires_confirmation("mouse_click") is True


def test_low_risk_office_no_confirmation(app_tmp, monkeypatch):
    monkeypatch.setattr("core.settings_store.get_bool", lambda key, default=False: {
        "confirm_dangerous_ops": True,
        "auto_execute_low_risk": False,
    }.get(key, default))
    assert requires_confirmation("office_word_create") is False
    assert requires_confirmation("library_search") is False


def test_full_access_skips_all_confirmation(app_tmp, monkeypatch):
    monkeypatch.setattr("core.settings_store.get_bool", lambda key, default=False: True)
    assert requires_confirmation("file_delete", full_access=True) is False


def test_auto_execute_low_risk(app_tmp, monkeypatch):
    monkeypatch.setattr("core.settings_store.get_bool", lambda key, default=False: {
        "confirm_dangerous_ops": True,
        "auto_execute_low_risk": True,
    }.get(key, default))
    assert requires_confirmation("shell_run") is False


def test_describe_risk_known_tools():
    assert "Word" in describe_risk("office_word_create")
    assert "资料库" in describe_risk("library_search")

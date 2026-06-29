"""Agent 三种模式（Ask / Plan / Craft）事件路由 — mock LLM，无网络。"""

from __future__ import annotations

from core.agent import Agent


class _StreamClient:
    def __init__(self, chunks: list[str]):
        self._chunks = chunks

    def stream_chat(self, messages, model):
        yield from self._chunks


def test_ask_mode_streams_reply(app_tmp, sample_project, monkeypatch):
    monkeypatch.setattr("core.agent.ModelClient", lambda: _StreamClient(["你好", "，这是回答"]))
    agent = Agent()
    events = list(
        agent.run(
            "什么是 BIM？",
            model={"model_name": "mock"},
            project=sample_project,
            mode="ask",
        )
    )
    types = [e["type"] for e in events]
    assert "token" in types
    assert "final_reply" in types
    assert "task_started" not in types
    assert "".join(e.get("content", "") for e in events if e["type"] == "token") == "你好，这是回答"


def test_plan_mode_emits_plan_ready(app_tmp, sample_project, monkeypatch):
    monkeypatch.setattr(
        "core.agent.ModelClient",
        lambda: _StreamClient(["# 任务计划\n\n1. 查资料\n2. 写文档"]),
    )
    agent = Agent()
    events = list(
        agent.run(
            "帮我规划技术方案",
            model={"model_name": "mock"},
            project=sample_project,
            mode="plan",
        )
    )
    assert any(e["type"] == "plan_ready" for e in events)
    plan_events = [e for e in events if e["type"] == "plan_ready"]
    assert "查资料" in plan_events[0]["content"]


def test_craft_mode_uses_llm_tool_loop(app_tmp, sample_project, monkeypatch):
    def _fake_tool_loop(self, **kwargs):
        yield {"type": "tool_call", "name": "office_ppt_create", "args": {}, "result": "ok"}
        yield {"type": "final_reply", "content": "PPT 已生成"}

    monkeypatch.setattr(Agent, "_run_tool_loop", _fake_tool_loop)
    agent = Agent()
    events = list(
        agent.run(
            "帮我生成投标 PPT",
            model={"model_name": "mock"},
            project=sample_project,
            mode="craft",
        )
    )
    types = [e["type"] for e in events]
    assert "task_started" in types
    assert "tool_call" in types
    assert "final_reply" in types
    assert "error" not in types


def test_ask_system_prompt_has_no_tools_suffix(app_tmp, sample_project):
    agent = Agent()
    system = agent._build_system_prompt("", "ask", sample_project)
    assert "不要调用任何工具" in system or "禁止" in system or "仅回答" in system

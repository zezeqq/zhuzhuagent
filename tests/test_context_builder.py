"""全量上下文与工具链还原。"""

from __future__ import annotations

import json

from core.context_builder import (
    build_agent_messages,
    estimate_messages_tokens,
    fit_messages_to_budget,
    history_rows_to_llm_messages,
)


def test_reconstruct_agent_step_with_tools():
    rows = [
        {"id": 1, "role": "user", "content": "查排名"},
        {"id": 2, "role": "agent_step", "content": json.dumps({
            "role": "assistant",
            "content": None,
            "reasoning_content": "需要搜索",
            "tool_calls": [{
                "id": "call_1",
                "type": "function",
                "function": {"name": "web_search", "arguments": '{"query":"x"}'},
            }],
        })},
        {"id": 3, "role": "tool_call", "content": json.dumps({
            "id": "call_1", "name": "web_search", "args": {"query": "x"}, "result": "ok",
        })},
    ]
    msgs = history_rows_to_llm_messages(rows)
    assert msgs[1]["reasoning_content"] == "需要搜索"
    assert msgs[2]["role"] == "tool"


def test_reconstruct_tool_round():
    rows = [
        {"id": 1, "role": "user", "content": "查 LMSYS 排名"},
        {"id": 2, "role": "assistant", "content": "我先搜索一下。"},
        {"id": 3, "role": "tool_call", "content": json.dumps({
            "id": "call_1",
            "name": "web_search",
            "args": {"query": "LMSYS"},
            "result": "# 联网搜索\n\n1. Arena Leaderboard",
        })},
        {"id": 4, "role": "assistant", "content": "根据搜索结果，前三名是…"},
    ]
    msgs = history_rows_to_llm_messages(rows)
    assert msgs[0]["role"] == "user"
    assert msgs[1]["role"] == "assistant"
    assert msgs[1]["tool_calls"][0]["function"]["name"] == "web_search"
    assert msgs[2]["role"] == "tool"
    assert msgs[2]["tool_call_id"] == "call_1"
    assert "Arena Leaderboard" in msgs[2]["content"]
    assert msgs[3]["role"] == "assistant"
    assert "前三名" in msgs[3]["content"]


def test_exclude_duplicate_current_user():
    rows = [
        {"id": 1, "role": "assistant", "content": "好的"},
        {"id": 2, "role": "user", "content": "继续改第三段"},
    ]
    msgs = history_rows_to_llm_messages(
        rows,
        current_user_text="继续改第三段",
        exclude_duplicate_user=True,
    )
    assert len(msgs) == 1
    assert msgs[0]["content"] == "好的"


def test_build_agent_messages_appends_current_user():
    rows = [
        {"id": 1, "role": "user", "content": "你好"},
        {"id": 2, "role": "assistant", "content": "你好！"},
    ]
    msgs, history_end = build_agent_messages(
        system="sys",
        history_rows=rows,
        user_content="再问一句",
        current_user_text="再问一句",
        attachments=None,
        model={"context_window": 128000},
        encode_images=lambda paths: [],
        vision_supported=True,
    )
    assert msgs[0]["content"] == "sys"
    assert history_end == 3
    assert msgs[-1]["role"] == "user"
    assert msgs[-1]["content"] == "再问一句"
    assert sum(1 for m in msgs if m["role"] == "user") == 2


def test_fit_messages_keeps_recent_tools_full():
    long = "x" * 30_000
    messages = [
        {"role": "system", "content": "s"},
        {"role": "tool", "content": long},
        {"role": "user", "content": "最新问题"},
        {"role": "tool", "content": "short result"},
    ]
    fit_messages_to_budget(messages, 8_000, protect_from_index=3)
    assert len(messages[1]["content"]) < len(long)
    assert messages[3]["content"] == "short result"


def test_fit_only_when_over_budget():
    messages = [
        {"role": "system", "content": "s"},
        {"role": "user", "content": "短对话"},
        {"role": "assistant", "content": "回复"},
    ]
    before = estimate_messages_tokens(messages)
    fit_messages_to_budget(messages, 128_000, protect_from_index=2)
    assert estimate_messages_tokens(messages) == before

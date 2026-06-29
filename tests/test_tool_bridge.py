"""tool_bridge 别名与参数归一化。"""

from __future__ import annotations

from pathlib import Path

from agent_runtime.tool_bridge import (
    execute_plan_step,
    is_agent_step,
    normalize_tool_name,
)


def test_normalize_tool_aliases():
    assert normalize_tool_name("office.word.create") == "office_word_create"
    assert normalize_tool_name("office.ppt.create") == "office_ppt_create"
    assert normalize_tool_name("rag.search") == "library_search"


def test_is_agent_step():
    assert is_agent_step("agent.execute") is True
    assert is_agent_step("office.word.create") is False


def test_execute_plan_step_word_creates_file(app_tmp, sample_project):
    result = execute_plan_step(
        "office.word.create",
        {
            "title": "桥接测试",
            "sections": [["章节一", "正文内容"]],
            "output_name": "bridge_test.docx",
        },
        project_id=sample_project["id"],
    )
    path = Path(result)
    assert path.exists()
    assert path.suffix == ".docx"

"""TaskPlan 序列化与 agent_execute 包装。"""

from __future__ import annotations

from agent_runtime.task_state import TaskPlan, TaskStep


def test_task_plan_json_roundtrip():
    plan = TaskPlan(
        title="测试计划",
        task_type="generate_word",
        user_goal="写文档",
        steps=[TaskStep("生成 Word", "office.word.create", {"title": "T"}, "medium")],
        expected_artifacts=["docx"],
    )
    restored = TaskPlan.from_dict(plan.to_dict(), user_goal=plan.user_goal)
    assert restored.title == plan.title
    assert restored.task_type == plan.task_type
    assert restored.steps[0].tool == "office.word.create"
    assert restored.expected_artifacts == ["docx"]


def test_agent_execute_plan_without_context():
    plan = TaskPlan.agent_execute_plan("整理资料并写报告")
    assert plan.task_type == "agent_craft"
    assert plan.steps[0].tool == "agent.execute"
    assert plan.steps[0].input["goal"] == "整理资料并写报告"


def test_agent_execute_plan_with_context():
    plan = TaskPlan.agent_execute_plan("执行", plan_context="# 步骤\n1. 查库")
    assert plan.task_type == "plan_execute"
    assert "plan_context" in plan.steps[0].input

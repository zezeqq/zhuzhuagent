"""Executor 离线结构化步骤执行。"""

from __future__ import annotations

from pathlib import Path

from agent_runtime.executor import Executor
from agent_runtime.task_state import TaskPlan, TaskStep
from db.database import insert


def _make_task(plan: TaskPlan) -> int:
    return insert(
        "tasks",
        {
            "task_name": plan.title,
            "task_type": plan.task_type,
            "status": "running",
            "user_goal": plan.user_goal,
            "plan_json": plan.to_json(),
        },
    )


def test_executor_runs_excel_step(app_tmp, sample_project):
    plan = TaskPlan(
        title="测试 Excel 步骤",
        task_type="generate_excel",
        user_goal="生成清单",
        steps=[
            TaskStep(
                "生成 XLSX",
                "office.excel.create",
                {
                    "title": "测试表",
                    "headers": ["列A", "列B"],
                    "rows": [[1, "x"]],
                    "output_name": "executor_test.xlsx",
                },
                "medium",
            ),
        ],
    )
    task_id = _make_task(plan)
    events = list(
        Executor().run_plan_streaming(
            plan,
            task_id=task_id,
            model=None,
            project=sample_project,
        )
    )
    types = [e["type"] for e in events]
    assert "tool_call" in types
    assert "final_reply" in types
    tool_events = [e for e in events if e["type"] == "tool_call"]
    output = tool_events[0]["result"]
    assert Path(output).exists()


def test_executor_permission_denied(app_tmp, sample_project, monkeypatch):
    plan = TaskPlan(
        title="需确认步骤",
        task_type="custom",
        user_goal="删除文件",
        steps=[TaskStep("删除", "file_delete", {"path": "dummy.txt"}, "high")],
    )
    task_id = _make_task(plan)
    monkeypatch.setattr("agent_runtime.permissions.requires_confirmation", lambda *a, **k: True)
    events = list(
        Executor().run_plan_streaming(
            plan,
            task_id=task_id,
            model=None,
            project=sample_project,
            full_access=False,
            request_permission=lambda req: False,
        )
    )
    assert any(e["type"] == "error" for e in events)

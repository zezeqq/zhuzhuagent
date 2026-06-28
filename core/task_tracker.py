"""Agent 运行时的任务与步骤记录，供结果面板「变更」Tab 使用。"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from db.database import execute, insert, query_one


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def start_task(
    *,
    conversation_id: int | None,
    goal: str,
    task_type: str = "agent",
    plan_json: str = "",
) -> int:
    return insert("tasks", {
        "task_name": (goal[:80] or "Agent 任务"),
        "task_type": task_type,
        "status": "running",
        "risk_level": "low",
        "user_goal": goal,
        "plan_json": plan_json or "",
        "conversation_id": conversation_id,
        "detail": "",
    })


def log_tool_step(
    task_id: int,
    step_index: int,
    tool_name: str,
    args: dict[str, Any],
    result: str,
    *,
    status: str = "completed",
) -> None:
    args_json = json.dumps(args, ensure_ascii=False)
    out_json = json.dumps({"result": result[:4000]}, ensure_ascii=False)
    insert("task_steps", {
        "task_id": task_id,
        "step_index": step_index,
        "step_name": tool_name,
        "tool_name": tool_name,
        "input_json": args_json,
        "output_json": out_json,
        "status": status,
        "started_at": _now(),
        "completed_at": _now(),
    })
    execute(
        "UPDATE tasks SET current_step=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
        (step_index, task_id),
    )


def complete_task(task_id: int, *, status: str = "completed") -> None:
    execute(
        "UPDATE tasks SET status=?, completed_at=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
        (status, _now(), task_id),
    )


def latest_task_for_conversation(conversation_id: int) -> dict | None:
    return query_one(
        "SELECT * FROM tasks WHERE conversation_id=? ORDER BY id DESC LIMIT 1",
        (conversation_id,),
    )

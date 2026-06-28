from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from agent_runtime.permissions import requires_confirmation
from agent_runtime.planner import Planner
from agent_runtime.task_state import TaskPlan, TaskStep
from agent_runtime.tool_registry import registry
from artifacts.artifact_manager import register_artifact
from core.agent_context import current_project
from db.database import execute, insert, query_all, query_one


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class Executor:
    def create_and_run(
        self,
        goal: str,
        project: dict | None = None,
        conversation_id: int | None = None,
        step_start_callback: Callable[[int, str], None] | None = None,
        step_complete_callback: Callable[[int, str], None] | None = None,
        cancel_check: Callable[[], bool] | None = None,
    ) -> dict[str, Any]:
        project = project or current_project()
        plan = Planner().plan(goal, project)
        task_id = self._create_task(plan, project, conversation_id)
        return self._run_task(task_id, step_start_callback, step_complete_callback, cancel_check)

    def plan_only(self, goal: str, project: dict | None = None) -> TaskPlan:
        project = project or current_project()
        return Planner().plan(goal, project)

    def execute_plan(
        self,
        plan: TaskPlan,
        project: dict | None = None,
        conversation_id: int | None = None,
        step_start_callback: Callable[[int, str], None] | None = None,
        step_complete_callback: Callable[[int, str], None] | None = None,
        cancel_check: Callable[[], bool] | None = None,
    ) -> dict[str, Any]:
        task_id = self._create_task(plan, project, conversation_id)
        return self._run_task(task_id, step_start_callback, step_complete_callback, cancel_check)

    def _create_task(self, plan: TaskPlan, project: dict | None, conversation_id: int | None = None) -> int:
        data: dict[str, Any] = {
            "task_name": plan.title,
            "task_type": plan.task_type,
            "status": "planning",
            "risk_level": plan.risk_level,
            "user_goal": plan.user_goal,
            "plan_json": plan.to_json(),
            "detail": f"预期产物：{', '.join(plan.expected_artifacts)}",
        }
        if conversation_id:
            data["conversation_id"] = conversation_id
        task_id = insert("tasks", data)
        for index, step in enumerate(plan.steps, 1):
            insert("task_steps", {
                "task_id": task_id,
                "step_index": index,
                "step_name": step.name,
                "tool_name": step.tool,
                "input_json": json.dumps(step.input, ensure_ascii=False),
                "status": "pending",
            })
        return task_id

    def _run_task(
        self,
        task_id: int,
        step_start_callback: Callable[[int, str], None] | None = None,
        step_complete_callback: Callable[[int, str], None] | None = None,
        cancel_check: Callable[[], bool] | None = None,
    ) -> dict[str, Any]:
        task = query_one("SELECT * FROM tasks WHERE id=?", (task_id,))
        if not task:
            raise ValueError("任务不存在")
        steps = query_all(
            "SELECT * FROM task_steps WHERE task_id=? ORDER BY step_index", (task_id,)
        )
        artifacts: list[dict] = []
        execute(
            "UPDATE tasks SET status='running', updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (task_id,),
        )
        for step in steps:
            if cancel_check and cancel_check():
                execute(
                    "UPDATE tasks SET status='cancelled', updated_at=CURRENT_TIMESTAMP WHERE id=?",
                    (task_id,),
                )
                return {"task_id": task_id, "status": "cancelled", "artifacts": artifacts}

            step_index = step.get("step_index", 0)
            step_name = step.get("step_name", "")
            if step_start_callback:
                step_start_callback(step_index, step_name)

            execute(
                "UPDATE task_steps SET status='running', started_at=? WHERE id=?",
                (_now(), step["id"]),
            )
            try:
                tool = registry.get(step["tool_name"])
                if requires_confirmation(tool.name, tool.risk_level) and tool.risk_level == "high":
                    execute(
                        "UPDATE tasks SET status='waiting_confirmation' WHERE id=?",
                        (task_id,),
                    )
                    return {
                        "task_id": task_id,
                        "status": "waiting_confirmation",
                        "artifacts": artifacts,
                    }
                input_data = json.loads(step.get("input_json") or "{}")
                insert("tool_calls", {
                    "task_id": task_id,
                    "tool_name": tool.name,
                    "input_json": json.dumps(input_data, ensure_ascii=False),
                    "risk_level": tool.risk_level,
                    "status": "running",
                })
                result = tool.handler(**input_data)
                output = {"result": str(result)}
                if isinstance(result, (str, Path)):
                    path = Path(result)
                    if path.exists():
                        artifact_id = register_artifact(
                            path,
                            path.suffix.lower().lstrip("."),
                            task_id=task_id,
                            project_id=None,
                            description=f"由任务 {task_id} 生成",
                        )
                        artifacts.append({
                            "id": artifact_id,
                            "path": str(path),
                            "type": path.suffix.lower().lstrip("."),
                        })
                execute(
                    "UPDATE task_steps SET status='completed', output_json=?, completed_at=? WHERE id=?",
                    (json.dumps(output, ensure_ascii=False), _now(), step["id"]),
                )
                execute(
                    "UPDATE tool_calls SET status='completed', output_json=? WHERE task_id=? AND tool_name=? AND status='running'",
                    (json.dumps(output, ensure_ascii=False), task_id, tool.name),
                )
                if step_complete_callback:
                    step_complete_callback(step_index, str(result)[:200])
            except Exception as exc:
                error = str(exc)
                execute(
                    "UPDATE task_steps SET status='failed', error_message=?, completed_at=? WHERE id=?",
                    (error, _now(), step["id"]),
                )
                execute(
                    "UPDATE tasks SET status='failed', error_message=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                    (error, task_id),
                )
                if step_complete_callback:
                    step_complete_callback(step_index, f"失败: {error[:100]}")
                return {
                    "task_id": task_id,
                    "status": "failed",
                    "error": error,
                    "artifacts": artifacts,
                }
        execute(
            "UPDATE tasks SET status='completed', current_step=?, completed_at=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (len(steps), _now(), task_id),
        )
        return {"task_id": task_id, "status": "completed", "artifacts": artifacts}

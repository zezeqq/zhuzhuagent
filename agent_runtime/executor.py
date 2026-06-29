from __future__ import annotations

import json
from collections.abc import Callable, Generator
from datetime import datetime
from pathlib import Path
from typing import Any

from agent_runtime.permissions import describe_risk, requires_confirmation
from agent_runtime.planner import Planner
from agent_runtime.task_state import TaskPlan
from agent_runtime.tool_bridge import AGENT_EXECUTE_TOOL, execute_plan_step, is_agent_step, normalize_tool_name
from artifacts.artifact_manager import register_artifact
from core.agent_context import current_project
from core.task_tracker import complete_task, log_tool_step
from db.database import execute, insert, query_all, query_one


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class Executor:
    """结构化任务执行器：按 TaskPlan 逐步执行，agent.execute 步骤委托 Agent 工具循环。"""

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
        result: dict[str, Any] = {"task_id": task_id, "status": "failed", "artifacts": []}
        for event in self.run_plan_streaming(
            plan,
            task_id=task_id,
            model=None,
            project=project,
            conversation_id=conversation_id,
            cancel_check=cancel_check,
        ):
            if event.get("type") == "final_reply":
                result["status"] = "completed"
            elif event.get("type") == "error":
                result["status"] = "failed"
                result["error"] = event.get("content", "")
        return result

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
        result: dict[str, Any] = {"task_id": task_id, "status": "completed", "artifacts": []}
        for event in self.run_plan_streaming(
            plan,
            task_id=task_id,
            model=None,
            project=project,
            conversation_id=conversation_id,
            cancel_check=cancel_check,
        ):
            if event.get("type") == "error":
                result["status"] = "failed"
                result["error"] = event.get("content", "")
        return result

    def run_plan_streaming(
        self,
        plan: TaskPlan,
        *,
        task_id: int,
        model: dict | None,
        project: dict | None = None,
        conversation_id: int | None = None,
        expert_prompt: str = "",
        full_access: bool = False,
        max_rounds: int = 0,
        history: list[dict] | None = None,
        attachments: list[str] | None = None,
        referenced_files: list[str] | None = None,
        request_permission: Callable[[dict], bool] | None = None,
        active_skill_package: str = "",
        cancel_check: Callable[[], bool] | None = None,
        guidance_poll: Callable[[], list[str]] | None = None,
    ) -> Generator[dict[str, Any], None, None]:
        """按 TaskPlan 逐步执行，产出与 Agent.run 兼容的事件流。"""
        project = project or current_project()
        project_id = project.get("id") if project else None

        self._sync_task_metadata(task_id, plan, conversation_id)

        step_index = query_one(
            "SELECT COALESCE(MAX(step_index), 0) AS mx FROM task_steps WHERE task_id=?",
            (task_id,),
        )
        step_counter = int((step_index or {}).get("mx") or 0)

        structured_results: list[str] = []
        agent_emitted_reply = False

        for step in plan.steps:
            if cancel_check and cancel_check():
                complete_task(task_id, status="cancelled")
                yield {"type": "final_reply", "content": "任务已取消。"}
                return

            step_counter += 1
            yield {
                "type": "thinking",
                "content": f"**步骤 {step_counter}**：{step.name}",
            }

            if is_agent_step(step.tool):
                if not model:
                    msg = "该步骤需要 AI 模型，请在设置中配置模型。"
                    log_tool_step(
                        task_id, step_counter, AGENT_EXECUTE_TOOL, step.input, msg, status="failed",
                    )
                    yield {"type": "error", "content": msg}
                    return

                goal = str(step.input.get("goal") or plan.user_goal)
                plan_context = str(step.input.get("plan_context") or "")
                step_max = int(step.input.get("max_rounds") or max_rounds or 0)

                from core.agent import Agent

                agent = Agent()
                try:
                    for event in agent._run_tool_loop(
                        user_text=goal,
                        model=model,
                        project=project,
                        expert_prompt=expert_prompt,
                        mode="craft",
                        full_access=full_access,
                        max_rounds=step_max,
                        history=history,
                        attachments=attachments,
                        referenced_files=referenced_files,
                        request_permission=request_permission,
                        plan_context=plan_context,
                        task_id=task_id,
                        active_skill_package=active_skill_package,
                        guidance_poll=guidance_poll,
                    ):
                        if event.get("type") == "final_reply":
                            agent_emitted_reply = True
                        yield event
                except Exception as exc:
                    yield {"type": "error", "content": str(exc)}
                    return
                continue

            tool_name = normalize_tool_name(step.tool)
            if requires_confirmation(tool_name, full_access):
                approved = True
                if request_permission:
                    approved = request_permission({
                        "name": tool_name,
                        "args": step.input,
                        "risk": step.risk_level,
                    })
                if not approved:
                    msg = f"用户未批准执行 {describe_risk(tool_name)}。"
                    log_tool_step(task_id, step_counter, tool_name, step.input, msg, status="failed")
                    yield {"type": "tool_call", "name": tool_name, "args": step.input, "result": msg}
                    yield {"type": "error", "content": msg}
                    return

            try:
                result = execute_plan_step(
                    step.tool,
                    step.input,
                    task_id=task_id,
                    project_id=project_id,
                )
                structured_results.append(result)
                log_tool_step(task_id, step_counter, tool_name, step.input, result)
                self._maybe_register_artifact(task_id, project_id, step.tool, step.input, result)
                yield {"type": "tool_call", "name": tool_name, "args": step.input, "result": result}
            except Exception as exc:
                err = str(exc)
                log_tool_step(task_id, step_counter, tool_name, step.input, err, status="failed")
                complete_task(task_id, status="failed")
                yield {"type": "error", "content": err}
                return

        if structured_results and not agent_emitted_reply:
            summary = self._build_summary(plan, structured_results)
            for i in range(0, len(summary), 32):
                yield {"type": "token", "content": summary[i:i + 32]}
            yield {"type": "final_reply", "content": summary}
        elif structured_results and agent_emitted_reply:
            extra = "\n".join(f"• {r[:200]}" for r in structured_results)
            yield {"type": "thinking", "content": f"**结构化步骤结果**\n{extra}"}
        elif not agent_emitted_reply:
            yield {"type": "final_reply", "content": "任务已完成。"}

    @staticmethod
    def _build_summary(plan: TaskPlan, results: list[str]) -> str:
        lines = [f"✅ **{plan.title}** 已完成。", ""]
        if plan.expected_artifacts:
            lines.append(f"预期产物：{', '.join(plan.expected_artifacts)}")
            lines.append("")
        for idx, result in enumerate(results, 1):
            lines.append(f"{idx}. {result[:500]}")
        return "\n".join(lines)

    @staticmethod
    def _sync_task_metadata(task_id: int, plan: TaskPlan, conversation_id: int | None) -> None:
        detail = f"预期产物：{', '.join(plan.expected_artifacts)}" if plan.expected_artifacts else ""
        execute(
            """UPDATE tasks SET task_name=?, task_type=?, risk_level=?, user_goal=?,
               plan_json=?, detail=?, status='running', updated_at=CURRENT_TIMESTAMP
               WHERE id=?""",
            (
                plan.title,
                plan.task_type,
                plan.risk_level,
                plan.user_goal,
                plan.to_json(),
                detail,
                task_id,
            ),
        )
        if conversation_id:
            execute(
                "UPDATE tasks SET conversation_id=? WHERE id=? AND conversation_id IS NULL",
                (conversation_id, task_id),
            )

    @staticmethod
    def _maybe_register_artifact(
        task_id: int,
        project_id: int | None,
        tool_name: str,
        step_input: dict,
        result: str,
    ) -> None:
        for token in result.replace("\\", "/").split():
            if token.endswith((".docx", ".xlsx", ".pptx", ".pdf", ".py", ".md", ".txt")):
                path = Path(token.rstrip(".,;"))
                if path.exists():
                    register_artifact(
                        path,
                        path.suffix.lower().lstrip("."),
                        task_id=task_id,
                        project_id=project_id,
                        description=f"步骤工具 {tool_name} 生成",
                    )
                    return
        output_name = step_input.get("output_name") or step_input.get("filename")
        if output_name:
            from artifacts.artifact_manager import ensure_export_dir
            candidate = ensure_export_dir() / str(output_name)
            if candidate.exists():
                register_artifact(
                    candidate,
                    candidate.suffix.lower().lstrip("."),
                    task_id=task_id,
                    project_id=project_id,
                    description=f"步骤工具 {tool_name} 生成",
                )

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
        """Legacy synchronous runner（保留兼容）。"""
        task = query_one("SELECT * FROM tasks WHERE id=?", (task_id,))
        if not task:
            raise ValueError("任务不存在")
        plan_data = json.loads(task.get("plan_json") or "{}")
        plan = TaskPlan.from_dict(plan_data, user_goal=task.get("user_goal") or "")
        result: dict[str, Any] = {"task_id": task_id, "status": "completed", "artifacts": []}
        for event in self.run_plan_streaming(
            plan,
            task_id=task_id,
            model=None,
            project=current_project(),
            cancel_check=cancel_check,
        ):
            if event.get("type") == "error":
                result["status"] = "failed"
                result["error"] = event.get("content", "")
        return result

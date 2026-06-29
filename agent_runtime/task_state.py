from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass
class TaskStep:
    name: str
    tool: str
    input: dict[str, Any] = field(default_factory=dict)
    risk_level: str = "low"


@dataclass
class TaskPlan:
    title: str
    task_type: str
    user_goal: str
    risk_level: str = "low"
    requires_confirmation: bool = False
    steps: list[TaskStep] = field(default_factory=list)
    expected_artifacts: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "task_type": self.task_type,
            "user_goal": self.user_goal,
            "risk_level": self.risk_level,
            "requires_confirmation": self.requires_confirmation,
            "steps": [step.__dict__ for step in self.steps],
            "expected_artifacts": self.expected_artifacts,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    @classmethod
    def from_dict(cls, data: dict[str, Any], *, user_goal: str = "") -> TaskPlan:
        steps_raw = data.get("steps") or []
        steps: list[TaskStep] = []
        for item in steps_raw:
            if not isinstance(item, dict):
                continue
            steps.append(TaskStep(
                name=str(item.get("name") or item.get("step_name") or "步骤"),
                tool=str(item.get("tool") or item.get("tool_name") or "agent.execute"),
                input=dict(item.get("input") or item.get("input_json") or {}),
                risk_level=str(item.get("risk_level") or "low"),
            ))
        goal = user_goal or str(data.get("user_goal") or data.get("goal") or "")
        return cls(
            title=str(data.get("title") or "任务计划"),
            task_type=str(data.get("task_type") or "agent_craft"),
            user_goal=goal,
            risk_level=str(data.get("risk_level") or "low"),
            requires_confirmation=bool(data.get("requires_confirmation", False)),
            steps=steps,
            expected_artifacts=[str(x) for x in (data.get("expected_artifacts") or [])],
        )

    @classmethod
    def agent_execute_plan(cls, goal: str, *, plan_context: str = "", title: str = "智能执行") -> TaskPlan:
        payload: dict[str, Any] = {"goal": goal}
        if plan_context.strip():
            payload["plan_context"] = plan_context.strip()
        return cls(
            title=title,
            task_type="plan_execute" if plan_context.strip() else "agent_craft",
            user_goal=goal,
            risk_level="low",
            steps=[TaskStep("智能执行", "agent.execute", payload, "low")],
            expected_artifacts=[],
        )

    def uses_executor(self) -> bool:
        return bool(self.steps)

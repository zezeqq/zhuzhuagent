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

    def to_json(self) -> str:
        return json.dumps(
            {
                "title": self.title,
                "task_type": self.task_type,
                "user_goal": self.user_goal,
                "risk_level": self.risk_level,
                "requires_confirmation": self.requires_confirmation,
                "steps": [step.__dict__ for step in self.steps],
                "expected_artifacts": self.expected_artifacts,
            },
            ensure_ascii=False,
            indent=2,
        )

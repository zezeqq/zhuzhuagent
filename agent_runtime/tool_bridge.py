"""统一步骤工具调度：Planner/Executor 与 Agent tool_executor、ToolRegistry 之间的桥梁。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_runtime.tool_executor import execute_tool, tool_context
from agent_runtime.tool_registry import registry

AGENT_EXECUTE_TOOL = "agent.execute"

# Planner 可引用的工具名（含 registry 点号命名与 executor 下划线命名）
REGISTRY_TOOLS = frozenset({
    "office.word.create",
    "office.excel.create",
    "office.ppt.create",
    "code.python.create",
    "software.launch",
    "skill.install.url",
    "skill.install.market",
})

TOOL_ALIASES: dict[str, str] = {
    "office.word.create": "office_word_create",
    "office.excel.create": "office_excel_create",
    "office.ppt.create": "office_ppt_create",
    "office.pptx.create": "office_ppt_create",
    "code.python.create": "code_create",
    "software.launch": "software_launch",
    "skill.install.url": "skill_install",
    "skill.install.market": "skill_install",
    "rag.search": "library_search",
    "library.list": "library_list",
}


def normalize_tool_name(name: str) -> str:
    raw = (name or "").strip()
    return TOOL_ALIASES.get(raw, raw)


def is_agent_step(tool_name: str) -> bool:
    return normalize_tool_name(tool_name) == AGENT_EXECUTE_TOOL


def is_registry_tool(tool_name: str) -> bool:
    return (tool_name or "").strip() in REGISTRY_TOOLS


def known_plan_tool(tool_name: str) -> bool:
    name = (tool_name or "").strip()
    if is_agent_step(name):
        return True
    if is_registry_tool(name):
        return True
    return normalize_tool_name(name) in _executor_tool_names()


def _executor_tool_names() -> set[str]:
    from agent_runtime.tool_executor import _HANDLERS  # noqa: PLC0415
    return set(_HANDLERS.keys())


def _normalize_registry_args(tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
    data = dict(args or {})
    if tool_name == "office.word.create":
        sections = data.get("sections") or []
        fixed: list[tuple[str, str]] = []
        for item in sections:
            if isinstance(item, dict):
                fixed.append((str(item.get("heading", "")), str(item.get("body", ""))))
            elif isinstance(item, (list, tuple)) and len(item) >= 2:
                fixed.append((str(item[0]), str(item[1])))
        data["sections"] = fixed
        if "filename" in data and "output_name" not in data:
            data["output_name"] = data.pop("filename")
    elif tool_name == "office.excel.create":
        if "filename" in data and "output_name" not in data:
            data["output_name"] = data.pop("filename")
    elif tool_name == "office.ppt.create":
        slides = data.get("slides") or []
        fixed_slides: list[tuple[str, list[str]]] = []
        for item in slides:
            if isinstance(item, dict):
                fixed_slides.append((
                    str(item.get("slide_title", item.get("title", ""))),
                    [str(b) for b in (item.get("bullets") or [])],
                ))
            elif isinstance(item, (list, tuple)) and len(item) >= 2:
                bullets = item[1] if isinstance(item[1], list) else [str(item[1])]
                fixed_slides.append((str(item[0]), [str(b) for b in bullets]))
        data["slides"] = fixed_slides
        if "filename" in data and "output_name" not in data:
            data["output_name"] = data.pop("filename")
    elif tool_name == "code.python.create":
        if "output_name" not in data and "filename" in data:
            data["output_name"] = data.pop("filename")
    return data


def _normalize_executor_args(tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
    data = dict(args or {})
    name = normalize_tool_name(tool_name)
    if name in {"office_word_create", "office_excel_create", "office_ppt_create"}:
        if "output_name" in data and "filename" not in data:
            data["filename"] = data.pop("output_name")
        if name == "office_word_create":
            sections = data.get("sections") or []
            fixed: list[dict[str, str]] = []
            for item in sections:
                if isinstance(item, dict):
                    fixed.append({
                        "heading": str(item.get("heading", "")),
                        "body": str(item.get("body", "")),
                    })
                elif isinstance(item, (list, tuple)) and len(item) >= 2:
                    fixed.append({"heading": str(item[0]), "body": str(item[1])})
            data["sections"] = fixed
        elif name == "office_ppt_create":
            slides = data.get("slides") or []
            fixed: list[dict[str, Any]] = []
            for item in slides:
                if isinstance(item, dict):
                    fixed.append(item)
                elif isinstance(item, (list, tuple)) and len(item) >= 2:
                    bullets = item[1] if isinstance(item[1], list) else [str(item[1])]
                    fixed.append({"slide_title": str(item[0]), "bullets": [str(b) for b in bullets]})
            data["slides"] = fixed
    return data


def execute_plan_step(
    tool_name: str,
    args: dict[str, Any],
    *,
    task_id: int | None = None,
    project_id: int | None = None,
) -> str:
    """执行 Planner 步骤中的单个工具（不含 agent.execute）。"""
    raw = (tool_name or "").strip()
    if is_agent_step(raw):
        raise ValueError("agent.execute 须由 Executor 委托 Agent，不可直接调用")

    if is_registry_tool(raw):
        payload = _normalize_registry_args(raw, args)
        spec = registry.get(raw)
        result = spec.handler(**payload)
        if isinstance(result, Path):
            return str(result)
        return str(result)

    normalized = normalize_tool_name(raw)
    payload = _normalize_executor_args(raw, args)
    with tool_context(task_id=task_id, project_id=project_id):
        return execute_tool(normalized, payload)

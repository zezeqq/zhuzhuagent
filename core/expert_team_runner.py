"""专家团并行执行：团长拆解 → 成员并行分析 → 团长汇总。"""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable

from core.expert_catalog import all_merged_experts, build_expert_prompt, build_team_prompt
from core.model_client import ModelClient, ModelClientError

ProgressFn = Callable[[dict[str, Any]], None]


def _notify(cb: ProgressFn | None, event: dict[str, Any]) -> None:
    if cb:
        cb(event)


def _expert_map(custom_experts: list[dict] | None = None) -> dict[str, dict]:
    return {e["name"]: e for e in all_merged_experts(custom_experts) if e.get("name")}


def _assign_subtasks(
    team: dict,
    user_text: str,
    model: dict,
    experts: dict[str, dict],
    progress: ProgressFn | None = None,
) -> dict[str, str]:
    members = [m for m in (team.get("members") or []) if m]
    if not members:
        return {}

    member_lines = []
    for name in members:
        e = experts.get(name, {})
        member_lines.append(f"- {name}：{e.get('desc', '领域顾问')}")

    leader_system = (
        build_team_prompt(team, list(experts.values()))
        + "\n\n当前阶段：任务拆解。不要执行工具，只输出成员分工。"
    )
    user_msg = (
        f"用户任务：\n{user_text}\n\n"
        f"团队成员：\n" + "\n".join(member_lines) + "\n\n"
        "请为每位成员写一句明确的子任务（覆盖各自专业视角）。\n"
        "严格按以下格式输出，每行一位成员：\n"
        "【成员名】该成员负责的子任务\n"
    )
    client = ModelClient()
    try:
        raw = client.chat(
            [{"role": "system", "content": leader_system}, {"role": "user", "content": user_msg}],
            model,
            temperature=0.3,
            max_tokens=800,
        )
    except ModelClientError as exc:
        _notify(progress, {"type": "warning", "content": f"团长拆解失败，改用默认分工：{exc}"})
        raw = ""

    assignments: dict[str, str] = {}
    for line in raw.splitlines():
        line = line.strip()
        m = re.match(r"^【(.+?)】(.+)$", line)
        if m:
            assignments[m.group(1).strip()] = m.group(2).strip()

    for name in members:
        if name not in assignments:
            assignments[name] = f"从「{name}」专业视角分析并给出建议：{user_text}"

    _notify(progress, {
        "type": "team_plan",
        "content": "\n".join(f"· **{k}**：{v}" for k, v in assignments.items()),
        "assignments": assignments,
    })
    return assignments


def _run_member(
    member_name: str,
    subtask: str,
    user_text: str,
    experts: dict[str, dict],
    model: dict,
) -> tuple[str, str]:
    expert = experts.get(member_name) or {"name": member_name, "desc": ""}
    system = (
        build_expert_prompt(expert)
        + f"\n\n你正在以「{member_name}」身份参与专家团协作。"
        "只输出本专业视角的结构化结论（标题+要点），不要调用工具，不要重复用户原文。"
    )
    user_msg = (
        f"整体用户任务：\n{user_text}\n\n"
        f"分配给你的子任务：\n{subtask}\n\n"
        "请给出可直接被团长汇总的结论。"
    )
    client = ModelClient()
    try:
        content = client.chat(
            [{"role": "system", "content": system}, {"role": "user", "content": user_msg}],
            model,
            temperature=0.5,
            max_tokens=1800,
        )
    except ModelClientError as exc:
        content = f"（{member_name} 分析失败：{exc}）"
    return member_name, content.strip()


def _synthesize_team(
    team: dict,
    user_text: str,
    member_outputs: list[tuple[str, str]],
    model: dict,
    progress: ProgressFn | None = None,
) -> str:
    _notify(progress, {"type": "thinking", "content": f"团长「{team.get('name', '专家团')}」正在汇总各成员结论…"})

    blocks = []
    for name, text in member_outputs:
        blocks.append(f"### {name}\n{text}")

    leader_system = (
        build_team_prompt(team, list(_expert_map().values()))
        + "\n\n当前阶段：整合交付。根据各成员产出写一份完整、可执行的最终答复。"
    )
    user_msg = (
        f"用户原始任务：\n{user_text}\n\n"
        f"各成员产出：\n\n" + "\n\n---\n\n".join(blocks) + "\n\n"
        "请输出最终交付（含结论、步骤或建议，Markdown 格式）。"
    )
    client = ModelClient()
    return client.chat(
        [{"role": "system", "content": leader_system}, {"role": "user", "content": user_msg}],
        model,
        temperature=0.4,
        max_tokens=4096,
    )


def run_expert_team_parallel(
    team: dict,
    user_text: str,
    model: dict,
    *,
    custom_experts: list[dict] | None = None,
    progress: ProgressFn | None = None,
    max_workers: int = 4,
) -> str:
    """Run expert team: decompose → parallel members → synthesize."""
    if not (user_text or "").strip():
        raise ValueError("任务描述不能为空。")
    if not model:
        raise ValueError("专家团并行需要已配置的 AI 模型。")

    experts = _expert_map(custom_experts)
    members = [m for m in (team.get("members") or []) if m]
    if not members:
        raise ValueError("专家团未配置成员。")

    _notify(progress, {
        "type": "thinking",
        "content": f"专家团「{team.get('name', '')}」启动：团长拆解任务…",
    })
    assignments = _assign_subtasks(team, user_text, model, experts, progress)

    member_outputs: list[tuple[str, str]] = []
    workers = min(max_workers, max(1, len(members)))

    _notify(progress, {
        "type": "thinking",
        "content": f"正在并行调用 {len(members)} 位成员（最多 {workers} 路并发）…",
    })

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(
                _run_member, name, assignments.get(name, user_text), user_text, experts, model
            ): name
            for name in members
        }
        for fut in as_completed(futures):
            name = futures[fut]
            _notify(progress, {"type": "member_start", "member": name})
            try:
                member_name, content = fut.result()
            except Exception as exc:
                member_name, content = name, f"（执行异常：{exc}）"
            member_outputs.append((member_name, content))
            _notify(progress, {
                "type": "member_done",
                "member": member_name,
                "content": content,
            })

    member_outputs.sort(key=lambda x: members.index(x[0]) if x[0] in members else 999)

    final = _synthesize_team(team, user_text, member_outputs, model, progress)
    _notify(progress, {"type": "team_sections", "sections": member_outputs})
    return final

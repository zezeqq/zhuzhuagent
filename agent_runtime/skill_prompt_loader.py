"""Load Cursor-style SKILL.md instructions into the Agent system prompt."""

from __future__ import annotations

import json
from pathlib import Path

from db.database import query_all

_MAX_SKILL_CHARS = 3500
_MAX_TOTAL_CHARS = 14000


def _skill_md_path(install_path: Path, manifest: dict) -> Path | None:
    entry = (manifest.get("entry") or "").strip()
    if entry.lower().endswith(".md"):
        candidate = install_path / entry
        if candidate.is_file():
            return candidate
    default = install_path / "SKILL.md"
    if default.is_file():
        return default
    return None


def _fallback_from_manifest(manifest: dict) -> str:
    display = manifest.get("display_name") or manifest.get("name") or "Skill"
    desc = (manifest.get("description") or "").strip()
    if not desc:
        return ""
    return (
        f"# {display}\n\n"
        f"{desc}\n\n"
        f"## 何时使用\n\n当用户任务与「{display}」相关时，遵循以上说明执行。\n\n"
        f"## 执行方式\n\n使用 Agent 内置工具（file_write、office_*、shell_run、ui_click 等）完成。\n"
    )


def default_skill_md(display_name: str, description: str = "") -> str:
    desc = description.strip() or "在此描述该技能的用途和使用场景。"
    return (
        f"# {display_name}\n\n"
        f"{desc}\n\n"
        f"## 何时使用\n\n"
        f"当用户请求与「{display_name}」相关的任务时，应用本 Skill。\n\n"
        f"## 执行步骤\n\n"
        f"1. 理解用户意图与约束\n"
        f"2. 选择合适的内置工具逐步执行\n"
        f"3. 验证结果并向用户汇报\n\n"
        f"## 输出格式\n\n"
        f"清晰说明做了什么、产物路径或下一步建议。\n"
    )


def ensure_skill_md(install_path: Path, manifest: dict) -> Path:
    """Create SKILL.md from manifest if missing. Returns path to SKILL.md."""
    install_path.mkdir(parents=True, exist_ok=True)
    existing = _skill_md_path(install_path, manifest)
    if existing:
        return existing
    md_path = install_path / "SKILL.md"
    display = manifest.get("display_name") or manifest.get("name") or install_path.name
    desc = manifest.get("description") or ""
    md_path.write_text(default_skill_md(str(display), str(desc)), encoding="utf-8")
    return md_path


def load_enabled_skill_sections() -> list[dict]:
    """Return enabled skills with prompt text from SKILL.md or manifest fallback."""
    from core.settings_runtime import plugins_disabled

    if plugins_disabled():
        return []

    rows = query_all(
        "SELECT package_name, display_name, install_path, manifest_json "
        "FROM installed_skill_packages WHERE enabled = 1 ORDER BY id"
    )
    sections: list[dict] = []
    for row in rows:
        install_path = Path(row.get("install_path") or "")
        if not install_path.is_dir():
            continue
        manifest_raw = row.get("manifest_json") or ""
        try:
            manifest = json.loads(manifest_raw) if manifest_raw else {}
        except Exception:
            manifest = {}

        display = (
            row.get("display_name")
            or manifest.get("display_name")
            or row.get("package_name")
            or install_path.name
        )
        package_name = row.get("package_name") or manifest.get("name") or install_path.name

        inline = (manifest.get("skill_prompt") or "").strip()
        if inline:
            content = inline
        else:
            md_path = _skill_md_path(install_path, manifest)
            if not md_path:
                md_path = ensure_skill_md(install_path, manifest)
            content = md_path.read_text(encoding="utf-8", errors="replace").strip()

        if not content:
            continue
        if len(content) > _MAX_SKILL_CHARS:
            content = content[:_MAX_SKILL_CHARS] + "\n\n…(Skill 说明过长，已截断)"

        sections.append({
            "package_name": package_name,
            "display_name": display,
            "content": content,
        })
    return sections


def build_skills_system_suffix() -> str:
    sections = load_enabled_skill_sections()
    if not sections:
        return ""

    lines = [
        "",
        "## 已启用的 Skill（SKILL.md）",
        "",
        "以下 Skill 已通过 Markdown 说明注入。遇到匹配任务时**优先遵循**对应步骤、格式与约束；"
        "使用 Agent **内置工具**执行，不要等待不存在的专用工具。",
        "",
    ]
    used = len("\n".join(lines))
    for sec in sections:
        block = (
            f"---\n"
            f"### Skill: {sec['display_name']} (`{sec['package_name']}`)\n\n"
            f"{sec['content']}\n"
        )
        if used + len(block) > _MAX_TOTAL_CHARS:
            remain = _MAX_TOTAL_CHARS - used - 40
            if remain > 200:
                lines.append(block[:remain] + "\n…(更多 Skill 说明已省略)\n")
            break
        lines.append(block)
        used += len(block)

    names = "、".join(s["display_name"] for s in sections)
    lines.append(f"\n当前启用 Skill：{names}\n")
    return "\n".join(lines)

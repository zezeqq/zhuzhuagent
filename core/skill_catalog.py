"""Skill 目录 — 仅使用远程 catalog（GitHub JSON），不再维护本地硬编码列表。"""

from __future__ import annotations

from utils.path_utils import (
    builtin_skills_dir,
    installed_skills_dir,
    skill_downloads_dir,
)
from db.database import query_all

INSTALLED_SKILLS_DIR = installed_skills_dir()
SKILL_DOWNLOADS_DIR = skill_downloads_dir()
BUILTIN_SKILLS_DIR = builtin_skills_dir()

SKILL_TYPE_LABELS = {
    "prompt": "说明文档",
    "tool": "含工具",
}

SKILL_CATEGORIES = ["全部", "办公", "效率", "开发", "研究", "数据", "工程", "创意", "远程"]

# 已废弃：市场列表仅来自远程 catalog.json
RECOMMENDED_SKILLS: list[dict] = []

_STUB_MAX_CHARS = 200
_STUB_MAX_LINES = 5


def is_catalog_stub(skill: dict) -> bool:
    """一行 skill_md 的 catalog 占位项，市场不展示、不可安装。"""
    if skill.get("discovered"):
        return False
    if skill.get("stub") is True or skill.get("status") in ("stub", "planned", "placeholder"):
        return True
    if skill.get("stub") is False or skill.get("status") == "published":
        return False
    if skill.get("install_url") or skill.get("package_url"):
        return False
    if skill.get("tools"):
        return False

    md = (skill.get("skill_md") or "").strip()
    if not md:
        return True
    if "##" in md and md.count("\n") >= 5:
        return False
    if len(md) >= 280:
        return False

    lines = [ln for ln in md.splitlines() if ln.strip()]
    if len(lines) <= _STUB_MAX_LINES and len(md) < _STUB_MAX_CHARS:
        return True
    return False


def all_catalog_skills(*, include_stubs: bool = False) -> list[dict]:
    from core.remote_catalog import all_network_catalog_skills
    items = all_network_catalog_skills()
    if include_stubs:
        return items
    return [s for s in items if not is_catalog_stub(s)]


def skill_by_name(name: str) -> dict | None:
    key = name.strip().lower().replace(" ", "_")
    for s in all_catalog_skills(include_stubs=True):
        if s.get("name", "").lower() == key:
            return s
        if s.get("display", "").lower() == name.strip().lower():
            return s
    return None


def skill_type_label(skill: dict) -> str:
    return SKILL_TYPE_LABELS.get(skill.get("skill_type", "prompt"), "说明文档")


def is_planned_skill(skill: dict) -> bool:
    return is_catalog_stub(skill)


def install_success_message(skill: dict, install_path: str) -> str:
    st = skill.get("skill_type", "prompt")
    base = f"技能「{skill.get('display', skill.get('name'))}」已安装。\n\n路径：{install_path}\n\n"
    if st == "tool":
        return base + "本 Skill 含专用工具函数，下一条 Craft 对话生效。"
    return base + "本 Skill 通过 SKILL.md 注入 Agent，下一条 Craft/Plan 对话生效。"


def get_installed_package_names() -> set[str]:
    names: set[str] = set()
    for row in query_all("SELECT package_name, display_name FROM installed_skill_packages"):
        if row.get("package_name"):
            names.add(str(row["package_name"]).lower())
        if row.get("display_name"):
            names.add(str(row["display_name"]).lower())
    return names


def is_skill_installed(skill: dict, installed: set[str] | None = None) -> bool:
    installed = installed if installed is not None else get_installed_package_names()
    pkg = skill.get("name", "").strip().lower().replace(" ", "_")
    display = skill.get("display", "").strip().lower()
    return pkg in installed or display in installed or skill.get("name", "").lower() in installed


def list_featured_skills() -> list[dict]:
    from core.remote_catalog import list_hot_remote_skills
    return [s for s in list_hot_remote_skills() if not is_catalog_stub(s)]


def catalog_market_stats() -> dict:
    """市场展示统计：可见 / 原始 / 隐藏占位。"""
    raw = all_catalog_skills(include_stubs=True)
    visible = all_catalog_skills(include_stubs=False)
    bundled = sum(1 for s in visible if s.get("bundled"))
    remote_visible = sum(1 for s in visible if not s.get("bundled"))
    return {
        "visible": len(visible),
        "raw": len(raw),
        "hidden_stubs": max(0, len(raw) - len(visible)),
        "bundled": bundled,
        "remote_visible": remote_visible,
    }


def catalog_skills_for_category(category: str) -> list[dict]:
    skills = all_catalog_skills()
    if category == "全部":
        return list(skills)
    return [s for s in skills if s.get("category") == category]

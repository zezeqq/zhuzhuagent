"""Generate skill.py for catalog Tool Skills."""

from __future__ import annotations

FILE_ORGANIZER_PY = '''"""File organizer tool skill — list exports inventory."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path


def _exports_root() -> Path:
    from utils.path_utils import exports_dir
    return exports_dir()


def list_exports_inventory(args: dict) -> str:
    sub = (args.get("subpath") or "").strip().replace("\\\\", "/").strip("/")
    root = _exports_root()
    target = root / sub if sub else root
    if not target.is_dir():
        return f"错误：目录不存在 {target}"
    groups: dict[str, list[str]] = defaultdict(list)
    for p in sorted(target.iterdir()):
        if p.is_file():
            groups[p.suffix.lower() or "(无扩展名)"].append(p.name)
    if not groups:
        return f"{target} 为空。"
    lines = [f"# exports 清单: {target}", ""]
    for ext, names in sorted(groups.items()):
        lines.append(f"## {ext} ({len(names)})")
        for n in names[:50]:
            lines.append(f"- {n}")
        if len(names) > 50:
            lines.append(f"- … 还有 {len(names) - 50} 个")
        lines.append("")
    return "\\n".join(lines)


def handle(args: dict) -> str:
    tool = args.get("_tool") or args.get("tool") or "list_exports_inventory"
    fn = globals().get(tool)
    if callable(fn):
        return fn(args)
    return list_exports_inventory(args)
'''

_BUILTIN_TOOL_SOURCES: dict[str, str] = {
    "file_organizer": FILE_ORGANIZER_PY,
}


def tool_skill_source(package_name: str) -> str | None:
    return _BUILTIN_TOOL_SOURCES.get(package_name)


def default_tool_skill_py(package_name: str, tools: list[dict]) -> str:
    custom = tool_skill_source(package_name)
    if custom:
        return custom
    names = [t.get("name", "") for t in tools if t.get("name")]
    lines = [
        f'"""Tool skill: {package_name}"""',
        "",
        "def handle(args: dict) -> str:",
        '    tool = args.get("_tool") or ""',
    ]
    for n in names:
        lines.append(f'    if tool == "{n}":')
        lines.append(f'        return "工具 {n} 尚未实现，请在 skill.py 中补充逻辑。"')
    lines.append('    return "未知工具"')
    return "\n".join(lines) + "\n"

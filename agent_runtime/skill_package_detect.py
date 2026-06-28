"""识别 GitHub / 本地 Skill 包目录与说明文档（不限于 SKILL.md 文件名）。"""

from __future__ import annotations

import json
from pathlib import Path

# 常见 Skill 合集目录（相对仓库根）
_SKILL_CONTAINER_REL_PATHS: tuple[tuple[str, ...], ...] = (
    ("skills",),
    (".claude", "skills"),
    (".gemini", "skills"),
    (".codex", "skills"),
    (".opencode", "skills"),
)

# 扫描时跳过的路径片段
_SKIP_PARTS = frozenset({
    ".github", "__pycache__", "node_modules", "venv", ".venv",
    "dist", "build", "coverage", ".git",
})

# 不作为 Skill 正文的 md 文件名（小写）
_NON_SKILL_MD_NAMES = frozenset({
    "readme.md", "changelog.md", "changelog.zh.md", "contributing.md",
    "license.md", "code_of_conduct.md", "security.md", "agents.md",
    "claude.md", "readme.zh-cn.md", "readme.zh.md",
})


def _path_has_skip_part(path: Path) -> bool:
    return any(part in _SKIP_PARTS for part in path.parts)


def find_file_case_insensitive(directory: Path, filename: str) -> Path | None:
    if not directory.is_dir():
        return None
    target = filename.lower()
    for item in directory.iterdir():
        if item.is_file() and item.name.lower() == target:
            return item
    return None


def _read_manifest_prompt_entry(package_dir: Path) -> str:
    for name in ("skill.json", "dna_skill.json", "manifest.json", "plugin.json"):
        p = package_dir / name
        if not p.is_file():
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        for key in ("prompt_entry", "entry", "skill_md", "prompt_file"):
            val = (data.get(key) or "").strip()
            if val.lower().endswith(".md"):
                candidate = package_dir / val
                if candidate.is_file():
                    return val.replace("\\", "/")
                ci = find_file_case_insensitive(package_dir, Path(val).name)
                if ci:
                    return ci.name
    return ""


def _markdown_candidates(package_dir: Path) -> list[Path]:
    if not package_dir.is_dir():
        return []
    out: list[Path] = []
    for item in sorted(package_dir.iterdir()):
        if not item.is_file() or item.suffix.lower() != ".md":
            continue
        if item.name.lower() in _NON_SKILL_MD_NAMES:
            continue
        out.append(item)
    return out


def find_skill_entry_md(package_dir: Path) -> Path | None:
    """返回 Skill 包目录内的说明文档路径（可为 SKILL.md、aass.md 等）。"""
    if not package_dir.is_dir():
        return None

    manifest_entry = _read_manifest_prompt_entry(package_dir)
    if manifest_entry:
        p = package_dir / manifest_entry
        if p.is_file():
            return p

    for preferred in ("SKILL.md", "skill.md", "Skill.md"):
        found = find_file_case_insensitive(package_dir, preferred)
        if found:
            return found

    candidates = _markdown_candidates(package_dir)
    if len(candidates) == 1:
        return candidates[0]
    if len(candidates) > 1:
        for c in candidates:
            if c.name.lower() == "skill.md" or c.stem.lower() == package_dir.name.lower():
                return c
        return candidates[0]
    return None


def is_skill_package_dir(package_dir: Path) -> bool:
    if find_skill_entry_md(package_dir):
        return True
    for name in ("skill.json", "dna_skill.json", "manifest.json", "plugin.json"):
        if (package_dir / name).is_file():
            return True
    return False


def _skill_container_dirs(repo_root: Path) -> list[Path]:
    containers: list[Path] = []
    seen: set[Path] = set()
    for parts in _SKILL_CONTAINER_REL_PATHS:
        p = repo_root.joinpath(*parts)
        if p.is_dir():
            resolved = p.resolve()
            if resolved not in seen:
                seen.add(resolved)
                containers.append(p)
    return containers


def _packages_in_container(container: Path) -> list[Path]:
    packages: list[Path] = []
    if not container.is_dir():
        return packages
    for sub in sorted(container.iterdir()):
        if not sub.is_dir() or _path_has_skip_part(sub):
            continue
        if is_skill_package_dir(sub):
            packages.append(sub)
    return packages


def find_skill_package_roots(repo_root: Path) -> list[Path]:
    """识别仓库内可安装的 Skill 包目录列表。"""
    if not repo_root.is_dir():
        return []

    if is_skill_package_dir(repo_root):
        return [repo_root]

    roots: list[Path] = []
    seen: set[Path] = set()

    for container in _skill_container_dirs(repo_root):
        for pkg in _packages_in_container(container):
            key = pkg.resolve()
            if key not in seen:
                seen.add(key)
                roots.append(pkg)

    if roots:
        return roots

    for md in sorted(repo_root.rglob("*.md")):
        if _path_has_skip_part(md):
            continue
        if md.name.lower() in _NON_SKILL_MD_NAMES:
            continue
        parent = md.parent
        if parent == repo_root:
            continue
        if not is_skill_package_dir(parent):
            continue
        key = parent.resolve()
        if key not in seen:
            seen.add(key)
            roots.append(parent)

    return roots


def apply_prompt_entry_to_manifest(package_dir: Path, manifest: dict) -> dict:
    """把识别到的 md 路径写入 manifest，供加载与 UI 使用。"""
    entry = find_skill_entry_md(package_dir)
    if entry:
        rel = entry.name
        manifest["prompt_entry"] = rel
        manifest["entry"] = rel
    return manifest

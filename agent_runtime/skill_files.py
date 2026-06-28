"""Resolve Skill package files for UI viewing."""

from __future__ import annotations

import json
from pathlib import Path


def list_skill_files(install_path: Path) -> list[tuple[str, Path]]:
    """Return (label, path) pairs for files to show in the editor."""
    if not install_path.is_dir():
        return []

    preferred = ["SKILL.md", "skill.json", "skill.py", "dna_skill.json", "manifest.json", "README.md"]
    found: list[tuple[str, Path]] = []
    seen: set[Path] = set()

    for name in preferred:
        p = install_path / name
        if p.is_file():
            found.append((name, p))
            seen.add(p.resolve())

    for p in sorted(install_path.rglob("*")):
        if not p.is_file() or p.resolve() in seen:
            continue
        if p.suffix.lower() in {".md", ".json", ".py", ".txt"} and "__pycache__" not in p.parts:
            rel = p.relative_to(install_path)
            found.append((str(rel).replace("\\", "/"), p))
            seen.add(p.resolve())

    return found


def read_skill_file(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def write_skill_file(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def skill_summary(install_path: Path, manifest: dict | None = None) -> str:
    manifest = manifest or {}
    lines = [str(install_path)]
    desc = (manifest.get("description") or "").strip()
    if desc:
        lines.append(desc)
    files = list_skill_files(install_path)
    if files:
        lines.append("文件: " + ", ".join(label for label, _ in files[:5]))
    return "\n".join(lines)

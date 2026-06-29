"""Chat @-references: library uploads and generated artifacts."""

from __future__ import annotations

from pathlib import Path

from core.agent_context import current_project
from core.file_manager import list_library_files
from artifacts.artifact_manager import list_artifacts
from rag.document_loader import load_text
from utils.path_utils import exports_dir


def collect_reference_candidates(project_id: int | None = None) -> list[dict]:
    """Build selectable items for the @ popup."""
    items: list[dict] = []
    seen: set[str] = set()

    for row in list_library_files(project_id):
        path = (row.get("file_path") or "").strip()
        if not path or path in seen:
            continue
        p = Path(path)
        if not p.is_file():
            continue
        seen.add(path)
        items.append({
            "name": row.get("file_name") or p.name,
            "path": path,
            "category": "library",
            "icon": "📚",
            "subtitle": "资料库",
        })

    for art in list_artifacts(120):
        path = (art.get("file_path") or "").strip()
        if not path or path in seen:
            continue
        p = Path(path)
        if not p.is_file():
            continue
        seen.add(path)
        items.append({
            "name": art.get("artifact_name") or p.name,
            "path": path,
            "category": "artifact",
            "icon": "📄",
            "subtitle": "生成文件",
        })

    export_root = exports_dir()
    if export_root.exists():
        artifact_count = sum(1 for i in items if i["category"] == "artifact")
        for p in sorted(
            (f for f in export_root.rglob("*") if f.is_file()),
            key=lambda f: f.stat().st_mtime,
            reverse=True,
        ):
            sp = str(p)
            if sp in seen:
                continue
            seen.add(sp)
            items.append({
                "name": p.name,
                "path": sp,
                "category": "artifact",
                "icon": "📄",
                "subtitle": "exports",
            })
            artifact_count += 1
            if artifact_count >= 40:
                break

    return items


def filter_reference_candidates(query: str, project_id: int | None = None) -> list[dict]:
    q = (query or "").strip().lower()
    items = collect_reference_candidates(project_id)
    if not q:
        return items[:40]
    filtered = [
        item for item in items
        if q in item["name"].lower() or q in Path(item["path"]).name.lower()
    ]
    return filtered[:40]


def build_referenced_files_context(paths: list[str], *, max_chars_per_file: int = 4500) -> str:
    blocks: list[str] = []
    for raw in paths:
        path = Path(raw)
        if not path.is_file():
            blocks.append(f"### @{path.name}\n文件不存在或路径无效：{raw}")
            continue
        try:
            pages = load_text(path)
            text = "\n".join(page.get("text", "") for page in pages if page.get("text"))
            text = text.strip()
            if not text:
                blocks.append(f"### @{path.name}\n（未能提取文本内容，可能是扫描版 PDF）")
                continue
            if len(text) > max_chars_per_file:
                text = text[:max_chars_per_file] + "\n…(已截断)"
            blocks.append(f"### @{path.name}\n路径: {path}\n\n{text}")
        except Exception as exc:
            blocks.append(f"### @{path.name}\n读取失败: {exc}")
    return "\n\n".join(blocks)


def current_project_id() -> int | None:
    project = current_project()
    return project["id"] if project else None

from __future__ import annotations

from pathlib import Path

from db.database import insert, query_all
from rag.indexer import index_file
from utils.file_utils import copy_to_folder
from utils.path_utils import uploads_dir


def import_file(path: str | Path, project_id: int | None = None) -> int:
    p = Path(path)
    copied = copy_to_folder(p, uploads_dir())
    return insert("files", {
        "project_id": project_id,
        "file_name": p.name,
        "file_path": str(copied),
        "original_path": str(p),
        "file_type": p.suffix.lower().lstrip("."),
        "file_size": p.stat().st_size,
        "summary": "已导入，待索引",
    })


def list_project_files(project_id: int | None = None) -> list[dict]:
    if project_id:
        return query_all(
            "SELECT * FROM files WHERE project_id=? OR project_id IS NULL ORDER BY id DESC",
            (project_id,),
        )
    return query_all("SELECT * FROM files ORDER BY id DESC")


def list_library_files(project_id: int | None = None) -> list[dict]:
    """List files visible to the agent: current project + global library uploads."""
    return list_project_files(project_id)

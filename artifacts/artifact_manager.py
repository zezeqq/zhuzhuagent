from __future__ import annotations

from pathlib import Path

from db.database import insert, query_all, query_one
from utils.path_utils import exports_dir


def ensure_export_dir() -> Path:
    return exports_dir()


def register_artifact(
    file_path: str | Path,
    artifact_type: str,
    task_id: int | None = None,
    project_id: int | None = None,
    description: str = "",
    preview_path: str = "",
) -> int:
    path = Path(file_path)
    return insert(
        "artifacts",
        {
            "task_id": task_id,
            "project_id": project_id,
            "artifact_name": path.name,
            "artifact_type": artifact_type,
            "file_path": str(path),
            "preview_path": preview_path,
            "description": description,
        },
    )


def list_artifacts(limit: int = 200) -> list[dict]:
    return query_all("SELECT * FROM artifacts ORDER BY id DESC LIMIT ?", (limit,))


def get_artifact(artifact_id: int) -> dict | None:
    return query_one("SELECT * FROM artifacts WHERE id=?", (artifact_id,))


def remove_artifact_by_path(file_path: str | Path) -> None:
    from db.database import execute

    execute("DELETE FROM artifacts WHERE file_path=?", (str(file_path),))

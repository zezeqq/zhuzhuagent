from __future__ import annotations

from pathlib import Path

from db.database import insert, query_all
from rag.indexer import index_standard
from utils.file_utils import copy_to_folder
from utils.path_utils import standards_dir


def import_standard(path: str | Path, name: str = "", code: str = "") -> int:
    p = Path(path)
    copied = copy_to_folder(p, standards_dir())
    return insert("standards", {
        "standard_name": name or p.stem,
        "standard_code": code,
        "standard_type": "行业标准",
        "file_path": str(copied),
    })


def list_standards() -> list[dict]:
    return query_all("SELECT * FROM standards ORDER BY id DESC")

"""共享 pytest fixtures：隔离 data/ 与 SQLite，避免污染开发库。"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def force_sparse_rag(monkeypatch):
    """测试环境禁用 fastembed/onnx，避免 Windows DLL 崩溃与拖慢用例。"""
    monkeypatch.setattr("rag.embedding_provider.get_rag_embedding_provider", lambda: "legacy")


@pytest.fixture
def app_tmp(monkeypatch, tmp_path):
    import utils.path_utils as path_utils

    (tmp_path / "db").mkdir(parents=True, exist_ok=True)
    shutil.copy(_PROJECT_ROOT / "db" / "schema.sql", tmp_path / "db" / "schema.sql")

    monkeypatch.setattr(path_utils, "_APP_ROOT", tmp_path)
    from db.database import init_database

    init_database()
    yield tmp_path


@pytest.fixture
def sample_project(app_tmp):
    from db.database import insert

    pid = insert("projects", {"project_name": "测试项目", "is_current": 1})
    return {"id": pid, "project_name": "测试项目"}


@pytest.fixture
def chrome_software(app_tmp):
    from db.database import insert

    return insert(
        "software_tools",
        {
            "software_name": "Chrome",
            "executable_path": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            "enabled": 1,
        },
    )

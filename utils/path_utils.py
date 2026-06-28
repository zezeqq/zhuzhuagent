"""Application paths for development and PyInstaller-frozen builds."""

from __future__ import annotations

import sys
from pathlib import Path

_APP_ROOT: Path | None = None


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def app_root() -> Path:
    """Writable root: folder containing the exe when packaged, project root in dev."""
    global _APP_ROOT
    if _APP_ROOT is None:
        if is_frozen():
            _APP_ROOT = Path(sys.executable).resolve().parent
        else:
            _APP_ROOT = Path(__file__).resolve().parents[1]
    return _APP_ROOT


def resource_root() -> Path:
    """Read-only bundled resources (_MEIPASS when frozen)."""
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS"))
    return app_root()


def resource_path(*parts: str) -> Path:
    return resource_root().joinpath(*parts)


def data_dir() -> Path:
    root = app_root() / "data"
    root.mkdir(parents=True, exist_ok=True)
    return root


def ensure_data_subdir(name: str) -> Path:
    path = data_dir() / name
    path.mkdir(parents=True, exist_ok=True)
    return path


def db_path() -> Path:
    return data_dir() / "database.sqlite"


def schema_path() -> Path:
    return resource_path("db", "schema.sql")


def exports_dir() -> Path:
    return ensure_data_subdir("exports")


def uploads_dir() -> Path:
    return ensure_data_subdir("uploads")


def standards_dir() -> Path:
    return ensure_data_subdir("standards")


def installed_skills_dir() -> Path:
    return ensure_data_subdir("installed_skills")


def skill_downloads_dir() -> Path:
    return ensure_data_subdir("skill_downloads")


def log_dir() -> Path:
    return ensure_data_subdir("logs")


def log_file() -> Path:
    return log_dir() / "app.log"


def builtin_skills_dir() -> Path:
    bundled = resource_path("skills")
    if bundled.is_dir():
        return bundled
    return app_root() / "skills"

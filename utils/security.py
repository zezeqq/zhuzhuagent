from __future__ import annotations

from pathlib import Path


def mask_secret(value: str | None) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "***"
    return f"{value[:4]}***{value[-4:]}"


def is_safe_path(path: str | Path) -> bool:
    try:
        Path(path).expanduser().resolve()
        return True
    except Exception:
        return False

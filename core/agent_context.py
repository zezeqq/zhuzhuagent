from __future__ import annotations

from db.database import query_one


def current_project() -> dict | None:
    return query_one("SELECT * FROM projects WHERE is_current=1 ORDER BY id DESC LIMIT 1")


def default_model() -> dict | None:
    from core.model_profiles import enrich_model_config

    row = query_one("SELECT * FROM models WHERE is_default=1 AND enabled=1 ORDER BY id DESC LIMIT 1")
    return enrich_model_config(row)

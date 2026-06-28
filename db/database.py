from __future__ import annotations

import sqlite3
from typing import Any

from utils.path_utils import data_dir, db_path, schema_path


def get_connection() -> sqlite3.Connection:
    data_dir()
    conn = sqlite3.connect(db_path())
    conn.row_factory = sqlite3.Row
    return conn


def init_database() -> None:
    data_dir()
    schema_file = schema_path()
    if not schema_file.is_file():
        raise FileNotFoundError(f"数据库结构文件不存在: {schema_file}")
    with get_connection() as conn:
        conn.executescript(schema_file.read_text(encoding="utf-8"))
        _migrate(conn)
        conn.commit()


def _migrate(conn: sqlite3.Connection) -> None:
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(tasks)").fetchall()}
    task_migrations = {
        "risk_level": "ALTER TABLE tasks ADD COLUMN risk_level TEXT DEFAULT 'low'",
        "user_goal": "ALTER TABLE tasks ADD COLUMN user_goal TEXT",
        "plan_json": "ALTER TABLE tasks ADD COLUMN plan_json TEXT",
        "current_step": "ALTER TABLE tasks ADD COLUMN current_step INTEGER DEFAULT 0",
        "error_message": "ALTER TABLE tasks ADD COLUMN error_message TEXT",
        "completed_at": "ALTER TABLE tasks ADD COLUMN completed_at TEXT",
        "conversation_id": "ALTER TABLE tasks ADD COLUMN conversation_id INTEGER",
    }
    for column, sql in task_migrations.items():
        if column not in columns:
            conn.execute(sql)
    conv_cols = {row["name"] for row in conn.execute("PRAGMA table_info(conversations)").fetchall()}
    conv_migrations = {
        "mode": "ALTER TABLE conversations ADD COLUMN mode TEXT DEFAULT 'craft'",
        "status": "ALTER TABLE conversations ADD COLUMN status TEXT DEFAULT 'active'",
    }
    for column, sql in conv_migrations.items():
        if column not in conv_cols:
            conn.execute(sql)
    chunk_cols = {row["name"] for row in conn.execute("PRAGMA table_info(file_chunks)").fetchall()}
    if "embedding_json" not in chunk_cols:
        conn.execute("ALTER TABLE file_chunks ADD COLUMN embedding_json TEXT")


def execute(sql: str, params: tuple | list = ()) -> int:
    with get_connection() as conn:
        cur = conn.execute(sql, params)
        conn.commit()
        return cur.rowcount


def query_all(sql: str, params: tuple | list = ()) -> list[dict[str, Any]]:
    with get_connection() as conn:
        return [dict(row) for row in conn.execute(sql, params).fetchall()]


def query_one(sql: str, params: tuple | list = ()) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute(sql, params).fetchone()
        return dict(row) if row else None


def insert(table: str, data: dict[str, Any]) -> int:
    keys = list(data.keys())
    placeholders = ", ".join(["?"] * len(keys))
    sql = f"INSERT INTO {table} ({', '.join(keys)}) VALUES ({placeholders})"
    with get_connection() as conn:
        cur = conn.execute(sql, [data[key] for key in keys])
        conn.commit()
        return int(cur.lastrowid)


def update(table: str, row_id: int, data: dict[str, Any]) -> int:
    keys = list(data.keys())
    assignments = ", ".join([f"{key}=?" for key in keys])
    values = [data[key] for key in keys] + [row_id]
    return execute(f"UPDATE {table} SET {assignments}, updated_at=CURRENT_TIMESTAMP WHERE id=?", values)


def delete(table: str, row_id: int) -> int:
    return execute(f"DELETE FROM {table} WHERE id=?", (row_id,))

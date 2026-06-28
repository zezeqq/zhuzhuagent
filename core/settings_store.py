from __future__ import annotations

from db.database import execute, insert, query_one


def get_setting(key: str, default: str = "") -> str:
    row = query_one("SELECT setting_value FROM settings WHERE setting_key=?", (key,))
    return row["setting_value"] if row else default


def set_setting(key: str, value: str, setting_type: str = "string") -> None:
    if query_one("SELECT id FROM settings WHERE setting_key=?", (key,)):
        execute(
            "UPDATE settings SET setting_value=?, setting_type=?, updated_at=CURRENT_TIMESTAMP WHERE setting_key=?",
            (value, setting_type, key),
        )
    else:
        insert("settings", {"setting_key": key, "setting_value": value, "setting_type": setting_type})


def get_bool(key: str, default: bool = False) -> bool:
    return get_setting(key, "1" if default else "0") == "1"


def set_bool(key: str, value: bool) -> None:
    set_setting(key, "1" if value else "0", "bool")

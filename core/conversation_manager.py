from __future__ import annotations

from db.database import delete, execute, insert, query_all, query_one


def create_conversation(project_id: int | None = None, title: str = "新任务", mode: str = "craft") -> int:
    return insert("conversations", {
        "project_id": project_id,
        "title": title,
        "mode": mode,
        "status": "active",
    })


def list_conversations(limit: int = 200) -> list[dict]:
    return query_all(
        "SELECT * FROM conversations ORDER BY updated_at DESC, id DESC LIMIT ?", (limit,)
    )


def get_conversation(conversation_id: int) -> dict | None:
    return query_one("SELECT * FROM conversations WHERE id=?", (conversation_id,))


def update_conversation(conversation_id: int, **fields) -> None:
    if not fields:
        return
    sets = ", ".join(f"{k}=?" for k in fields)
    vals = list(fields.values()) + [conversation_id]
    execute(f"UPDATE conversations SET {sets}, updated_at=CURRENT_TIMESTAMP WHERE id=?", vals)


def delete_conversation(conversation_id: int) -> None:
    execute("DELETE FROM messages WHERE conversation_id=?", (conversation_id,))
    execute("DELETE FROM tasks WHERE conversation_id=?", (conversation_id,))
    delete("conversations", conversation_id)


def get_messages(conversation_id: int) -> list[dict]:
    return query_all(
        "SELECT * FROM messages WHERE conversation_id=? ORDER BY id", (conversation_id,)
    )


def add_message(conversation_id: int, role: str, content: str, project_id: int | None = None) -> int:
    from core.settings_store import get_bool

    if role != "user" and not get_bool("auto_save_chat", True):
        execute(
            "UPDATE conversations SET updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (conversation_id,),
        )
        return 0

    msg_id = insert("messages", {
        "conversation_id": conversation_id,
        "project_id": project_id,
        "role": role,
        "content": content,
    })
    title_text = content[:40].replace("\n", " ").strip()
    conv = get_conversation(conversation_id)
    if conv and conv.get("title") == "新任务" and role == "user":
        update_conversation(conversation_id, title=title_text)
    else:
        execute("UPDATE conversations SET updated_at=CURRENT_TIMESTAMP WHERE id=?", (conversation_id,))
    return msg_id


def search_conversations(keyword: str) -> list[dict]:
    like = f"%{keyword}%"
    return query_all(
        "SELECT DISTINCT c.* FROM conversations c "
        "LEFT JOIN messages m ON m.conversation_id=c.id "
        "WHERE c.title LIKE ? OR m.content LIKE ? "
        "ORDER BY c.updated_at DESC LIMIT 50",
        (like, like),
    )


def conversation_task_info(conversation_id: int) -> dict | None:
    return query_one(
        "SELECT id, status, task_type FROM tasks WHERE conversation_id=? ORDER BY id DESC LIMIT 1",
        (conversation_id,),
    )


def batch_conversation_task_info(conversation_ids: list[int]) -> dict[int, dict]:
    """一次查询多会话的任务状态，避免侧边栏 N+1。"""
    ids = [int(i) for i in conversation_ids if i]
    if not ids:
        return {}
    placeholders = ",".join("?" * len(ids))
    rows = query_all(
        f"SELECT conversation_id, id, status, task_type FROM tasks "
        f"WHERE conversation_id IN ({placeholders}) ORDER BY conversation_id, id DESC",
        ids,
    )
    result: dict[int, dict] = {}
    for row in rows:
        cid = row.get("conversation_id")
        if cid is not None and cid not in result:
            result[int(cid)] = row
    return result

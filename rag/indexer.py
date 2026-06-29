from __future__ import annotations

from db.database import execute, insert, query_one
from rag.document_loader import load_text
from rag.embedding_provider import active_embedding_backend, parse_embedding_json
from rag.embeddings import embed_texts_batch
from rag.text_splitter import split_text
from utils.text_utils import keywords_from_query


def _chunk_model_id(embedding_json: str) -> str:
    _fmt, _vec, model_id = parse_embedding_json(embedding_json)
    return model_id or active_embedding_backend()


def _collect_chunks(row: dict, *, source_type: str, standard_code: str | None = None) -> list[dict]:
    pending: list[dict] = []
    for page in load_text(row["file_path"]):
        for i, chunk in enumerate(split_text(page["text"])):
            if not (chunk or "").strip():
                continue
            item: dict = {
                "file_id": row.get("id") if source_type == "file" else None,
                "project_id": row.get("project_id"),
                "source_type": source_type,
                "page_number": page.get("page_number"),
                "chunk_index": i,
                "content": chunk,
                "keywords": " ".join(keywords_from_query(chunk)),
            }
            if source_type == "standard":
                item["standard_code"] = standard_code or row.get("standard_code")
            pending.append(item)
    return pending


def _insert_chunks(pending: list[dict]) -> int:
    if not pending:
        return 0
    texts = [p["content"] for p in pending]
    embeddings = embed_texts_batch(texts)
    count = 0
    for item, emb_json in zip(pending, embeddings):
        insert("file_chunks", {
            **item,
            "embedding_json": emb_json,
            "embedding_model": _chunk_model_id(emb_json),
        })
        count += 1
    return count


def index_file(file_id: int) -> int:
    row = query_one("SELECT * FROM files WHERE id=?", (file_id,))
    if not row:
        raise ValueError("文件记录不存在")
    execute("DELETE FROM file_chunks WHERE file_id=? AND source_type='file'", (file_id,))
    pending = _collect_chunks(row, source_type="file")
    return _insert_chunks(pending)


def index_standard(standard_id: int) -> int:
    row = query_one("SELECT * FROM standards WHERE id=?", (standard_id,))
    if not row:
        raise ValueError("标准记录不存在")
    execute(
        "DELETE FROM file_chunks WHERE source_type='standard' AND standard_code=?",
        (row.get("standard_code"),),
    )
    pending = _collect_chunks(row, source_type="standard", standard_code=row.get("standard_code"))
    return _insert_chunks(pending)


def reindex_all_files() -> int:
    """对所有已导入文件重新分块并写入 embedding。"""
    from db.database import query_all

    rows = query_all("SELECT id FROM files ORDER BY id")
    total_chunks = 0
    for row in rows:
        total_chunks += index_file(row["id"])
    return len(rows)


def reindex_all_standards() -> int:
    from db.database import query_all

    rows = query_all("SELECT id FROM standards ORDER BY id")
    for row in rows:
        index_standard(row["id"])
    return len(rows)

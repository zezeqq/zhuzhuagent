from __future__ import annotations

from pathlib import Path

from db.database import execute, insert, query_one
from rag.document_loader import load_text
from rag.embeddings import embed_to_json
from rag.text_splitter import split_text
from utils.text_utils import keywords_from_query


def index_file(file_id: int) -> int:
    row = query_one("SELECT * FROM files WHERE id=?", (file_id,))
    if not row:
        raise ValueError("文件记录不存在")
    execute("DELETE FROM file_chunks WHERE file_id=? AND source_type='file'", (file_id,))
    count = 0
    for page in load_text(row["file_path"]):
        for i, chunk in enumerate(split_text(page["text"])):
            insert("file_chunks", {
                "file_id": file_id,
                "project_id": row.get("project_id"),
                "source_type": "file",
                "page_number": page.get("page_number"),
                "chunk_index": i,
                "content": chunk,
                "keywords": " ".join(keywords_from_query(chunk)),
                "embedding_json": embed_to_json(chunk),
            })
            count += 1
    return count


def index_standard(standard_id: int) -> int:
    row = query_one("SELECT * FROM standards WHERE id=?", (standard_id,))
    if not row:
        raise ValueError("标准记录不存在")
    execute("DELETE FROM file_chunks WHERE source_type='standard' AND standard_code=?", (row.get("standard_code"),))
    count = 0
    for page in load_text(row["file_path"]):
        for i, chunk in enumerate(split_text(page["text"])):
            insert("file_chunks", {
                "source_type": "standard",
                "standard_code": row.get("standard_code"),
                "chapter": "",
                "page_number": page.get("page_number"),
                "chunk_index": i,
                "content": chunk,
                "keywords": " ".join(keywords_from_query(chunk)),
                "embedding_json": embed_to_json(chunk),
            })
            count += 1
    return count


def reindex_all_files() -> int:
    """对所有已导入文件重新分块并写入 embedding。"""
    from db.database import query_all

    rows = query_all("SELECT id FROM files ORDER BY id")
    for row in rows:
        index_file(row["id"])
    return len(rows)

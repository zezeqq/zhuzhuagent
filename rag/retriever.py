from __future__ import annotations

from db.database import query_all
from rag.embeddings import cosine_similarity, embed_from_json, embed_text
from utils.text_utils import keywords_from_query


def _keyword_search(query: str, project_id: int | None, include_standards: bool, limit: int) -> list[dict]:
    words = keywords_from_query(query)
    if not words:
        return []
    params: list = []
    clauses = []
    for word in words:
        clauses.append("(content LIKE ? OR keywords LIKE ?)")
        params.extend([f"%{word}%", f"%{word}%"])
    sql = f"SELECT * FROM file_chunks WHERE ({' OR '.join(clauses)})"
    if project_id:
        sql += " AND (project_id=? OR source_type='standard')"
        params.append(project_id)
    elif include_standards:
        sql += " AND (source_type='file' OR source_type='standard')"
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(limit * 3)
    return query_all(sql, params)


def _vector_search(query: str, project_id: int | None, include_standards: bool, limit: int) -> list[dict]:
    q_vec = embed_text(query)
    if not q_vec:
        return []
    params: list = []
    sql = "SELECT * FROM file_chunks WHERE embedding_json IS NOT NULL AND embedding_json != ''"
    if project_id:
        sql += " AND (project_id=? OR source_type='standard')"
        params.append(project_id)
    elif include_standards:
        sql += " AND (source_type='file' OR source_type='standard')"
    sql += " ORDER BY id DESC LIMIT 500"
    rows = query_all(sql, params)
    scored: list[tuple[float, dict]] = []
    for row in rows:
        vec = embed_from_json(row.get("embedding_json"))
        score = cosine_similarity(q_vec, vec)
        if score > 0.05:
            scored.append((score, row))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [r for _, r in scored[:limit]]


def search_chunks(
    query: str,
    project_id: int | None = None,
    include_standards: bool = True,
    limit: int = 6,
) -> list[dict]:
    """混合检索：向量相似度 + 关键词 LIKE。"""
    vector_hits = _vector_search(query, project_id, include_standards, limit)
    keyword_hits = _keyword_search(query, project_id, include_standards, limit)
    merged: dict[int, dict] = {}
    for row in vector_hits + keyword_hits:
        rid = row.get("id")
        if rid is not None and rid not in merged:
            merged[rid] = row
    return list(merged.values())[:limit]

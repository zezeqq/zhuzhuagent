from __future__ import annotations

from db.database import query_all, query_one
from rag.embedding_provider import DENSE_FORMAT, SPARSE_FORMAT, embed_query, legacy_sparse_embed, parse_embedding_json, similarity
from utils.text_utils import keywords_from_query

_VECTOR_MIN_SCORE = {
    DENSE_FORMAT: 0.35,
    SPARSE_FORMAT: 0.05,
}
_VECTOR_SCAN_LIMIT = 800


_STRONG_QUERY_ANCHORS = frozenset({
    "财务", "会计", "预算", "模板", "分析", "报告", "工程", "验收", "投标", "施工", "合同", "清单",
})


def _keyword_search(query: str, project_id: int | None, include_standards: bool, limit: int) -> list[tuple[float, dict]]:
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
        sql += " AND (project_id=? OR project_id IS NULL OR source_type='standard')"
        params.append(project_id)
    elif include_standards:
        sql += " AND (source_type='file' OR source_type='standard')"
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(limit * 8)
    rows = query_all(sql, params)
    strong_anchors = [w for w in words if w in _STRONG_QUERY_ANCHORS]
    min_match = 1 if len(words) <= 2 else max(2, (len(words) + 2) // 3)
    hits: list[tuple[float, dict]] = []
    for row in rows:
        content = (row.get("content") or "").lower()
        keyword_blob = (row.get("keywords") or "").lower()
        matched = sum(
            1 for w in words
            if w.lower() in content or w.lower() in keyword_blob
        )
        if matched < min_match:
            continue
        if strong_anchors and not any(a in content or a in keyword_blob for a in strong_anchors):
            continue
        score = matched / max(len(words), 1)
        if strong_anchors:
            anchor_hits = sum(1 for a in strong_anchors if a in content or a in keyword_blob)
            score += anchor_hits * 0.08
        hits.append((score, row))
    hits.sort(key=lambda x: x[0], reverse=True)
    return hits[:limit]


def _vector_search(query: str, project_id: int | None, include_standards: bool, limit: int) -> list[tuple[float, dict]]:
    q_fmt, q_vec, _q_model = embed_query(query)
    q_sparse = legacy_sparse_embed(query)
    if not q_vec and not q_sparse:
        return []

    params: list = []
    sql = "SELECT * FROM file_chunks WHERE embedding_json IS NOT NULL AND embedding_json != ''"
    if project_id:
        sql += " AND (project_id=? OR project_id IS NULL OR source_type='standard')"
        params.append(project_id)
    elif include_standards:
        sql += " AND (source_type='file' OR source_type='standard')"
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(_VECTOR_SCAN_LIMIT)
    rows = query_all(sql, params)

    scored: list[tuple[float, dict]] = []
    for row in rows:
        c_fmt, c_vec, _c_model = parse_embedding_json(row.get("embedding_json"))
        score = 0.0
        if c_fmt == DENSE_FORMAT and q_fmt == DENSE_FORMAT:
            score = similarity(q_fmt, q_vec, c_fmt, c_vec)
            min_score = _VECTOR_MIN_SCORE[DENSE_FORMAT]
        elif c_fmt == SPARSE_FORMAT and q_sparse:
            from rag.embedding_provider import cosine_similarity_sparse
            if isinstance(c_vec, dict):
                score = cosine_similarity_sparse(q_sparse, c_vec)
            min_score = _VECTOR_MIN_SCORE[SPARSE_FORMAT]
        else:
            continue
        if score >= min_score:
            scored.append((score, row))
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[:limit]


def _enrich_chunk(row: dict, *, score: float = 0.0, keyword_score: float = 0.0) -> dict:
    enriched = dict(row)
    enriched["retrieval_score"] = score
    enriched["keyword_score"] = keyword_score
    file_id = enriched.get("file_id")
    if file_id:
        file_row = query_one("SELECT file_name, file_path FROM files WHERE id=?", (file_id,))
        if file_row:
            enriched["file_name"] = file_row.get("file_name", "")
            enriched["file_path"] = file_row.get("file_path", "")
    elif enriched.get("source_type") == "standard" and enriched.get("standard_code"):
        enriched["file_name"] = enriched["standard_code"]
    return enriched


def search_chunks(
    query: str,
    project_id: int | None = None,
    include_standards: bool = True,
    limit: int = 6,
    *,
    use_vector: bool = True,
) -> list[dict]:
    """混合检索：语义向量 + 关键词 LIKE 兜底。use_vector=False 时仅关键词（更快）。"""
    if not (query or "").strip():
        return []

    vector_hits = _vector_search(query, project_id, include_standards, limit) if use_vector else []
    keyword_hits = _keyword_search(query, project_id, include_standards, limit)

    merged: dict[int, dict] = {}
    scores: dict[int, float] = {}
    keyword_scores: dict[int, float] = {}

    for rank, (vscore, row) in enumerate(vector_hits):
        rid = row.get("id")
        if rid is None:
            continue
        scores[rid] = max(scores.get(rid, 0.0), vscore * 0.7 + (1.0 / (rank + 2)) * 0.05)

    for rank, (kscore, row) in enumerate(keyword_hits):
        rid = row.get("id")
        if rid is None:
            continue
        keyword_scores[rid] = max(keyword_scores.get(rid, 0.0), kscore)
        scores[rid] = scores.get(rid, 0.0) + kscore * 0.35 + (1.0 / (rank + 2)) * 0.03
        if rid not in merged:
            merged[rid] = row

    for _score, row in vector_hits:
        rid = row.get("id")
        if rid is not None and rid not in merged:
            merged[rid] = row

    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:limit]
    results: list[dict] = []
    for rid, total in ranked:
        row = merged.get(rid)
        if not row:
            row = query_one("SELECT * FROM file_chunks WHERE id=?", (rid,))
        if row:
            results.append(_enrich_chunk(
                row,
                score=total,
                keyword_score=keyword_scores.get(rid, 0.0),
            ))
    return results

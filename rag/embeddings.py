"""RAG 向量工具：对外统一接口，内部委托 embedding_provider。"""

from __future__ import annotations

import json

from rag.embedding_provider import (
    active_embedding_backend,
    cosine_similarity_dense,
    cosine_similarity_sparse,
    embed_query,
    embed_texts_batch,
    embedding_status,
    legacy_sparse_embed,
    parse_embedding_json,
    similarity,
)

__all__ = [
    "active_embedding_backend",
    "cosine_similarity",
    "embed_from_json",
    "embed_query_vector",
    "embed_text",
    "embed_texts_batch",
    "embed_to_json",
    "embedding_status",
    "legacy_sparse_embed",
    "parse_embedding_json",
]


def embed_text(text: str):
    _fmt, vec, _model = embed_query(text)
    return vec


def embed_query_vector(text: str):
    return embed_query(text)


def embed_to_json(text: str) -> str:
    batch = embed_texts_batch([text])
    return batch[0] if batch else json.dumps({"format": "sparse", "model": "legacy-tf", "vector": {}})


def embed_from_json(raw: str | None):
    _fmt, vec, _model = parse_embedding_json(raw)
    return vec


def cosine_similarity(a, b) -> float:
    if isinstance(a, list) and isinstance(b, list):
        return cosine_similarity_dense(a, b)
    if isinstance(a, dict) and isinstance(b, dict):
        return cosine_similarity_sparse(a, b)
    return 0.0

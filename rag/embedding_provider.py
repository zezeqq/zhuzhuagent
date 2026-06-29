"""RAG 向量提供者：本地 fastembed (bge-small-zh) / OpenAI 兼容 API / 词袋兜底。"""

from __future__ import annotations

import json
import logging
import re
import threading
from collections import Counter
from typing import Any

import httpx

from core.agent_context import default_model
from core.settings_store import get_setting

logger = logging.getLogger(__name__)

DENSE_FORMAT = "dense"
SPARSE_FORMAT = "sparse"
DEFAULT_LOCAL_MODEL = "BAAI/bge-small-zh-v1.5"
DEFAULT_API_MODEL = "text-embedding-3-small"
DEFAULT_OLLAMA_MODEL = "nomic-embed-text"
DEFAULT_OLLAMA_BASE = "http://localhost:11434"
_TOKEN_RE = re.compile(r"[\u4e00-\u9fff]|[a-zA-Z0-9_]+")

_local_model: Any | None = None
_local_model_name: str | None = None
_local_lock = threading.Lock()


def get_rag_embedding_provider() -> str:
    return (get_setting("rag_embedding_provider", "auto") or "auto").strip().lower()


def get_rag_embedding_model_local() -> str:
    return (get_setting("rag_embedding_model_local", DEFAULT_LOCAL_MODEL) or DEFAULT_LOCAL_MODEL).strip()


def get_rag_embedding_model_api() -> str:
    return (get_setting("rag_embedding_model_api", DEFAULT_API_MODEL) or DEFAULT_API_MODEL).strip()


def get_rag_embedding_api_base() -> str:
    return (get_setting("rag_embedding_api_base", "") or "").strip()


def get_rag_embedding_api_key() -> str:
    return (get_setting("rag_embedding_api_key", "") or "").strip()


def get_rag_embedding_ollama_base() -> str:
    return (get_setting("rag_embedding_ollama_base", DEFAULT_OLLAMA_BASE) or DEFAULT_OLLAMA_BASE).strip().rstrip("/")


def get_rag_embedding_model_ollama() -> str:
    return (get_setting("rag_embedding_model_ollama", DEFAULT_OLLAMA_MODEL) or DEFAULT_OLLAMA_MODEL).strip()


def active_embedding_backend() -> str:
    """返回当前实际会使用的后端：local | ollama | api | sparse。"""
    provider = get_rag_embedding_provider()
    if provider == "legacy":
        return "sparse"
    if provider == "local":
        return "local" if _can_use_local() else ("ollama" if _can_use_ollama() else "sparse")
    if provider == "ollama":
        return "ollama" if _can_use_ollama() else "sparse"
    if provider == "api":
        return "api" if _can_use_api() else "sparse"
    if _can_use_local():
        return "local"
    if _can_use_ollama():
        return "ollama"
    if _can_use_api():
        return "api"
    return "sparse"


def embedding_status() -> dict[str, Any]:
    backend = active_embedding_backend()
    return {
        "provider_setting": get_rag_embedding_provider(),
        "backend": backend,
        "local_model": get_rag_embedding_model_local(),
        "api_model": get_rag_embedding_model_api(),
        "ollama_model": get_rag_embedding_model_ollama(),
        "local_available": _can_use_local(),
        "ollama_available": _can_use_ollama(),
        "api_available": _can_use_api(),
    }


def _can_use_local() -> bool:
    try:
        import fastembed  # noqa: F401
        return True
    except ImportError:
        return False


def _can_use_api() -> bool:
    base, key = _resolve_api_credentials()
    if not base or not key:
        return False
    # 自动模式：若未单独配置 Embedding API，默认聊天模型（如 DeepSeek）往往不支持 /embeddings
    if get_rag_embedding_provider() == "auto":
        if get_rag_embedding_api_base() and get_rag_embedding_api_key():
            return True
        return False
    return True


def _resolve_api_credentials() -> tuple[str, str]:
    base = get_rag_embedding_api_base()
    key = get_rag_embedding_api_key()
    if base and key:
        return base.rstrip("/"), key
    model = default_model()
    if not model:
        return "", ""
    api_key = (model.get("api_key") or "").strip()
    api_base = (model.get("api_base") or "").strip().rstrip("/")
    return api_base, api_key


def _can_use_ollama() -> bool:
    try:
        resp = httpx.get(f"{get_rag_embedding_ollama_base()}/api/tags", timeout=2.0)
        return resp.status_code == 200
    except Exception:
        return False


def _get_local_embedder(model_name: str):
    global _local_model, _local_model_name
    with _local_lock:
        if _local_model is not None and _local_model_name == model_name:
            return _local_model
        from fastembed import TextEmbedding

        logger.info("Loading local embedding model: %s", model_name)
        _local_model = TextEmbedding(model_name=model_name)
        _local_model_name = model_name
        return _local_model


def _embed_local_batch(texts: list[str], model_name: str) -> list[list[float]]:
    embedder = _get_local_embedder(model_name)
    vectors: list[list[float]] = []
    for vec in embedder.embed(texts):
        vectors.append([float(x) for x in vec])
    return vectors


def _embed_api_batch(texts: list[str], model_name: str) -> list[list[float]]:
    api_base, api_key = _resolve_api_credentials()
    if not api_base or not api_key:
        raise RuntimeError("未配置 Embedding API（可在设置中填写 rag_embedding_api_base/key，或配置默认模型）")

    payload = {"model": model_name, "input": texts}
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    try:
        resp = httpx.post(f"{api_base}/embeddings", headers=headers, json=payload, timeout=120)
    except Exception as exc:
        raise RuntimeError(f"Embedding API 请求失败：{exc}") from exc
    if resp.status_code != 200:
        detail = resp.text[:500]
        try:
            detail = resp.json().get("error", {}).get("message", detail)
        except Exception:
            pass
        raise RuntimeError(f"Embedding API 错误（{resp.status_code}）：{detail}")

    data = resp.json().get("data") or []
    if len(data) != len(texts):
        raise RuntimeError("Embedding API 返回数量与输入不一致")
    ordered = sorted(data, key=lambda x: x.get("index", 0))
    return [[float(v) for v in item.get("embedding") or []] for item in ordered]


def _embed_ollama_batch(texts: list[str], model_name: str) -> list[list[float]]:
    base = get_rag_embedding_ollama_base()
    payload = {"model": model_name, "input": texts}
    try:
        resp = httpx.post(f"{base}/api/embed", json=payload, timeout=120)
    except Exception as exc:
        raise RuntimeError(f"Ollama Embedding 请求失败：{exc}") from exc
    if resp.status_code != 200:
        raise RuntimeError(f"Ollama Embedding 错误（{resp.status_code}）：{resp.text[:300]}")
    body = resp.json()
    embeddings = body.get("embeddings")
    if not isinstance(embeddings, list) or len(embeddings) != len(texts):
        raise RuntimeError("Ollama Embedding 返回格式异常")
    return [[float(x) for x in vec] for vec in embeddings]


def embed_texts_batch(texts: list[str]) -> list[str]:
    """批量生成 embedding_json 字符串（与 indexer 配套）。"""
    cleaned = [(t or "").strip() for t in texts]
    if not cleaned:
        return []

    backend = active_embedding_backend()
    if backend == "local":
        try:
            model_name = get_rag_embedding_model_local()
            vectors = _embed_local_batch(cleaned, model_name)
            return [_dense_to_json(model_name, vec) for vec in vectors]
        except Exception as exc:
            logger.warning("Local embedding failed, falling back: %s", exc)

    if backend in ("local", "ollama") or get_rag_embedding_provider() == "ollama":
        if _can_use_ollama():
            try:
                model_name = get_rag_embedding_model_ollama()
                vectors = _embed_ollama_batch(cleaned, model_name)
                return [_dense_to_json(f"ollama:{model_name}", vec) for vec in vectors]
            except Exception as exc:
                logger.warning("Ollama embedding failed, falling back: %s", exc)

    if backend in ("local", "ollama", "api") or get_rag_embedding_provider() in ("api", "auto"):
        base, key = _resolve_api_credentials()
        try_api = bool(base and key) and (
            get_rag_embedding_provider() == "api"
            or _can_use_api()
        )
        if try_api:
            try:
                model_name = get_rag_embedding_model_api()
                vectors = _embed_api_batch(cleaned, model_name)
                return [_dense_to_json(model_name, vec) for vec in vectors]
            except Exception as exc:
                logger.warning("API embedding failed, falling back: %s", exc)

    return [legacy_sparse_to_json(legacy_sparse_embed(t)) for t in cleaned]


def embed_query(text: str) -> tuple[str, list[float] | dict[str, float], str]:
    """检索用：返回 (format, vector, model_id)。"""
    batch = embed_texts_batch([text])
    if not batch:
        return SPARSE_FORMAT, {}, "sparse"
    fmt, model_id, vec = parse_embedding_json(batch[0])
    return fmt, vec, model_id


def _dense_to_json(model_name: str, vector: list[float]) -> str:
    return json.dumps({
        "format": DENSE_FORMAT,
        "model": model_name,
        "dim": len(vector),
        "vector": vector,
    }, ensure_ascii=False)


def legacy_sparse_to_json(sparse: dict[str, float]) -> str:
    return json.dumps({
        "format": SPARSE_FORMAT,
        "model": "legacy-tf",
        "vector": sparse,
    }, ensure_ascii=False)


def parse_embedding_json(raw: str | None) -> tuple[str, list[float] | dict[str, float], str]:
    if not raw:
        return SPARSE_FORMAT, {}, "unknown"
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return SPARSE_FORMAT, {}, "unknown"

    if isinstance(data, list):
        return DENSE_FORMAT, [float(x) for x in data], "legacy-list"

    if not isinstance(data, dict):
        return SPARSE_FORMAT, {}, "unknown"

    fmt = str(data.get("format") or "")
    model_id = str(data.get("model") or "unknown")

    if fmt == DENSE_FORMAT or "vector" in data and isinstance(data["vector"], list):
        vec_raw = data.get("vector")
        if isinstance(vec_raw, list):
            return DENSE_FORMAT, [float(x) for x in vec_raw], model_id

    if fmt == SPARSE_FORMAT:
        vec_raw = data.get("vector")
        if isinstance(vec_raw, dict):
            return SPARSE_FORMAT, {str(k): float(v) for k, v in vec_raw.items()}, model_id

    # 旧版词袋：{"词": 0.1, ...}
    if data and all(isinstance(k, str) for k in data.keys()) and "format" not in data:
        return SPARSE_FORMAT, {str(k): float(v) for k, v in data.items()}, "legacy-tf"

    return SPARSE_FORMAT, {}, model_id


def legacy_sparse_embed(text: str) -> dict[str, float]:
    tokens = _TOKEN_RE.findall((text or "").lower())
    if not tokens:
        return {}
    counts = Counter(tokens)
    total = float(sum(counts.values()))
    return {t: c / total for t, c in counts.items()}


def cosine_similarity_dense(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def cosine_similarity_sparse(a: dict[str, float], b: dict[str, float]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(a.get(k, 0.0) * b.get(k, 0.0) for k in a)
    na = sum(v * v for v in a.values()) ** 0.5
    nb = sum(v * v for v in b.values()) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def similarity(query_fmt: str, query_vec: Any, chunk_fmt: str, chunk_vec: Any) -> float:
    if query_fmt == DENSE_FORMAT and chunk_fmt == DENSE_FORMAT:
        if isinstance(query_vec, list) and isinstance(chunk_vec, list):
            return cosine_similarity_dense(query_vec, chunk_vec)
        return 0.0
    if query_fmt == SPARSE_FORMAT and chunk_fmt == SPARSE_FORMAT:
        if isinstance(query_vec, dict) and isinstance(chunk_vec, dict):
            return cosine_similarity_sparse(query_vec, chunk_vec)
        return 0.0
    return 0.0

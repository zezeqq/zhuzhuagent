"""Fetch remote Skill / Expert catalogs from network (JSON manifest + cache)."""

from __future__ import annotations

import json
import logging
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

from core.settings_store import get_setting, set_setting

logger = logging.getLogger(__name__)

_CACHE_TTL_SEC = 3600
_USER_AGENT = "Buddy-RemoteCatalog/1.0"

# 官方远程目录（GitHub Raw）；可在 设置→系统 覆盖
DEFAULT_REMOTE_CATALOG_URL = (
    "https://raw.githubusercontent.com/zezeqq/-agent/main/config/catalog.json"
)


def _cache_path() -> Path:
    from utils.path_utils import data_dir
    return data_dir() / "remote_catalog_cache.json"


def _jsdelivr_mirror(url: str) -> str | None:
    prefix = "https://raw.githubusercontent.com/"
    if not url.startswith(prefix):
        return None
    rest = url[len(prefix):].split("?", 1)[0]
    parts = rest.split("/", 2)
    if len(parts) < 3:
        return None
    user, repo, branch_and_path = parts[0], parts[1], parts[2]
    branch, _, filepath = branch_and_path.partition("/")
    if not branch or not filepath:
        return None
    return f"https://cdn.jsdelivr.net/gh/{user}/{repo}@{branch}/{filepath}"


def _fetch_json(url: str, timeout: float = 10.0, *, bust_cache: bool = False) -> dict:
    fetch_url = url
    if bust_cache:
        sep = "&" if "?" in url else "?"
        fetch_url = f"{url}{sep}_={int(time.time())}"

    candidates: list[str] = []
    mirror = _jsdelivr_mirror(url)
    if mirror:
        candidates.append(f"{mirror}?_={int(time.time())}" if bust_cache else mirror)
    candidates.append(fetch_url)

    last_exc: Exception | None = None
    best: dict | None = None
    for candidate in candidates:
        try:
            req = urllib.request.Request(
                candidate, headers={"User-Agent": _USER_AGENT, "Accept": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
            data = json.loads(raw)
            if not isinstance(data, dict):
                raise ValueError("远程目录必须是 JSON 对象（含 skills / experts 等字段）")
            if best is None:
                best = data
                continue
            # 优先 version 更高、或 hot_skills 更多的清单
            cur_hot = len(data.get("hot_skills") or [])
            best_hot = len(best.get("hot_skills") or [])
            cur_ver = int(data.get("version") or 0)
            best_ver = int(best.get("version") or 0)
            if cur_ver > best_ver or (cur_ver == best_ver and cur_hot > best_hot):
                best = data
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError, ValueError) as exc:
            last_exc = exc
            logger.debug("Catalog fetch failed for %s: %s", candidate, exc)
    if best is not None:
        return best
    raise ValueError("无法拉取远程目录")


def get_catalog_urls() -> list[str]:
    """支持多个远程 catalog URL（换行、逗号、分号分隔）。"""
    raw = get_setting("remote_catalog_url", "").strip()
    if not raw:
        return [DEFAULT_REMOTE_CATALOG_URL]
    parts = re.split(r"[\n,;|]+", raw)
    urls = [p.strip() for p in parts if p.strip()]
    return urls or [DEFAULT_REMOTE_CATALOG_URL]


def get_catalog_url() -> str:
    """状态栏展示用：单源返回 URL，多源返回摘要。"""
    urls = get_catalog_urls()
    if len(urls) == 1:
        return urls[0]
    return f"{urls[0]} 等 {len(urls)} 个源"


def ensure_catalog_url_configured() -> None:
    """首次启动写入默认远程目录 URL（用户可在设置中修改）。"""
    if not get_setting("remote_catalog_url", "").strip():
        set_setting("remote_catalog_url", DEFAULT_REMOTE_CATALOG_URL, "string")


def set_catalog_url(url: str) -> None:
    set_setting("remote_catalog_url", url.strip(), "string")


def _merge_manifest_payloads(payloads: list[tuple[str, dict]]) -> dict:
    """合并多个 catalog.json，按 name 去重；hot_rank 取更小者。"""
    merged_skills: dict[str, dict] = {}
    merged_hot: dict[str, dict] = {}
    merged_experts: dict[str, dict] = {}
    max_version = 0
    updated_at = ""
    source_urls: list[str] = []

    for url, data in payloads:
        source_urls.append(url)
        max_version = max(max_version, int(data.get("version") or 0))
        if data.get("updated_at"):
            updated_at = str(data["updated_at"])

        for s in data.get("hot_skills") or []:
            if not isinstance(s, dict) or not s.get("name"):
                continue
            key = str(s["name"]).lower()
            prev = merged_hot.get(key)
            if prev is None or int(s.get("hot_rank", 999)) < int(prev.get("hot_rank", 999)):
                merged_hot[key] = dict(s)

        for s in data.get("skills") or []:
            if not isinstance(s, dict) or not s.get("name"):
                continue
            key = str(s["name"]).lower()
            if key not in merged_skills:
                merged_skills[key] = dict(s)

        for e in data.get("experts") or []:
            if not isinstance(e, dict) or not e.get("name"):
                continue
            key = str(e["name"])
            if key not in merged_experts:
                merged_experts[key] = dict(e)

    hot_list = sorted(merged_hot.values(), key=lambda x: int(x.get("hot_rank", 999)))
    return {
        "version": max_version,
        "updated_at": updated_at,
        "skills": list(merged_skills.values()),
        "hot_skills": hot_list,
        "experts": list(merged_experts.values()),
        "fetched_at": time.time(),
        "source_url": ", ".join(source_urls),
        "source_urls": source_urls,
    }


def load_cached_catalog() -> dict | None:
    path = _cache_path()
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def cached_remote_manifest() -> dict:
    """UI 线程安全：只读本地缓存，不发起网络请求。"""
    return load_cached_catalog() or {
        "skills": [],
        "hot_skills": [],
        "experts": [],
        "fetched_at": 0,
        "source_url": "",
    }


def _normalize_remote_skill(rs: dict) -> dict:
    entry = dict(rs)
    entry.setdefault("skill_type", "prompt")
    entry.setdefault("category", "远程")
    entry.setdefault("icon", "🌐")
    entry.setdefault("tags", [])
    entry["remote"] = True
    return entry


def list_hot_remote_skills() -> list[dict]:
    """远程热门 Skill（来自 catalog hot_skills，按 hot_rank 排序）。"""
    manifest = cached_remote_manifest()
    hot = manifest.get("hot_skills") or []
    if hot:
        items = [_normalize_remote_skill(s) for s in hot if isinstance(s, dict) and s.get("name")]
    else:
        items = [
            _normalize_remote_skill(s)
            for s in manifest.get("skills", [])
            if isinstance(s, dict) and s.get("name") and (s.get("hot") or s.get("featured"))
        ]
    items.sort(key=lambda s: int(s.get("hot_rank", 999)))
    return items


def list_hot_remote_experts(local_experts: list[dict]) -> list[dict]:
    """远程热门专家（hot 标记或 provider 含远程）。"""
    merged = remote_experts_merged_with_local(local_experts)
    hot = [e for e in merged if e.get("hot") or e.get("remote")]
    return hot[:8]


def fetch_remote_catalog(*, force: bool = False) -> dict:
    """Return merged remote manifest; uses disk cache when fresh."""
    urls = get_catalog_urls()
    if not urls:
        cached = load_cached_catalog()
        return cached or {"skills": [], "experts": [], "fetched_at": 0, "source_url": ""}

    cache_key = "|".join(urls)

    if not force:
        cached = load_cached_catalog()
        cached_key = "|".join(cached.get("source_urls") or []) if cached else ""
        if not cached_key and cached:
            cached_key = cached.get("source_url") or ""
        if cached and cached_key == cache_key:
            age = time.time() - float(cached.get("fetched_at") or 0)
            if age < _CACHE_TTL_SEC:
                return cached

    payloads: list[tuple[str, dict]] = []
    errors: list[str] = []
    for url in urls:
        try:
            data = _fetch_json(url, bust_cache=force)
            payloads.append((url, data))
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError, ValueError) as exc:
            errors.append(f"{url}: {exc}")
            logger.warning("Remote catalog fetch failed for %s: %s", url, exc)

    if not payloads:
        cached = load_cached_catalog()
        if cached:
            cached["fetch_error"] = "; ".join(errors) if errors else "无法拉取远程目录"
            return cached
        raise ValueError(errors[0] if errors else "无法拉取远程目录")

    payload = _merge_manifest_payloads(payloads)
    if errors:
        payload["fetch_error"] = "; ".join(errors)
    _cache_path().write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    set_setting("remote_catalog_last_fetch", str(int(payload["fetched_at"])), "string")
    n_hot = len(payload["hot_skills"])
    logger.info(
        "Remote catalog fetched from %d source(s): %d hot, %d skills, %d experts",
        len(payloads), n_hot, len(payload["skills"]), len(payload["experts"]),
    )
    return payload


def _load_bundled_skill_md(name: str) -> str:
    try:
        from utils.path_utils import app_root
        path = app_root() / "config" / "bundled_skills" / f"{name}.md"
        if path.is_file():
            return path.read_text(encoding="utf-8").strip()
    except Exception:
        pass
    return ""


def _load_bundled_catalog_skills() -> list[dict]:
    """应用内置 catalog.json + bundled_skills/*.md（GitHub 未更新时仍可用完整 Skill）。"""
    try:
        from utils.path_utils import app_root
        path = app_root() / "config" / "catalog.json"
        if not path.is_file():
            return []
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    items: list[dict] = []
    for rs in (data.get("hot_skills") or []) + (data.get("skills") or []):
        if isinstance(rs, dict) and rs.get("name"):
            entry = _normalize_remote_skill(rs)
            md = _load_bundled_skill_md(str(rs["name"]))
            if md:
                entry["skill_md"] = md
            entry["bundled"] = True
            items.append(entry)
    return items


def all_network_catalog_skills() -> list[dict]:
    """合并远程缓存 + 内置 catalog；占位项被内置完整版覆盖。"""
    from core.skill_catalog import is_catalog_stub

    manifest = cached_remote_manifest()
    by_name: dict[str, dict] = {}
    for rs in (manifest.get("hot_skills") or []) + (manifest.get("skills") or []):
        if not isinstance(rs, dict) or not rs.get("name"):
            continue
        key = str(rs["name"]).lower().replace(" ", "_")
        by_name[key] = _normalize_remote_skill(rs)

    bundled_list = _load_bundled_catalog_skills()
    for bs in bundled_list:
        key = str(bs["name"]).lower().replace(" ", "_")
        prev = by_name.get(key)
        if prev is None or is_catalog_stub(prev):
            if not is_catalog_stub(bs):
                by_name[key] = bs
        elif bs.get("bundled") and not is_catalog_stub(bs):
            by_name[key] = bs

    for bs in bundled_list:
        key = str(bs["name"]).lower().replace(" ", "_")
        if key not in by_name and not is_catalog_stub(bs):
            by_name[key] = bs

    items = list(by_name.values())
    items.sort(key=lambda s: (int(s.get("hot_rank", 9999)), s.get("display", "")))
    return items


def remote_skills_merged_with_local() -> list[dict]:
    """兼容旧名：仅返回远程 Skill 列表。"""
    return all_network_catalog_skills()


def remote_experts_merged_with_local(local_experts: list[dict]) -> list[dict]:
    """Local EXPERTS + remote experts list."""
    by_name: dict[str, dict] = {}
    for e in local_experts:
        by_name[e.get("name", "")] = dict(e)

    try:
        remote = cached_remote_manifest()
    except Exception:
        remote = {"experts": []}

    for re in remote.get("experts") or []:
        if not isinstance(re, dict) or not re.get("name"):
            continue
        by_name[re["name"]] = {
            "name": re["name"],
            "provider": re.get("provider", "远程"),
            "desc": re.get("desc", re.get("description", "")),
            "tags": re.get("tags", []),
            "category": re.get("category", "远程"),
            "prompt": re.get("prompt", re.get("system_prompt", "")),
            "remote": True,
            "hot": bool(re.get("hot")),
            "kind": "expert",
            "recommended_skills": re.get("recommended_skills") or [],
        }

    return list(by_name.values())

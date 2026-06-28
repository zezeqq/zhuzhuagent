"""联网发现 Skill（GitHub 等）与目录内相似推荐。"""

from __future__ import annotations

import json
import logging
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

logger = logging.getLogger(__name__)

_USER_AGENT = "Buddy-SkillDiscovery/1.0"
_TRENDING_CACHE_TTL_SEC = 3600

# 翻译结果短缓存，避免重复请求
_translate_cache: dict[str, str] = {}

# 高星但通常不是「可直接安装的 Skill 包」
_NOISE_NAME_RE = re.compile(
    r"(awesome|daily|list|backup|collection|learn|tutorial|book|index|agents?-index|"
    r"openclaw|lobe-chat|starry|divine|prompt-engineering|aigc)",
    re.I,
)

_EN_STOPWORDS = frozenset({
    "the", "and", "for", "with", "from", "that", "this", "your", "are", "was",
    "have", "has", "will", "can", "not", "you", "our", "all", "any", "into",
})


def _latin_tokens(text: str) -> list[str]:
    return [m.group().lower() for m in re.finditer(r"[a-z0-9]{2,}", text.lower())]


def _translate_to_english(text: str) -> str:
    """中文查询自动译成英文（免费公共 API，失败则返回空串）。"""
    if not re.search(r"[\u4e00-\u9fff]", text):
        return ""

    key = text.strip()
    if not key:
        return ""
    if key in _translate_cache:
        return _translate_cache[key]

    url = (
        "https://api.mymemory.translated.net/get?"
        + urllib.parse.urlencode({"q": key[:500], "langpair": "zh-CN|en"})
    )
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
        translated = (data.get("responseData") or {}).get("translatedText") or ""
        translated = translated.strip()
        if translated.upper() == key.upper():
            translated = ""
        _translate_cache[key] = translated
        return translated
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError, KeyError) as exc:
        logger.debug("Translate failed for %r: %s", key, exc)
        _translate_cache[key] = ""
        return ""


def expand_search_terms(query: str) -> list[str]:
    """
    把用户输入拆成检索词：
    - 保留原始 query（供本地中文 catalog 匹配）
    - 提取英文/数字 token（ppt、sql、docker…）
    - 含中文时自动翻译，再拆英文词（无需写死别名表）
    """
    q = query.strip()
    if not q:
        return []

    terms: list[str] = []
    seen: set[str] = set()

    def add(t: str):
        t = t.strip().lower()
        if len(t) < 2 or t in seen:
            return
        seen.add(t)
        terms.append(t)

    add(q.lower())
    for tok in _latin_tokens(q):
        add(tok)

    translated = _translate_to_english(q)
    if translated:
        add(translated.lower())
        for tok in _latin_tokens(translated):
            add(tok)
        for word in re.findall(r"[a-z]{3,}", translated.lower()):
            if word not in _EN_STOPWORDS:
                add(word)

    return terms[:16]


def explain_search_expansion(query: str) -> str:
    """供 UI 展示：用户输入如何被扩展（透明，非写死别名）。"""
    q = query.strip()
    if not q:
        return ""
    translated = _translate_to_english(q) if re.search(r"[\u4e00-\u9fff]", q) else ""
    latin = _latin_tokens(q)
    parts = []
    if translated:
        parts.append(f"译英「{translated}」")
    if latin:
        parts.append("英文词 " + "/".join(latin[:6]))
    if not parts:
        parts.append("原词检索")
    return " · ".join(parts)


def _github_friendly_terms(terms: list[str]) -> list[str]:
    """GitHub API 检索用 ASCII 词。"""
    out: list[str] = []
    seen: set[str] = set()
    for t in terms:
        if re.match(r"^[a-z0-9][a-z0-9_-]{0,48}$", t) and t not in seen:
            seen.add(t)
            out.append(t)
        elif re.match(r"^[a-z0-9][a-z0-9 _-]{0,80}$", t):
            for piece in t.split():
                if re.match(r"^[a-z0-9][a-z0-9_-]{0,48}$", piece) and piece not in seen:
                    seen.add(piece)
                    out.append(piece)
    return out


def _build_github_queries(query: str, terms: list[str]) -> list[str]:
    """根据扩展词动态生成 2～3 条 GitHub 检索式（无固定主题表）。"""
    latin = _github_friendly_terms(terms) or _latin_tokens(query)
    queries: list[str] = []
    seen_q: set[str] = set()

    def push(q: str):
        q = q.strip()
        if q and q not in seen_q:
            seen_q.add(q)
            queries.append(q)

    translated = _translate_to_english(query) if re.search(r"[\u4e00-\u9fff]", query) else ""
    if translated:
        phrase = " ".join(_latin_tokens(translated)[:6]) or translated.lower()
        if phrase:
            push(f"{phrase} in:name,description")

    if latin:
        core = " ".join(latin[:5])
        push(f"{core} in:name,description")
        push(f"{core} skill in:name,description")

    if not queries and latin:
        push(f"{latin[0]} in:name,description")

    return queries[:3]


def _github_api_search(search_q: str, *, per_page: int = 50, page: int = 1) -> list[dict]:
    per_page = max(1, min(per_page, 100))
    page = max(1, min(page, 10))
    url = (
        "https://api.github.com/search/repositories"
        f"?q={urllib.parse.quote(search_q)}&sort=stars&order=desc"
        f"&per_page={per_page}&page={page}"
    )
    req = urllib.request.Request(
        url,
        headers={"User-Agent": _USER_AGENT, "Accept": "application/vnd.github+json"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8", errors="replace"))
    return [it for it in (data.get("items") or []) if isinstance(it, dict)]


def _relevance_score(item: dict, terms: list[str], original: str) -> int:
    name = (item.get("name") or "").lower()
    desc = (item.get("description") or "").lower()
    full = (item.get("full_name") or "").lower()
    blob = f"{name} {desc} {full}"
    orig = original.lower()

    score = 0

    for term in terms:
        if len(term) < 2:
            continue
        if term in name:
            score += 18
        elif term in desc:
            score += 12
        elif term in blob:
            score += 6

    if orig in name or orig in desc:
        score += 25
    for part in re.findall(r"[\u4e00-\u9fff]{2,}|[a-z0-9]{2,}", orig):
        if part in name:
            score += 8
        elif part in desc:
            score += 5

    if "skill" in name or "skill.md" in desc:
        score += 4

    if _NOISE_NAME_RE.search(name):
        score -= 35
    if name.startswith("awesome-"):
        score -= 40
    if "backup" in name or "list" in name:
        score -= 15

    stars = int(item.get("stargazers_count") or 0)
    if stars > 0:
        score += min(8, stars.bit_length())

    return score


def _github_repo_to_skill(item: dict, *, relevance: int = 0, trending: bool = False) -> dict:
    full_name = item.get("full_name") or item.get("name") or "unknown"
    slug = re.sub(r"[^a-z0-9_]+", "_", full_name.lower()).strip("_")
    branch = item.get("default_branch") or "main"
    tags = ["GitHub", "网络热门"] if trending else ["GitHub", "联网发现"]
    return {
        "name": f"github_{slug}"[:64],
        "display": item.get("name") or full_name,
        "desc": (item.get("description") or "GitHub 仓库（联网发现）")[:200],
        "category": "远程",
        "icon": "🌐",
        "skill_type": "prompt",
        "tags": tags,
        "discovered": True,
        "trending": trending,
        "remote": True,
        "source_url": item.get("html_url", ""),
        "install_url": f"https://github.com/{full_name}/archive/refs/heads/{branch}.zip",
        "skill_md": (
            f"# {item.get('name', full_name)}\n\n"
            f"{item.get('description') or '来自 GitHub 的 Skill 包，安装后从仓库读取 SKILL.md。'}\n\n"
            f"来源：{item.get('html_url', '')}\n"
        ),
        "stars": item.get("stargazers_count", 0),
        "_relevance": relevance,
    }


def _trending_cache_path() -> Path:
    from utils.path_utils import data_dir
    return data_dir() / "trending_skills_cache.json"


def _load_trending_cache() -> dict | None:
    path = _trending_cache_path()
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        age = time.time() - float(data.get("fetched_at") or 0)
        if age < _TRENDING_CACHE_TTL_SEC and data.get("skills"):
            return data
    except Exception:
        pass
    return None


def _save_trending_cache(skills: list[dict]) -> None:
    path = _trending_cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"fetched_at": time.time(), "skills": skills}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_trending_cache() -> dict | None:
    return _load_trending_cache()


_EXPERT_DOMAIN_CACHE_TTL_SEC = 3600


def _expert_domain_cache_path() -> Path:
    from utils.path_utils import data_dir
    return data_dir() / "expert_domain_skills_cache.json"


def _load_expert_domain_cache() -> dict:
    path = _expert_domain_cache_path()
    if not path.is_file():
        return {"experts": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data.get("experts"), dict):
            return data
    except Exception:
        pass
    return {"experts": {}}


def _save_expert_domain_cache(expert_key: str, query: str, skills: list[dict]) -> None:
    path = _expert_domain_cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = _load_expert_domain_cache()
    experts = data.setdefault("experts", {})
    experts[expert_key] = {
        "query": query,
        "fetched_at": time.time(),
        "skills": skills,
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def fetch_github_skills_for_expert(item: dict, *, limit: int = 8, force: bool = False) -> tuple[str, list[dict]]:
    """
    按专家工作方向在 GitHub 搜索相关 Skill，返回 (检索词, 结果列表)。
    结果带 _relevance，供专家预览「方向热门」组使用。
    """
    from core.expert_catalog import expert_github_search_query

    limit = max(1, min(limit, 20))
    expert_key = (item.get("name") or "unknown").strip()
    query = expert_github_search_query(item)

    if not force:
        cached = _load_expert_domain_cache()
        entry = (cached.get("experts") or {}).get(expert_key)
        if entry:
            age = time.time() - float(entry.get("fetched_at") or 0)
            if age < _EXPERT_DOMAIN_CACHE_TTL_SEC and entry.get("skills"):
                return str(entry.get("query") or query), list(entry["skills"])[:limit]

    skills = search_github_skills(query, limit=limit)
    for s in skills:
        s["domain_matched"] = True
        s["expert_name"] = expert_key
    if skills:
        _save_expert_domain_cache(expert_key, query, skills)
    return query, skills


def fetch_trending_github_skills(*, limit: int = 100, force: bool = False) -> list[dict]:
    """拉取 GitHub 上高星 Agent/Skill 相关仓库作为「网络热门」列表。"""
    limit = max(1, min(limit, 100))
    if not force:
        cached = _load_trending_cache()
        if cached:
            return list(cached.get("skills") or [])[:limit]

    queries = [
        "agent skill stars:>100",
        "cursor skill stars:>50",
        "mcp skill stars:>30",
        "claude skill agent stars:>20",
    ]
    merged: dict[str, dict] = {}
    errors: list[str] = []

    for search_q in queries:
        try:
            items = _github_api_search(search_q, per_page=50, page=1)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as exc:
            logger.debug("Trending query failed (%s): %s", search_q, exc)
            errors.append(str(exc))
            continue
        for it in items:
            key = (it.get("full_name") or it.get("name") or "").lower()
            if not key:
                continue
            name = (it.get("name") or "").lower()
            if _NOISE_NAME_RE.search(name):
                continue
            stars = int(it.get("stargazers_count") or 0)
            prev = merged.get(key)
            if prev is None or stars > int(prev["item"].get("stargazers_count") or 0):
                merged[key] = {"item": it, "_score": stars}

    if not merged and errors:
        raise RuntimeError(f"GitHub 热门 Skill 拉取失败：{errors[0]}")

    ranked = sorted(
        merged.values(),
        key=lambda x: -int(x["item"].get("stargazers_count") or 0),
    )
    picked = ranked[:limit]
    skills = [_github_repo_to_skill(x["item"], relevance=x["_score"], trending=True) for x in picked]
    if skills:
        _save_trending_cache(skills)
    return skills


def search_github_skills(query: str, *, limit: int = 100) -> list[dict]:
    """在 GitHub 搜索与关键词相关的 Skill/Agent 仓库，按相关度重排（最多 limit 条）。"""
    q = query.strip()
    if not q:
        return []

    limit = max(1, min(limit, 100))
    terms = expand_search_terms(q)
    queries = _build_github_queries(q, terms)

    merged: dict[str, dict] = {}
    errors: list[str] = []

    for search_q in queries:
        for page in (1, 2):
            try:
                items = _github_api_search(search_q, per_page=50, page=page)
            except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as exc:
                logger.debug("GitHub query failed (%s p%d): %s", search_q, page, exc)
                if page == 1:
                    errors.append(str(exc))
                continue
            if not items:
                break
            for it in items:
                key = (it.get("full_name") or it.get("name") or "").lower()
                if not key:
                    continue
                score = _relevance_score(it, terms, q)
                prev = merged.get(key)
                if prev is None or score > prev["_score"]:
                    merged[key] = {"item": it, "_score": score}
            if len(merged) >= limit * 2:
                break

    if not merged and errors:
        raise RuntimeError(f"GitHub 搜索失败：{errors[0]}")

    ranked = sorted(
        merged.values(),
        key=lambda x: (-x["_score"], -int(x["item"].get("stargazers_count") or 0)),
    )
    min_score = 4
    picked = [x for x in ranked if x["_score"] >= min_score][:limit]

    if len(picked) < min(10, limit):
        picked = [
            x for x in ranked
            if x["_score"] >= 0 and not _NOISE_NAME_RE.search((x["item"].get("name") or ""))
        ][:limit]

    if not picked and ranked:
        picked = ranked[:limit]

    return [_github_repo_to_skill(x["item"], relevance=x["_score"]) for x in picked]


def find_similar_in_catalog(query: str, catalog_skills: list[dict], *, limit: int = 6) -> list[dict]:
    """在已缓存目录中按标签/名称/描述推荐相似 Skill。"""
    q = query.strip().lower()
    if not q:
        return []

    terms = expand_search_terms(q)
    scored: list[tuple[int, dict]] = []

    for s in catalog_skills:
        tags = " ".join(str(t).lower() for t in (s.get("tags") or []))
        blob = " ".join([
            s.get("name", ""),
            s.get("display", ""),
            s.get("desc", ""),
            s.get("category", ""),
            s.get("skill_md", "")[:200],
            tags,
        ]).lower()

        score = 0
        if q in s.get("display", "").lower() or q in s.get("name", "").lower():
            score += 20
        if q in tags or q in s.get("desc", "").lower():
            score += 12
        for term in terms:
            if term in s.get("display", "").lower() or term in s.get("name", "").lower():
                score += 10
            elif term in tags:
                score += 9
            elif term in s.get("desc", "").lower() or term in blob:
                score += 5
        if score > 0:
            scored.append((score, s))

    scored.sort(key=lambda x: (-x[0], x[1].get("hot_rank", 9999)))
    seen: set[str] = set()
    out: list[dict] = []
    for _, s in scored:
        key = s.get("name", "")
        if key in seen:
            continue
        seen.add(key)
        entry = dict(s)
        entry["similar"] = True
        out.append(entry)
        if len(out) >= limit:
            break
    return out

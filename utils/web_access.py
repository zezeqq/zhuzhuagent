"""联网搜索与网页抓取（内置工具，不依赖 MCP）。"""

from __future__ import annotations

import html as html_module
import re
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlparse

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36 DNA-Work-Agent/1.0"
)


class _HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("script", "style", "noscript"):
            self._skip_depth += 1
        elif self._skip_depth == 0 and tag in ("p", "div", "br", "li", "h1", "h2", "h3", "h4", "tr"):
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style", "noscript") and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        text = data.strip()
        if text:
            self._parts.append(text)

    def get_text(self) -> str:
        raw = " ".join(self._parts)
        raw = html_module.unescape(raw)
        raw = re.sub(r"[ \t]+\n", "\n", raw)
        raw = re.sub(r"\n{3,}", "\n\n", raw)
        return re.sub(r" {2,}", " ", raw).strip()


def html_to_text(content: str) -> str:
    parser = _HTMLTextExtractor()
    try:
        parser.feed(content)
        parser.close()
    except Exception:
        return re.sub(r"<[^>]+>", " ", content)
    return parser.get_text()


def extract_html_title(content: str) -> str:
    match = re.search(r"<title[^>]*>(.*?)</title>", content, re.I | re.S)
    if not match:
        return ""
    return html_module.unescape(re.sub(r"\s+", " ", match.group(1))).strip()


def _normalize_url(url: str) -> str:
    raw = (url or "").strip()
    if not raw:
        raise ValueError("URL 不能为空")
    if not re.match(r"^https?://", raw, re.I):
        raw = "https://" + raw
    parsed = urlparse(raw)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("仅支持 http/https URL")
    return raw


def fetch_web_page(url: str, *, max_chars: int = 12000, timeout: float = 25.0) -> dict[str, Any]:
    import httpx

    target = _normalize_url(url)
    headers = {"User-Agent": _USER_AGENT, "Accept": "text/html,application/xhtml+xml,*/*;q=0.8"}
    with httpx.Client(follow_redirects=True, timeout=timeout, headers=headers) as client:
        resp = client.get(target)
        resp.raise_for_status()
        final_url = str(resp.url)
        ctype = (resp.headers.get("content-type") or "").lower()
        body = resp.text
        if "html" in ctype or "<html" in body[:800].lower():
            title = extract_html_title(body)
            text = html_to_text(body)
        else:
            title = final_url
            text = body
        if len(text) > max_chars:
            text = text[:max_chars] + "\n\n…(内容已截断)"
        return {"url": final_url, "title": title or final_url, "text": text}


def search_web(query: str, *, max_results: int = 8) -> list[dict[str, str]]:
    q = (query or "").strip()
    if not q:
        return []
    max_results = max(1, min(int(max_results), 12))

    for import_path in ("ddgs", "duckduckgo_search"):
        try:
            mod = __import__(import_path, fromlist=["DDGS"])
            ddgs_cls = mod.DDGS
            with ddgs_cls() as ddgs:
                rows = list(ddgs.text(q, max_results=max_results))
            out = _normalize_search_rows(rows)
            if out:
                return out
        except ImportError:
            continue
        except Exception:
            continue

    return _search_duckduckgo_instant(q, max_results)


def _normalize_search_rows(rows: list) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        href = str(row.get("href") or row.get("url") or "").strip()
        if not href:
            continue
        out.append({
            "title": str(row.get("title") or "无标题"),
            "url": href,
            "snippet": str(row.get("body") or row.get("snippet") or "")[:600],
        })
    return out


def _search_duckduckgo_instant(query: str, max_results: int) -> list[dict[str, str]]:
    """无 duckduckgo-search 包时的轻量兜底（结果较少）。"""
    import httpx

    url = "https://api.duckduckgo.com/"
    params = {"q": query, "format": "json", "no_redirect": "1", "no_html": "1"}
    with httpx.Client(timeout=15.0, headers={"User-Agent": _USER_AGENT}) as client:
        resp = client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()

    results: list[dict[str, str]] = []
    abstract = (data.get("AbstractText") or "").strip()
    abstract_url = (data.get("AbstractURL") or "").strip()
    if abstract:
        results.append({
            "title": data.get("Heading") or query,
            "url": abstract_url or f"https://duckduckgo.com/?q={query}",
            "snippet": abstract,
        })
    for item in data.get("RelatedTopics") or []:
        if len(results) >= max_results:
            break
        if isinstance(item, dict) and item.get("Text") and item.get("FirstURL"):
            results.append({
                "title": str(item["Text"]).split(" - ")[0][:120],
                "url": str(item["FirstURL"]),
                "snippet": str(item["Text"])[:600],
            })
    return results[:max_results]


def format_search_results(query: str, results: list[dict[str, str]]) -> str:
    if not results:
        return (
            f"联网搜索「{query}」未返回结果。"
            "请换关键词重试，或对已知 URL 使用 web_fetch。"
        )
    lines = [f"# 联网搜索：{query}", ""]
    for idx, row in enumerate(results, 1):
        lines.append(f"## [{idx}] {row.get('title') or '无标题'}")
        lines.append(row.get("url") or "")
        snippet = (row.get("snippet") or "").strip()
        if snippet:
            lines.append(snippet)
        lines.append("")
    return "\n".join(lines).strip()

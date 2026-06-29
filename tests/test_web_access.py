"""联网搜索与网页抓取。"""

from __future__ import annotations

from agent_runtime.tool_executor import execute_tool


def test_web_search_empty_query(app_tmp, monkeypatch):
    result = execute_tool("web_search", {"query": ""})
    assert "错误" in result


def test_web_search_formats_results(app_tmp, monkeypatch):
    monkeypatch.setattr(
        "utils.web_access.search_web",
        lambda query, max_results=8: [
            {"title": "LMSYS Arena", "url": "https://example.com/lmsys", "snippet": "排行榜"},
        ],
    )
    result = execute_tool("web_search", {"query": "LMSYS arena"})
    assert "# 联网搜索" in result
    assert "LMSYS Arena" in result
    assert "example.com" in result


def test_web_fetch(app_tmp, monkeypatch):
    monkeypatch.setattr(
        "utils.web_access.fetch_web_page",
        lambda url, max_chars=12000, timeout=25.0: {
            "url": url,
            "title": "测试页",
            "text": "正文内容",
        },
    )
    result = execute_tool("web_fetch", {"url": "https://example.com"})
    assert "测试页" in result
    assert "正文内容" in result


def test_html_to_text():
    from utils.web_access import html_to_text

    text = html_to_text("<html><body><h1>Hi</h1><p>World</p><script>x</script></body></html>")
    assert "Hi" in text
    assert "World" in text
    assert "x" not in text

"""library_search 工具与检索格式化。"""

from __future__ import annotations

from agent_runtime.tool_executor import execute_tool


def test_library_search_empty_query(app_tmp, sample_project, monkeypatch):
    monkeypatch.setattr("core.agent_context.current_project", lambda: sample_project)
    result = execute_tool("library_search", {"query": ""})
    assert "错误" in result


def test_library_search_formats_mock_results(app_tmp, sample_project, monkeypatch):
    monkeypatch.setattr("core.agent_context.current_project", lambda: sample_project)
    monkeypatch.setattr(
        "rag.retriever.search_chunks",
        lambda query, project_id=None, include_standards=True, limit=6: [
            {"file_name": "规范.pdf", "page_number": 3, "content": "机电工程验收要求"},
            {"file_name": "方案.docx", "content": "施工组织设计要点"},
        ],
    )
    result = execute_tool("library_search", {"query": "机电验收"})
    assert "# 资料库检索" in result
    assert "[1]" in result
    assert "规范.pdf" in result


def test_library_search_no_results(app_tmp, sample_project, monkeypatch):
    monkeypatch.setattr("core.agent_context.current_project", lambda: sample_project)
    monkeypatch.setattr("rag.retriever.search_chunks", lambda *a, **k: [])
    result = execute_tool("library_search", {"query": "不存在的内容"})
    assert "未检索到" in result


def test_keyword_search_hits_db_chunk(app_tmp, sample_project):
    from db.database import insert
    from rag.retriever import search_chunks

    insert(
        "file_chunks",
        {
            "project_id": sample_project["id"],
            "content": "公路工程质量检验评定标准 机电工程章节",
            "keywords": "机电,验收",
            "source_type": "file",
        },
    )
    hits = search_chunks("机电工程", project_id=sample_project["id"], limit=3)
    assert hits
    assert "机电" in hits[0].get("content", "")


def test_finance_query_filters_highway_income_noise(app_tmp, sample_project):
    from db.database import insert
    from rag.retriever import search_chunks

    insert(
        "file_chunks",
        {
            "project_id": sample_project["id"],
            "content": "打印报表功能测试：通行费收入的班次日月年报表",
            "keywords": "收费,报表",
            "source_type": "file",
        },
    )
    insert(
        "file_chunks",
        {
            "project_id": sample_project["id"],
            "content": "财务分析模板：收入、成本、利润与预算说明",
            "keywords": "财务,分析,模板",
            "source_type": "file",
        },
    )
    hits = search_chunks(
        "财务分析模板 收入 成本 利润",
        project_id=sample_project["id"],
        limit=3,
        use_vector=False,
    )
    assert hits
    assert "财务" in hits[0].get("content", "")

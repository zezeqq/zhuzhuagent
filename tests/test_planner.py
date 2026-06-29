"""规则 Planner 与 JSON 解析。"""

from __future__ import annotations

from agent_runtime.planner import Planner, _extract_json_object, plan_from_confirmed_markdown, plan_with_llm
from agent_runtime.task_state import TaskPlan


def test_plan_generate_ppt(sample_project):
    plan = Planner().plan("帮我生成投标 PPT", sample_project)
    assert plan.task_type == "agent_craft"
    assert plan.steps[0].tool == "agent.execute"


def test_plan_generate_excel(sample_project):
    plan = Planner().plan("生成项目资料清单 Excel 表格", sample_project)
    assert plan.task_type == "agent_craft"
    assert plan.steps[0].tool == "agent.execute"


def test_plan_custom_topic_uses_agent(sample_project):
    plan = Planner().plan("帮我做一个关于大模型排名统计的excel表和word版", sample_project)
    assert plan.task_type == "agent_craft"
    assert plan.steps[0].tool == "agent.execute"


def test_plan_generate_word(sample_project):
    plan = Planner().plan("帮我写一份施工组织设计 Word 文档", sample_project)
    assert plan.task_type == "agent_craft"
    assert plan.steps[0].tool == "agent.execute"


def test_plan_launch_chrome(sample_project, chrome_software):
    plan = Planner().plan("打开 Chrome 浏览器", sample_project)
    assert plan.task_type == "launch_software"
    assert plan.steps[0].tool == "software.launch"
    assert plan.steps[0].input["software_id"] == chrome_software


def test_plan_launch_unconfigured(sample_project):
    plan = Planner().plan("打开 Chrome", sample_project)
    assert plan.task_type == "launch_software_failed"
    assert plan.steps == []


def test_plan_vague_goal_falls_through_to_agent(sample_project):
    plan = Planner().plan("你觉得这个方案怎么样？", sample_project)
    assert plan.task_type == "agent_craft"
    assert plan.steps[0].tool == "agent.execute"


def test_plan_financial_analysis_uses_agent(sample_project):
    plan = Planner().plan("帮我做一份简单的财务分析", sample_project)
    assert plan.task_type == "agent_craft"
    assert plan.steps[0].tool == "agent.execute"


def test_sanitize_empty_excel_plan_to_agent(sample_project):
    from agent_runtime.planner import _sanitize_plan_steps
    from agent_runtime.task_state import TaskPlan, TaskStep

    plan = TaskPlan(
        title="生成财务分析报告",
        task_type="generate_excel",
        user_goal="做财务分析",
        steps=[
            TaskStep("检索", "library_search", {"query": "财务模板"}, "low"),
            TaskStep("生成", "office.excel.create", {"output_name": "workbook.xlsx"}, "medium"),
        ],
    )
    fixed = _sanitize_plan_steps(plan)
    assert fixed.steps[0].tool == "agent.execute"


def test_extract_json_object_from_codeblock():
    raw = '```json\n{"title": "测试", "steps": []}\n```'
    data = _extract_json_object(raw)
    assert data["title"] == "测试"


def test_plan_from_confirmed_markdown(sample_project):
    md = "# 我的计划\n\n1. 查资料\n2. 写文档"
    plan = plan_from_confirmed_markdown("执行计划", md, sample_project)
    assert plan.task_type == "plan_execute"
    assert plan.steps[0].tool == "agent.execute"
    assert "查资料" in plan.steps[0].input.get("plan_context", "")


def test_plan_with_llm_delegates_to_agent(sample_project):
    plan = plan_with_llm("生成投标技术方案汇报 PPT", {"model_name": "fake"}, sample_project, rule_first=True)
    assert plan.task_type == "agent_craft"
    assert plan.steps[0].tool == "agent.execute"

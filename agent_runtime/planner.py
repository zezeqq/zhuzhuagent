from __future__ import annotations

import re
from datetime import datetime

from agent_runtime.task_state import TaskPlan, TaskStep
from db.database import query_one


def _stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


SOFTWARE_ALIASES = {
    "vscode": "VS Code", "vs code": "VS Code",
    "pycharm": "PyCharm",
    "chrome": "Chrome", "谷歌": "Chrome", "谷歌浏览器": "Chrome",
    "edge": "Edge", "微软浏览器": "Edge",
    "浏览器": "_browser",
    "word软件": "Word", "文档软件": "Word",
    "excel软件": "Excel", "表格软件": "Excel",
    "powerpoint": "PowerPoint", "ppt软件": "PowerPoint",
    "git": "Git",
    "terminal": "Windows Terminal", "终端": "Windows Terminal", "命令行": "Windows Terminal",
    "wt": "Windows Terminal",
    "notepad": "Notepad++", "记事本": "Notepad++",
    "autocad": "AutoCAD", "cad": "AutoCAD",
    "wps": "WPS Writer",
    "keil": "Keil uVision",
}

LAUNCH_KEYWORDS = ["打开", "启动", "运行", "开启", "启用", "launch", "open", "start"]

GEN_VERBS = ["生成", "创建", "制作", "编写", "写", "做", "帮我写", "帮我做", "帮我生成"]

WORD_NOUNS = ["word", "docx", "文档", "方案", "报告", "技术响应", "施工组织设计", "整改报告", "工作总结", "竣工报告"]
PPT_NOUNS = ["ppt", "pptx", "演示", "汇报", "幻灯片", "演示文稿"]
EXCEL_NOUNS = ["excel", "xlsx", "表格", "清单", "台账", "统计表"]
CODE_NOUNS = ["代码", "python", "脚本", "script"]
ANALYSIS_REPORT_KEYWORDS = [
    "财务分析", "分析报告", "利润分析", "成本分析", "经营分析", "财务报告", "财务模型",
]
CUSTOM_OFFICE_TOPIC_KEYWORDS = [
    "排名", "统计", "对比", "调研", "大模型", "榜单", "评测", "数据表",
]


def _mentions_multiple_office_formats(text: str) -> bool:
    has_excel = _has_any(text, ["excel", "xlsx", "表格", "台账", "统计表"])
    has_word = _has_any(text, ["word", "docx", "word版", "word文档", "文档版"])
    has_ppt = _has_any(text, ["ppt", "pptx", "演示文稿", "幻灯片", "ppt版"])
    return sum([has_excel, has_word, has_ppt]) >= 2


def _wants_template_excel(goal: str, text: str) -> bool:
    return _has_any(text, ["资料清单", "交付清单", "文件清单", "成果清单"])


def _wants_template_ppt(goal: str, text: str) -> bool:
    return _has_any(text, ["投标", "方案汇报", "技术方案", "汇报材料"]) and _has_any(text, PPT_NOUNS)


def _wants_template_word(goal: str, text: str) -> bool:
    return _has_any(text, ["施工组织设计", "竣工报告", "工程技术文档", "技术响应"])


def _needs_agent_for_office(goal: str) -> bool:
    text = goal.lower()
    if _mentions_multiple_office_formats(text):
        return True
    if re.search(r"关于.+的", goal):
        return True
    if _has_any(text, CUSTOM_OFFICE_TOPIC_KEYWORDS):
        return True
    wants_office = _has_any(text, EXCEL_NOUNS + WORD_NOUNS + PPT_NOUNS)
    if not wants_office:
        return False
    if _wants_template_excel(goal, text) or _wants_template_ppt(goal, text) or _wants_template_word(goal, text):
        return False
    return _has_any(goal, GEN_VERBS) or _has_any(text, ["excel", "xlsx", "word", "docx", "ppt", "pptx"])


def _resolve_browser() -> str:
    for name in ["Chrome", "Edge"]:
        row = query_one(
            "SELECT id FROM software_tools WHERE software_name=? AND enabled=1 AND executable_path<>''",
            (name,),
        )
        if row:
            return name
    return "Chrome"


def _has_any(text: str, keywords: list[str]) -> bool:
    return any(kw in text for kw in keywords)


def _wants_generate(goal: str, text: str, doc_nouns: list[str]) -> bool:
    """Check if user wants to GENERATE a specific document type.
    Must have both a generation verb AND the document type noun."""
    if _has_any(text, [n for n in doc_nouns if len(n) >= 4]):
        return True
    return _has_any(goal, GEN_VERBS) and _has_any(text, doc_nouns)


class Planner:
    """Intent-based planner. Only routes to tools when the intent is crystal clear.
    Everything else falls through to Agent LLM for an intelligent response."""

    def plan(self, goal: str, project: dict | None = None) -> TaskPlan:
        text = goal.lower()

        # 1) Skill installation from URL
        url_match = re.search(r"https?://\S+", goal)
        if url_match and _has_any(text, ["skill", "插件", "安装", "技能"]):
            return TaskPlan(
                title="从网络安装 Skill",
                task_type="install_skill",
                user_goal=goal,
                risk_level="medium",
                expected_artifacts=["installed_skill"],
                steps=[TaskStep("下载并安装 Skill", "skill.install.url",
                                {"url": url_match.group(0).rstrip("。；;，,")}, "medium")],
            )

        # 2) Launch software
        if _has_any(goal, LAUNCH_KEYWORDS):
            software_name = self._match_software(text)
            if software_name:
                row = query_one(
                    "SELECT id FROM software_tools WHERE software_name=? AND enabled=1 AND executable_path<>''",
                    (software_name,),
                )
                if row:
                    return TaskPlan(
                        title=f"启动 {software_name}",
                        task_type="launch_software",
                        user_goal=goal,
                        risk_level="medium",
                        expected_artifacts=[],
                        steps=[TaskStep(f"启动 {software_name}", "software.launch",
                                        {"software_id": row["id"]}, "medium")],
                    )
                return TaskPlan(
                    title=f"启动 {software_name}（未配置）",
                    task_type="launch_software_failed",
                    user_goal=goal, risk_level="low",
                    expected_artifacts=[], steps=[],
                )

        return TaskPlan.agent_execute_plan(goal, title="Agent 智能执行")

    @staticmethod
    def _match_software(text: str) -> str | None:
        for alias, name in SOFTWARE_ALIASES.items():
            if alias in text:
                if name == "_browser":
                    return _resolve_browser()
                return name
        return None


_PLANNER_SYSTEM = """你是 DNA Work Agent 的任务规划器。根据用户目标输出 **唯一一段 JSON**（不要 markdown 代码块），格式：

{
  "title": "简短任务标题",
  "task_type": "generate_ppt|generate_word|generate_excel|agent_craft|...",
  "risk_level": "low|medium|high",
  "expected_artifacts": ["pptx"],
  "steps": [
    {"name": "步骤说明", "tool": "工具名", "input": {}}
  ]
}

可用工具（优先用确定性工具，复杂任务才用 agent.execute）：
- office.ppt.create / office.word.create / office.excel.create — 生成 Office 文件（input 必须含完整 sections/slides/headers+rows 或 sheets，禁止空文件）
- library_search — 检索资料库，input: {"query": "..."}
- library_list — 列出资料库
- software.launch — 启动软件，input: {"software_id": 数字}（仅当明确知道 ID）
- agent.execute — 开放式/多工具任务，input: {"goal": "本步骤目标描述"}

规则：
1. 财务分析、经营分析、需要模型撰写表格内容的任务 → **只用 agent.execute**，不要 library_search + 空 office.excel.create
2. office.excel.create 的 input 必须自带完整 headers/rows（或 sheets），不能把检索结果留空
3. 默认 **不要** 规划 GUI 步骤（ui_click 等）；除非用户明确要求操控软件且已知 GUI 实验功能已开启
4. 打开软件类请求 → software.launch 或 agent.execute（仅启动，不在 App 内自动化）
5. steps 至少 1 步，最多 6 步
6. 只输出 JSON"""


def _extract_json_object(text: str) -> dict | None:
    import json

    raw = (text or "").strip()
    if not raw:
        return None
    if raw.startswith("```"):
        lines = raw.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        raw = "\n".join(lines).strip()
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        pass
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        try:
            data = json.loads(raw[start:end + 1])
            return data if isinstance(data, dict) else None
        except json.JSONDecodeError:
            return None
    return None


def _sanitize_plan_steps(plan: TaskPlan) -> TaskPlan:
    from adapters.office_excel_adapter import excel_input_has_data
    from agent_runtime.tool_bridge import AGENT_EXECUTE_TOOL, known_plan_tool, normalize_tool_name

    clean: list[TaskStep] = []
    for step in plan.steps:
        if known_plan_tool(step.tool):
            clean.append(step)
            continue
        clean.append(TaskStep(
            name=step.name or "智能执行",
            tool=AGENT_EXECUTE_TOOL,
            input={"goal": plan.user_goal, "step_hint": step.name, "original_tool": step.tool},
            risk_level=step.risk_level,
        ))
    if not clean:
        return TaskPlan.agent_execute_plan(plan.user_goal, title=plan.title)

    for step in clean:
        tool = normalize_tool_name(step.tool)
        if tool == "office_excel_create" and not excel_input_has_data(
            title=str(step.input.get("title") or ""),
            headers=step.input.get("headers"),
            rows=step.input.get("rows"),
            sheets=step.input.get("sheets"),
        ):
            return TaskPlan.agent_execute_plan(plan.user_goal, title=plan.title or "智能执行")
        if tool == "office_word_create":
            from adapters.office_word_adapter import word_input_has_data
            if not word_input_has_data(
                sections=step.input.get("sections"),
                content=step.input.get("content"),
            ):
                return TaskPlan.agent_execute_plan(plan.user_goal, title=plan.title or "智能执行")
        if tool == "office_ppt_create":
            slides = step.input.get("slides") or []
            if not slides:
                return TaskPlan.agent_execute_plan(plan.user_goal, title=plan.title or "智能执行")
    plan.steps = clean
    return plan


def plan_from_confirmed_markdown(goal: str, plan_markdown: str, project: dict | None = None) -> TaskPlan:
    """Plan 模式用户确认 Markdown 计划后，包装为 Executor 可执行的 TaskPlan。"""
    title = "执行已确认计划"
    for line in (plan_markdown or "").splitlines():
        s = line.strip()
        if s.startswith("#"):
            title = s.lstrip("# ").strip() or title
            break
    return TaskPlan.agent_execute_plan(
        goal,
        plan_context=plan_markdown,
        title=title,
    )


def plan_with_llm(
    goal: str,
    model: dict,
    project: dict | None = None,
    *,
    rule_first: bool = True,
) -> TaskPlan:
    """保留兼容入口：文档/分析类任务一律交给 Agent，仅启动软件等走规则。"""
    del model, rule_first
    return Planner().plan(goal, project)

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
        project_name = (project or {}).get("project_name") or "未命名项目"
        safe_name = "".join(ch for ch in project_name if ch.isalnum() or ch in ("_", "-"))[:24] or "project"
        stamp = _stamp()

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

        # 3) Generate PPT
        if _wants_generate(goal, text, PPT_NOUNS):
            return TaskPlan(
                title="生成 PPT 演示文稿",
                task_type="generate_ppt",
                user_goal=goal,
                risk_level="medium",
                expected_artifacts=["pptx"],
                steps=[TaskStep("生成 PPTX", "office.ppt.create", {
                    "title": f"{project_name} 技术方案汇报",
                    "slides": [
                        ["项目概况", ["项目背景与建设目标", "工程范围与关键边界"]],
                        ["技术路线", ["系统架构与实施路径", "关键设备与接口"]],
                        ["质量与验收", ["测试依据与标准库引用", "验收资料闭环"]],
                        ["交付计划", ["进度安排", "成果文件清单"]],
                    ],
                    "output_name": f"{safe_name}_方案汇报_{stamp}.pptx",
                }, "medium")],
            )

        # 4) Generate Excel
        if _wants_generate(goal, text, EXCEL_NOUNS):
            return TaskPlan(
                title="生成 Excel 表格",
                task_type="generate_excel",
                user_goal=goal,
                risk_level="medium",
                expected_artifacts=["xlsx"],
                steps=[TaskStep("生成 XLSX", "office.excel.create", {
                    "title": "资料清单",
                    "headers": ["序号", "资料名称", "类型", "状态", "备注"],
                    "rows": [
                        [1, "项目技术方案", "Word", "待完善", "由 Agent 生成草稿"],
                        [2, "现场测试记录", "Word", "待完善", "需结合标准库"],
                        [3, "投标技术响应", "PPT/Word", "待完善", "需结合招标文件"],
                    ],
                    "output_name": f"{safe_name}_资料清单_{stamp}.xlsx",
                }, "medium")],
            )

        # 5) Generate code
        if _wants_generate(goal, text, CODE_NOUNS):
            return TaskPlan(
                title="生成 Python 脚本",
                task_type="generate_code",
                user_goal=goal,
                risk_level="medium",
                expected_artifacts=["py"],
                steps=[TaskStep("生成 Python 文件", "code.python.create",
                                {"task": goal, "output_name": f"generated_script_{stamp}.py"}, "medium")],
            )

        # 6) Generate Word — verb + document noun
        if _wants_generate(goal, text, WORD_NOUNS):
            return TaskPlan(
                title="生成工程文档 Word",
                task_type="generate_word",
                user_goal=goal,
                risk_level="medium",
                expected_artifacts=["docx"],
                steps=[TaskStep("生成 DOCX 文档", "office.word.create", {
                    "title": f"{project_name} 工程技术文档",
                    "sections": [
                        ["一、任务目标", goal],
                        ["二、项目上下文", f"当前项目：{project_name}"],
                        ["三、实施建议", "1. 收集项目资料\n2. 查询行业标准\n3. 形成可交付文档"],
                    ],
                    "output_name": f"{safe_name}_工程技术文档_{stamp}.docx",
                }, "medium")],
            )

        # 7) DEFAULT: Agent LLM handles it intelligently
        return TaskPlan(
            title="Agent 智能回答",
            task_type="agent_answer",
            user_goal=goal,
            risk_level="low",
            expected_artifacts=[],
            steps=[],
        )

    @staticmethod
    def _match_software(text: str) -> str | None:
        for alias, name in SOFTWARE_ALIASES.items():
            if alias in text:
                if name == "_browser":
                    return _resolve_browser()
                return name
        return None

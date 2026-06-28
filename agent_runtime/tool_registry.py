from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from adapters.code_adapter import create_python_script
from adapters.office_excel_adapter import create_excel_workbook
from adapters.office_ppt_adapter import create_presentation
from adapters.office_word_adapter import create_word_document
from agent_runtime.project_writer import write_project_file
from agent_runtime.skill_installer import install_market_skill, install_skill_from_url
from agent_runtime.software_connector import launch_software


@dataclass
class ToolSpec:
    name: str
    display_name: str
    description: str
    risk_level: str
    handler: Callable[..., Any]


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, ToolSpec] = {}
        self.register("office.word.create", "生成 Word", "生成 DOCX 文档", "medium", create_word_document)
        self.register("office.excel.create", "生成 Excel", "生成 XLSX 表格", "medium", create_excel_workbook)
        self.register("office.ppt.create", "生成 PPT", "生成 PPTX 演示文稿", "medium", create_presentation)
        self.register("code.python.create", "生成 Python 脚本", "生成 Python 代码文件", "medium", create_python_script)
        self.register("code.project.write_file", "写入项目文件", "在指定项目目录内写入代码/文本文件并自动备份", "high", write_project_file)
        self.register("software.launch", "启动本机软件", "启动已配置的本机软件，可传入打开路径", "medium", launch_software)
        self.register("skill.install.url", "从网络安装 Skill", "从 URL 或 GitHub 仓库下载并安装 Skill 包", "medium", install_skill_from_url)
        self.register("skill.install.market", "安装市场 Skill", "从内置市场安装 Skill 占位包", "low", install_market_skill)

    def register(self, name: str, display_name: str, description: str, risk_level: str, handler: Callable[..., Any]) -> None:
        self._tools[name] = ToolSpec(name, display_name, description, risk_level, handler)

    def get(self, name: str) -> ToolSpec:
        if name not in self._tools:
            raise KeyError(f"工具不存在：{name}")
        return self._tools[name]

    def list_tools(self) -> list[ToolSpec]:
        return list(self._tools.values())


registry = ToolRegistry()

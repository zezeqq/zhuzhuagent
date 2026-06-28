"""Skill 目录与市场清单 — 唯一数据源（商店 / 专家中心共用）。"""

from __future__ import annotations

from utils.path_utils import (
    builtin_skills_dir,
    installed_skills_dir,
    skill_downloads_dir,
)
from db.database import query_all

INSTALLED_SKILLS_DIR = installed_skills_dir()
SKILL_DOWNLOADS_DIR = skill_downloads_dir()
BUILTIN_SKILLS_DIR = builtin_skills_dir()

# skill_type: prompt = SKILL.md 注入 | tool = tools[] + skill.py | planned = 不可安装
SKILL_TYPE_LABELS = {
    "prompt": "说明文档",
    "tool": "含工具",
    "planned": "规划中",
}

SKILL_CATEGORIES = ["全部", "办公", "效率", "开发", "研究", "数据", "工程", "创意", "远程", "规划"]

RECOMMENDED_SKILLS: list[dict] = [
    {
        "name": "ppt_maker",
        "display": "PPT 制作",
        "desc": "根据主题生成结构完整的汇报 PPT（注入步骤 + 调用 office_ppt_create）",
        "category": "办公",
        "icon": "📽",
        "skill_type": "prompt",
        "featured": True,
        "recommended_tools": ["office_ppt_create"],
        "skill_md": """# PPT 制作

根据用户主题与数据，生成结构完整、内容充实的汇报 PPT。

## 何时使用

用户要求做 PPT、演示文稿、汇报幻灯片、路演 deck 时使用。

## 执行步骤

1. 确认主题、受众、页数要求（默认 8–12 页）
2. 自行构思每页标题与 3–5 条完整要点句（每句 15–40 字，禁止只写关键词）
3. 调用 `office_ppt_create`，一次传入全部 slides 内容
4. 告知用户产物路径，必要时用 `software_launch` 打开

## 质量标准

- 每页要点是完整句子，像行业专家汇报
- 有封面、目录/背景、正文、总结页
- 禁止「自主性、感知能力」式单词罗列

## 工具

优先 `office_ppt_create`。
""",
    },
    {
        "name": "markitdown",
        "display": "MarkItDown",
        "desc": "文档转 Markdown（需本机 markitdown CLI 或替代方案）",
        "category": "效率",
        "icon": "M",
        "skill_type": "prompt",
        "featured": True,
        "recommended_tools": ["shell_run", "file_read", "file_write"],
        "skill_md": """# MarkItDown 文档转换

将 PDF、Word、PPT、图片等转为 Markdown 或可读文本。

## 何时使用

用户要「转成 Markdown」「提取文档文字」「OCR 图片里的字」时使用。

## 执行步骤

1. 确认源文件路径（`file_list` 辅助定位）
2. 若已安装 markitdown CLI：`shell_run` 执行 `markitdown 源文件 -o 输出.md`
3. 若无 CLI：说明限制并建议安装 markitdown
4. 用 `file_write` 保存结果，返回输出路径
""",
    },
    {
        "name": "file_organizer",
        "display": "文件整理",
        "desc": "扫描 exports 目录并生成按类型分组的文件清单（含专用工具）",
        "category": "效率",
        "icon": "📂",
        "skill_type": "tool",
        "featured": True,
        "recommended_tools": ["file_list", "file_write"],
        "recommended_mcp": ["filesystem"],
        "tools": [
            {
                "name": "list_exports_inventory",
                "description": "列出 exports 目录下文件并按扩展名分组统计",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "subpath": {
                            "type": "string",
                            "description": "exports 下的子路径，默认根目录",
                        }
                    },
                    "required": [],
                },
            }
        ],
        "skill_md": """# 文件整理

整理、盘点 exports 产物目录。

## 何时使用

用户要整理 exports、生成文件清单、按类型统计时使用。

## 执行步骤

1. 优先调用 `list_exports_inventory` 获取分组清单
2. 如需写入报告，用 `file_write` 保存为 markdown
3. 如需 MCP 读写，可用 `mcp__filesystem__*`（Settings 中已配置时）
""",
    },
    {
        "name": "web_access",
        "display": "Web Access",
        "desc": "网页抓取与阅读（配合 MCP Fetch / Puppeteer，非 CDP 硬编码）",
        "category": "开发",
        "icon": "🌐",
        "skill_type": "prompt",
        "featured": True,
        "recommended_mcp": ["fetch", "puppeteer"],
        "recommended_tools": ["open_url"],
        "skill_md": """# Web Access

通过 MCP 访问网页内容（非内置 CDP）。

## 何时使用

用户要抓取网页、阅读 URL 内容、简单浏览器自动化时使用。

## 执行步骤

1. 若已配置 **Web Fetch MCP**：优先 `mcp__fetch__*` 抓取并转 Markdown
2. 若已配置 **Puppeteer MCP**：需要交互时用 `mcp__puppeteer__*`
3. 仅打开页面给用户看：可用 `open_url`
4. 不要用不存在的「CDP 直连」工具

## 前置

设置 → MCP 中启用 Fetch 或 Puppeteer，并开启网络访问。
""",
    },
    {
        "name": "deep_research",
        "display": "深度研究",
        "desc": "多轮检索 + 阅读 + 输出研究报告（需 Brave/Fetch MCP）",
        "category": "研究",
        "icon": "🔬",
        "skill_type": "prompt",
        "featured": False,
        "recommended_mcp": ["brave-search", "fetch"],
        "skill_md": """# 深度研究

对复杂问题多轮调研并输出报告。

## 执行步骤

1. 拆解子问题
2. 用 `mcp__brave-search__*` 或内置检索补充资料
3. 用 Fetch MCP 阅读关键 URL
4. 汇总为结构化报告，`file_write` 保存
""",
    },
    {
        "name": "email_writer",
        "display": "邮件助手",
        "desc": "撰写商务邮件（纯 prompt，无 SMTP 工具）",
        "category": "办公",
        "icon": "✉",
        "skill_type": "prompt",
        "featured": False,
        "skill_md": """# 邮件助手

撰写商务邮件、回复与跟进。

## 何时使用

用户要写邮件、润色邮件、写跟进时使用。

## 输出

直接给出可复制的邮件主题与正文；若用户要求发送，说明当前无 SMTP Skill，仅生成文案。
""",
    },
    {
        "name": "code_review",
        "display": "代码审查",
        "desc": "审查本地代码文件质量",
        "category": "开发",
        "icon": "💻",
        "skill_type": "prompt",
        "featured": False,
        "recommended_tools": ["file_read", "code_create"],
        "skill_md": """# 代码审查

审查 Python / JS 等代码质量。

## 执行步骤

1. `file_read` 读取目标文件
2. 从可读性、错误处理、安全、性能四方面审查
3. 给出分级问题列表与修改建议
""",
    },
    {
        "name": "meeting_minutes",
        "display": "会议纪要",
        "desc": "根据文字记录整理会议纪要",
        "category": "办公",
        "icon": "📝",
        "skill_type": "prompt",
        "featured": False,
        "skill_md": """# 会议纪要

整理会议内容为标准纪要。

## 输出结构

背景、结论、待办（负责人+截止时间）、风险与遗留问题。
""",
    },
    # ── 规划中（诚实标注，不可安装）──
    {
        "name": "qq_music",
        "display": "QQ 音乐助手",
        "desc": "规划中：需 QQ 音乐 API 或 GUI 自动化方案",
        "category": "规划",
        "icon": "🎵",
        "skill_type": "planned",
    },
    {
        "name": "tencent_news",
        "display": "腾讯新闻",
        "desc": "规划中：可改用 Brave Search + Fetch MCP 组合",
        "category": "规划",
        "icon": "📰",
        "skill_type": "planned",
    },
    {
        "name": "stock_analyzer",
        "display": "股票综合分析",
        "desc": "规划中：需行情数据源 API",
        "category": "规划",
        "icon": "📈",
        "skill_type": "planned",
    },
    {
        "name": "imap_smtp",
        "display": "IMAP/SMTP 邮件",
        "desc": "规划中：需邮件协议实现",
        "category": "规划",
        "icon": "✉",
        "skill_type": "planned",
    },
    {
        "name": "data_viz",
        "display": "数据可视化",
        "desc": "规划中：图表生成 Skill 包",
        "category": "规划",
        "icon": "📊",
        "skill_type": "planned",
    },
    {
        "name": "poster_gen",
        "display": "海报生成",
        "desc": "规划中：需图像生成 API",
        "category": "规划",
        "icon": "🎨",
        "skill_type": "planned",
    },
    {
        "name": "highway_test",
        "display": "公路机电测试",
        "desc": "规划中：工程模板包",
        "category": "规划",
        "icon": "🛣",
        "skill_type": "planned",
    },
    {
        "name": "bid_response",
        "display": "投标响应",
        "desc": "规划中：招标文件解析包",
        "category": "规划",
        "icon": "📋",
        "skill_type": "planned",
    },
    {
        "name": "quality_inspect",
        "display": "质量检验",
        "desc": "规划中：检验表模板包",
        "category": "规划",
        "icon": "✅",
        "skill_type": "planned",
    },
]


def all_catalog_skills() -> list[dict]:
    try:
        from core.remote_catalog import remote_skills_merged_with_local
        return remote_skills_merged_with_local()
    except Exception:
        return list(RECOMMENDED_SKILLS)


def skill_by_name(name: str) -> dict | None:
    key = name.strip().lower().replace(" ", "_")
    for s in all_catalog_skills():
        if s.get("name", "").lower() == key:
            return s
        if s.get("display", "").lower() == name.strip().lower():
            return s
    return None


def skill_type_label(skill: dict) -> str:
    return SKILL_TYPE_LABELS.get(skill.get("skill_type", "prompt"), "说明文档")


def is_planned_skill(skill: dict) -> bool:
    return skill.get("skill_type") == "planned"


def install_success_message(skill: dict, install_path: str) -> str:
    st = skill.get("skill_type", "prompt")
    base = f"技能「{skill.get('display', skill.get('name'))}」已安装。\n\n路径：{install_path}\n\n"
    if st == "tool":
        return base + "本 Skill 含专用工具函数，下一条 Craft 对话生效。"
    if st == "prompt":
        return base + "本 Skill 通过 SKILL.md 注入 Agent，下一条 Craft/Plan 对话生效。"
    return base


def get_installed_package_names() -> set[str]:
    names: set[str] = set()
    for row in query_all("SELECT package_name, display_name FROM installed_skill_packages"):
        if row.get("package_name"):
            names.add(str(row["package_name"]).lower())
        if row.get("display_name"):
            names.add(str(row["display_name"]).lower())
    return names


def is_skill_installed(skill: dict, installed: set[str] | None = None) -> bool:
    installed = installed if installed is not None else get_installed_package_names()
    pkg = skill.get("name", "").strip().lower().replace(" ", "_")
    display = skill.get("display", "").strip().lower()
    return pkg in installed or display in installed or skill.get("name", "").lower() in installed


def list_featured_skills() -> list[dict]:
    from core.remote_catalog import list_hot_remote_skills
    hot = list_hot_remote_skills()
    if hot:
        return hot
    return [s for s in all_catalog_skills() if s.get("featured") and not is_planned_skill(s)]


def catalog_skills_for_category(category: str) -> list[dict]:
    skills = all_catalog_skills()
    if category == "全部":
        return list(skills)
    if category == "规划":
        return [s for s in skills if is_planned_skill(s)]
    return [s for s in skills if s.get("category") == category and not is_planned_skill(s)]

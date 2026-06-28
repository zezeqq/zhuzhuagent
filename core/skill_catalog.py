"""Skill 目录与市场清单 — 安装路径与推荐技能统一在此维护。"""

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

# 推荐技能：download_url 有值时从网络安装，否则安装本地占位包（可后续替换为真实实现）
RECOMMENDED_SKILLS: list[dict] = [
    {
        "name": "ppt_maker",
        "display": "PPT 制作",
        "desc": "根据数据和主题自动生成汇报演示文稿",
        "category": "办公",
        "icon": "📽",
        "skill_md": """# PPT 制作

根据用户主题与数据，生成结构完整、内容充实的汇报 PPT。

## 何时使用

用户要求做 PPT、演示文稿、汇报幻灯片、路演 deck 时使用。

## 执行步骤

1. 确认主题、受众、页数要求（默认 8–12 页）
2. 自行构思每页标题与 3–5 条完整要点句（每句 15–40 字，禁止只写关键词）
3. 调用 `office_ppt_create`，一次传入全部 slides 内容
4. 告知用户产物路径，必要时用 `open_url` 或 `software_launch` 打开

## 质量标准

- 每页要点是完整句子，像行业专家汇报
- 有封面、目录/背景、正文、总结页
- 禁止「自主性、感知能力」式单词罗列

## 工具

优先 `office_ppt_create`；需要配图说明时用 `file_write` 写大纲后再生成。
""",
    },
    {
        "name": "markitdown",
        "display": "MarkItDown",
        "desc": "文档转换 Markdown / PDF / Word / PPT / 图片 OCR",
        "category": "效率",
        "icon": "M",
        "skill_md": """# MarkItDown 文档转换

将 PDF、Word、PPT、图片等转为 Markdown 或可读文本。

## 何时使用

用户要「转成 Markdown」「提取文档文字」「OCR 图片里的字」时使用。

## 执行步骤

1. 确认源文件路径（`file_list` 辅助定位）
2. 若已安装 markitdown CLI：`shell_run` 执行 `markitdown 源文件 -o 输出.md`
3. 若无 CLI：用 `file_read` 读 txt/md；Office 文件说明限制并建议安装 markitdown
4. 用 `file_write` 保存结果，返回输出路径

## 注意

二进制 PDF/Word 不要强行当文本读；优先命令行或专用库。
""",
    },
    {
        "name": "file_organizer",
        "display": "文件整理",
        "desc": "批量整理、重命名、归档文件夹内容",
        "category": "效率",
        "icon": "📂",
    },
    {
        "name": "deep_research",
        "display": "深度研究",
        "desc": "对复杂问题进行多轮调研并输出报告",
        "category": "研究",
        "icon": "🔬",
    },
    {
        "name": "email_writer",
        "display": "邮件助手",
        "desc": "自动撰写商务邮件、回复和跟进",
        "category": "办公",
        "icon": "✉",
    },
    {
        "name": "code_review",
        "display": "代码审查",
        "desc": "自动审查 Python / JS 代码质量",
        "category": "开发",
        "icon": "💻",
    },
    {
        "name": "data_viz",
        "display": "数据可视化",
        "desc": "将 CSV / Excel 数据生成图表和看板",
        "category": "数据",
        "icon": "📊",
    },
    {
        "name": "highway_test",
        "display": "公路机电测试",
        "desc": "根据标准生成现场测试记录和报告",
        "category": "工程",
        "icon": "🛣",
    },
    {
        "name": "bid_response",
        "display": "投标响应",
        "desc": "解析招标文件并生成技术响应文档",
        "category": "工程",
        "icon": "📋",
    },
    {
        "name": "quality_inspect",
        "display": "质量检验",
        "desc": "生成质量检验评定表和验收清单",
        "category": "工程",
        "icon": "✅",
    },
    {
        "name": "meeting_minutes",
        "display": "会议纪要",
        "desc": "根据会议录音 / 文字整理会议纪要",
        "category": "办公",
        "icon": "📝",
    },
    {
        "name": "poster_gen",
        "display": "海报生成",
        "desc": "根据需求文案生成活动海报图片",
        "category": "创意",
        "icon": "🎨",
    },
]

SKILL_CATEGORIES = ["全部", "办公", "数据", "工程", "开发", "创意", "研究", "效率"]


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

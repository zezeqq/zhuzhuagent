"""专家与专家团目录 — 对齐 WorkBuddy 专家中心数据模型。"""

from __future__ import annotations

import json
import re
from typing import Literal
from urllib.parse import urlparse

from core.remote_catalog import remote_experts_merged_with_local

ExpertKind = Literal["expert", "team"]

# recommended_skills 支持两种写法（可混用）：
#   1) catalog 名称字符串：  "sql_analyst"
#   2) GitHub 仓库对象：     {"name": "my_skill", "display": "显示名", "install_url": "https://github.com/owner/repo", "desc": "可选说明"}
#   3) 直接 URL 字符串：     "https://github.com/owner/repo"
EXPERT_TO_SKILL_CATEGORIES: dict[str, list[str]] = {
    "技术工程": ["开发", "工程", "远程"],
    "产品设计": ["办公", "研究", "创意"],
    "内容创作": ["办公", "创意", "效率"],
    "金融投资": ["数据", "研究", "远程"],
    "数据智能": ["数据", "研究", "开发"],
    "法律咨询": ["办公", "远程"],
    "电商运营": ["办公", "研究", "远程"],
    "办公效率": ["办公", "效率", "工程"],
    "小微企业": ["办公", "效率", "研究"],
}

EXPERT_GITHUB_KEYWORDS: dict[str, list[str]] = {
    "技术工程": ["code", "dev", "agent", "mcp", "skill", "cursor", "github"],
    "产品设计": ["product", "design", "ui", "prototype", "ppt"],
    "内容创作": ["content", "write", "story", "markdown", "social", "xiaohongshu"],
    "金融投资": ["finance", "stock", "trading", "invest", "sql", "data", "market"],
    "数据智能": ["data", "sql", "analyst", "python", "chart"],
    "法律咨询": ["legal", "contract", "compliance", "law"],
    "电商运营": ["ecommerce", "shop", "retail", "growth", "ops"],
    "办公效率": ["office", "word", "excel", "ppt", "report", "file"],
    "小微企业": ["smb", "sales", "growth", "business", "office", "report"],
}


def expert_github_search_query(item: dict) -> str:
    """根据专家分类、标签、名称与成员生成 GitHub Skill 检索词。"""
    tokens: list[str] = []
    seen: set[str] = set()

    def add(text: str) -> None:
        text = text.strip()
        if not text:
            return
        key = text.lower()
        if key in seen:
            return
        seen.add(key)
        tokens.append(text)

    category = item.get("category") or ""
    for kw in EXPERT_GITHUB_KEYWORDS.get(category, [])[:5]:
        add(kw)
    add(category)
    add(item.get("name") or "")
    for tag in (item.get("tags") or [])[:4]:
        add(str(tag))
    for member in (item.get("members") or [])[:4]:
        add(str(member))
    desc = (item.get("desc") or "").strip()
    if desc:
        add(desc[:48])
    if not tokens:
        return "agent skill"
    return " ".join(tokens[:12])


def expert_domain_search_hint(item: dict) -> str:
    """供 UI 展示：该专家 GitHub 热门组使用的方向关键词。"""
    q = expert_github_search_query(item)
    if len(q) > 56:
        return q[:53] + "…"
    return q

CATEGORY_DEFAULT_SKILLS: dict[str, list[str]] = {
    "技术工程": ["code_review_pro", "mcp_setup_guide"],
    "办公效率": ["weekly_report_gen", "file_organizer"],
    "内容创作": ["weekly_report_gen", "ppt_storyline"],
    "金融投资": ["sql_analyst", "deep_research_pro"],
    "数据智能": ["sql_analyst", "deep_research_pro"],
    "法律咨询": ["weekly_report_gen"],
    "电商运营": ["weekly_report_gen", "ppt_storyline"],
    "产品设计": ["ppt_storyline", "deep_research_pro"],
    "小微企业": ["weekly_report_gen", "ppt_storyline"],
}

# 内置专家（单角色 Agent 型）
BUNDLED_EXPERTS: list[dict] = [
    {"name": "高级开发工程师", "provider": "专八哥", "kind": "expert", "desc": "10年以上全栈经验，精通多种语言和框架，熟悉前后端、架构设计与代码评审。", "tags": ["高级开发", "架构设计", "代码质量"], "category": "技术工程", "recommended_skills": [
        "code_review_pro",
        "github_helper",
        {
            "name": "vibe_tools",
            "display": "Vibe Tools",
            "desc": "为 Cursor Agent 扩展工具能力的 GitHub Skill 合集。",
            "install_url": "https://github.com/yamadashy/vibe-tools",
        },
    ]},
    {"name": "内容创作专家", "provider": "文博客", "kind": "expert", "desc": "擅长撰写引人入胜的多平台内容，让品牌故事触达目标受众。", "tags": ["内容创作", "品牌故事"], "category": "内容创作", "recommended_skills": ["weekly_report_gen", "ppt_storyline"]},
    {"name": "数据分析师", "provider": "数据派", "kind": "expert", "desc": "精通 Python 数据处理、可视化和统计分析，善于从数据中提炼业务洞察。", "tags": ["数据分析", "可视化"], "category": "数据智能", "recommended_skills": ["sql_analyst"]},
    {"name": "投资分析师", "provider": "金融通", "kind": "expert", "desc": "深入研究宏观经济与行业趋势，提供专业的投资策略和风险评估。", "tags": ["投资分析", "风险评估"], "category": "金融投资", "recommended_skills": ["deep_research_pro", "sql_analyst"]},
    {"name": "法律顾问", "provider": "法务通", "kind": "expert", "desc": "精通合同法、劳动法和知识产权，为企业提供合规建议和风险防范。", "tags": ["合同审查", "合规咨询"], "category": "法律咨询", "recommended_skills": ["weekly_report_gen"]},
    {"name": "公路机电专家", "provider": "DNA", "kind": "expert", "desc": "精通交通监控、收费、通信、供配电、照明和隧道机电系统。", "tags": ["公路机电", "工程标准"], "category": "技术工程", "recommended_skills": ["code_review_pro", "weekly_report_gen"]},
    {"name": "投标专家", "provider": "DNA", "kind": "expert", "desc": "擅长解读招标文件技术要求，组织技术方案和响应内容。", "tags": ["投标技术", "方案编写"], "category": "办公效率", "recommended_skills": ["weekly_report_gen", "ppt_storyline"]},
    {"name": "测试专家", "provider": "DNA", "kind": "expert", "desc": "熟悉公路机电工程各系统的测试方法、仪器使用和记录规范。", "tags": ["现场测试", "标准规程"], "category": "技术工程", "recommended_skills": ["weekly_report_gen", "file_organizer"]},
    {"name": "质量管理专家", "provider": "DNA", "kind": "expert", "desc": "精通质量检验评定标准，熟悉工序、分部、单位工程的检验流程。", "tags": ["质量管理", "检验评定"], "category": "技术工程", "recommended_skills": ["weekly_report_gen", "file_organizer"]},
    {"name": "文档编写专家", "provider": "DNA", "kind": "expert", "desc": "擅长项目方案、施工组织设计、工程总结和验收资料的撰写。", "tags": ["技术文档", "方案撰写"], "category": "办公效率", "recommended_skills": ["weekly_report_gen", "ppt_storyline"]},
    {"name": "电商运营专家", "provider": "运营派", "kind": "expert", "desc": "深耕电商领域，精通流量获取、转化优化和用户运营策略。", "tags": ["电商运营", "流量增长"], "category": "电商运营", "recommended_skills": ["weekly_report_gen", "deep_research_pro"]},
    {"name": "产品经理", "provider": "产品派", "kind": "expert", "desc": "擅长需求分析、产品规划和用户体验设计，推动产品从0到1。", "tags": ["需求分析", "产品规划"], "category": "产品设计", "recommended_skills": ["ppt_storyline", "deep_research_pro"]},
]

# 精选场景（Hero 卡片 → 分类筛选 + 关联专家团）
FEATURED_SCENES: list[dict] = [
    {"title": "内容创作", "category": "内容创作", "team": "内容创作专家团", "highlights": ["内容创作专家", "小红书运营专家"]},
    {"title": "投资分析", "category": "金融投资", "team": "交易分析团队", "highlights": ["投资分析师", "数据分析师"]},
    {"title": "法律咨询", "category": "法律咨询", "team": "法律合规审查团", "highlights": ["法律顾问"]},
    {"title": "小微企业", "category": "办公效率", "team": "小微增长顾问团", "highlights": ["投标专家", "内容创作专家"]},
    {"title": "电商运营", "category": "电商运营", "team": "中国电商运营专家团", "highlights": ["电商运营专家", "产品经理"]},
]

_TEAM_PROMPT_HEADER = (
    "你是「{name}」的团长，负责拆解任务、协调成员并整合交付。\n\n"
    "协作成员：\n{members_block}\n\n"
    "工作方式：\n"
    "1. 先澄清用户目标与约束\n"
    "2. 将任务拆成子任务，标注由哪位成员视角完成\n"
    "3. 汇总为一份完整、可执行的交付物\n\n"
)

BUNDLED_EXPERT_TEAMS: list[dict] = [
    {
        "name": "内容创作专家团",
        "kind": "team",
        "provider": "Buddy",
        "category": "内容创作",
        "desc": "选题策划、多平台文案与小红书运营协作，适合品牌内容与增长任务。",
        "tags": ["专家团", "内容创作", "小红书"],
        "members": ["内容创作专家", "小红书运营专家"],
        "recommended_skills": [
            "weekly_report_gen",
            "ppt_storyline",
            {
                "name": "baoyu_design",
                "display": "Baoyu Design Skill",
                "desc": "UI  mockup / 原型 HTML 生成类 Agent Skill。",
                "install_url": "https://github.com/nicepkg/baoyu-design",
            },
        ],
    },
    {
        "name": "交易分析团队",
        "kind": "team",
        "provider": "Buddy",
        "category": "金融投资",
        "desc": "宏观研判 + 数据验证，输出投资策略与风险提示。",
        "tags": ["专家团", "投资", "数据分析"],
        "members": ["投资分析师", "数据分析师"],
        "recommended_skills": [
            "sql_analyst",
            "deep_research_pro",
            {
                "name": "agent_skills_registry",
                "display": "Agent Skills 合集",
                "desc": "addyosmani 高星 Agent Skill 注册表，安装后批量识别子 Skill。",
                "install_url": "https://github.com/addyosmani/agent-skills",
            },
        ],
    },
    {
        "name": "法律合规审查团",
        "kind": "team",
        "provider": "Buddy",
        "category": "法律咨询",
        "desc": "合同条款审查与合规风险识别，适合商务与劳动场景。",
        "tags": ["专家团", "法务", "合规"],
        "members": ["法律顾问"],
    },
    {
        "name": "小微增长顾问团",
        "kind": "team",
        "provider": "Buddy",
        "category": "办公效率",
        "desc": "投标方案、内容获客与日常办公文档协作。",
        "tags": ["专家团", "小微", "投标"],
        "members": ["投标专家", "内容创作专家", "文档编写专家"],
        "recommended_skills": ["weekly_report_gen"],
    },
    {
        "name": "中国电商运营专家团",
        "kind": "team",
        "provider": "Buddy",
        "category": "电商运营",
        "desc": "选品、流量、转化与产品体验联合分析，适合电商增长项目。",
        "tags": ["专家团", "电商", "运营"],
        "members": ["电商运营专家", "产品经理", "数据分析师"],
        "recommended_skills": ["weekly_report_gen", "deep_research_pro"],
    },
]


def _expert_index(experts: list[dict]) -> dict[str, dict]:
    return {e["name"]: e for e in experts if e.get("name")}


def build_team_prompt(team: dict, experts: list[dict]) -> str:
    idx = _expert_index(experts)
    lines: list[str] = []
    for member in team.get("members") or []:
        e = idx.get(member)
        if e:
            desc = e.get("desc") or ""
            lines.append(f"- {member}（{e.get('provider', '')}）：{desc}")
        else:
            lines.append(f"- {member}：领域顾问")
    members_block = "\n".join(lines) if lines else "- （成员待配置）"
    custom = (team.get("prompt") or "").strip()
    if custom:
        return custom
    workflow = "\n".join(f"- {x}" for x in team.get("workflow", []))
    deliverables = "\n".join(f"- {x}" for x in team.get("deliverables", []))
    prompt = _TEAM_PROMPT_HEADER.format(name=team["name"], members_block=members_block)
    if workflow:
        prompt += f"\n团队工作流：\n{workflow}\n"
    if deliverables:
        prompt += f"\n最终交付物要求：\n{deliverables}\n"
    return prompt


def build_expert_prompt(expert: dict) -> str:
    custom = (expert.get("prompt") or "").strip()
    if custom:
        return custom
    responsibilities = "\n".join(f"- {x}" for x in expert.get("responsibilities", []))
    deliverables = "\n".join(f"- {x}" for x in expert.get("deliverables", []))
    workflow = "\n".join(f"- {x}" for x in expert.get("workflow", []))
    guardrails = "\n".join(f"- {x}" for x in expert.get("guardrails", []))
    prompt = (
        f"你是「{expert['name']}」，{expert.get('desc', '')}\n\n"
        "请以该专家身份工作：先判断用户目标，再给出专业、可执行、可落地的方案。"
    )
    if responsibilities:
        prompt += f"\n\n核心职责：\n{responsibilities}"
    if workflow:
        prompt += f"\n\n工作流程：\n{workflow}"
    if deliverables:
        prompt += f"\n\n输出交付物：\n{deliverables}"
    if guardrails:
        prompt += f"\n\n边界与注意事项：\n{guardrails}"
    return prompt


def _merge_tags(base: list[str], extra: list[str]) -> list[str]:
    out: list[str] = []
    for tag in [*base, *extra]:
        if tag and tag not in out:
            out.append(tag)
    return out


def _rich_prompt(entry: dict) -> str:
    return build_expert_prompt({**entry, "prompt": ""})


EXPERT_ROLE_BLUEPRINTS: dict[str, dict] = {
    "高级开发工程师": {
        "desc": "资深全栈与桌面软件工程师，擅长 Python、PySide6、自动化脚本、项目结构治理、代码审查和调试。",
        "responsibilities": [
            "把自然语言需求拆解成可执行的工程任务、文件改动和验证步骤。",
            "直接生成或修改项目代码，优先保持现有架构、命名和风格一致。",
            "做代码审查、异常定位、运行测试、依赖处理和打包排错。",
            "为桌面 Agent 增加工具调用、权限确认、日志、任务追踪等底层能力。",
        ],
        "workflow": [
            "先阅读项目结构和相关文件，确认入口、状态流和数据边界。",
            "给出最小可运行改动，必要时补测试或脚本验证。",
            "修改后必须说明涉及文件、验证结果和剩余风险。",
        ],
        "deliverables": ["可运行代码", "补丁说明", "测试/启动验证", "后续 TODO"],
        "guardrails": ["不硬编码 API Key、个人隐私或固定模型密钥。", "涉及覆盖/删除/系统命令时先确认。"],
    },
    "内容创作专家": {
        "desc": "多平台内容策划与写作专家，擅长公众号、小红书、短视频脚本、品牌故事和技术内容转译。",
        "responsibilities": [
            "将复杂业务或技术内容改写为目标人群能理解、愿意行动的表达。",
            "输出选题、标题、正文、脚本、分发节奏和复盘指标。",
            "根据平台调性调整语气：公众号重结构，小红书重场景，短视频重钩子。",
        ],
        "workflow": ["先明确受众、平台、目标动作和禁忌。", "输出 3 个方向，再展开最佳方案。", "给出可直接发布的正文和标题备选。"],
        "deliverables": ["内容策略", "标题库", "正文/脚本", "标签与发布建议"],
    },
    "小红书运营专家": {
        "provider": "内容增长",
        "category": "内容创作",
        "tags": ["小红书", "种草文案", "选题增长"],
        "desc": "熟悉小红书平台内容机制，擅长选题、标题、封面文案、正文结构和账号定位。",
        "responsibilities": [
            "设计小红书账号定位、内容栏目、爆款选题和发布节奏。",
            "输出标题、封面短句、正文、标签、评论区引导和转化路径。",
            "把工程、办公、电商等专业内容转成用户愿意收藏的场景化笔记。",
        ],
        "workflow": ["先判断目标用户和使用场景。", "用痛点/反差/清单/避坑组织内容。", "给出 A/B 标题和标签组合。"],
        "deliverables": ["小红书笔记", "标题与封面文案", "标签组合", "账号栏目建议"],
        "recommended_skills": ["weekly_report_gen", "ppt_storyline"],
    },
    "数据分析师": {
        "desc": "数据分析与业务洞察专家，擅长 Python、SQL、Excel、可视化、指标体系和经营分析。",
        "responsibilities": [
            "把业务问题转成指标、数据表、分析路径和可验证假设。",
            "清洗数据、做统计分析、生成图表和结论摘要。",
            "指出数据质量问题、异常值、采样偏差和下一步采集建议。",
        ],
        "workflow": ["先定义口径和目标指标。", "再设计分析步骤和图表。", "最后输出结论、风险和行动建议。"],
        "deliverables": ["分析思路", "SQL/Python/Excel 方案", "图表建议", "业务结论"],
    },
    "投资分析师": {
        "desc": "宏观、行业与资产研究专家，擅长信息搜集、财务指标、风险框架和投资备忘录。",
        "responsibilities": [
            "梳理宏观环境、行业逻辑、公司基本面和市场情绪。",
            "输出投资假设、关键变量、风险因素和跟踪指标。",
            "把数据分析师结果转成投资视角的判断，不做确定性收益承诺。",
        ],
        "workflow": ["先区分事实、假设和观点。", "再做 bull/base/bear 三情景分析。", "最后给出跟踪清单和风险提示。"],
        "deliverables": ["投资备忘录", "风险评估", "跟踪指标表", "研究问题清单"],
        "guardrails": ["不得承诺收益，不替代持牌金融建议。"],
    },
    "法律顾问": {
        "desc": "企业法务与合同合规顾问，擅长合同条款审查、劳动用工、知识产权和商务风险识别。",
        "responsibilities": [
            "审查合同、协议、制度文本中的权利义务、违约责任和争议条款。",
            "指出高风险条款、模糊表述、证据缺口和谈判建议。",
            "把法律风险翻译成业务可执行的修改意见。",
        ],
        "workflow": ["先识别文件类型和交易背景。", "逐条标注风险等级。", "给出替代表述和谈判策略。"],
        "deliverables": ["合同审查清单", "风险条款表", "修改建议", "谈判要点"],
        "guardrails": ["不替代律师正式法律意见；需提示用户结合当地法律和专业律师复核。"],
    },
    "公路机电专家": {
        "desc": "公路机电工程顾问，熟悉监控、收费、通信、供配电、照明、隧道机电系统的设计、施工、调试和验收。",
        "responsibilities": [
            "解读公路机电系统技术要求、施工方案、测试记录和验收依据。",
            "根据 JTG/T 3520、JTG 2182 等标准组织检查项和测试方法。",
            "帮助生成设备调试方案、故障排查步骤、验收资料和整改建议。",
        ],
        "workflow": ["先确认系统类型和项目阶段。", "引用标准或说明知识库未找到依据。", "输出测试/验收/整改的可执行步骤。"],
        "deliverables": ["技术方案", "测试记录模板", "验收检查清单", "整改报告"],
    },
    "投标专家": {
        "desc": "投标技术响应专家，擅长招标文件解读、评分点拆解、技术方案组织、偏离表和响应条款编写。",
        "responsibilities": [
            "从招标文件中提取强制要求、评分项、技术参数和交付物。",
            "组织技术方案目录、响应矩阵、偏离说明和实施计划。",
            "提醒缺资料、风险点和需要商务/法务确认的条款。",
        ],
        "workflow": ["先提取评分项和必须响应项。", "再组织方案结构和证据材料。", "最后输出可粘贴到标书的文本。"],
        "deliverables": ["技术响应稿", "评分点覆盖表", "偏离表", "方案目录"],
    },
    "测试专家": {
        "desc": "现场测试与调试专家，熟悉公路机电设备测试方法、仪器使用、测试记录和问题闭环。",
        "responsibilities": [
            "根据系统类型生成测试步骤、仪器清单、判定标准和记录表。",
            "指导现场故障定位、复测验证和整改闭环。",
            "把测试过程转成可归档的记录和验收附件。",
        ],
        "workflow": ["先确认测试对象、标准依据和现场条件。", "输出测试前准备、操作步骤、合格判定和异常处理。"],
        "deliverables": ["测试记录", "仪器清单", "问题闭环表", "现场操作步骤"],
    },
    "质量管理专家": {
        "desc": "工程质量管理专家，熟悉质量检验评定、分部分项工程、资料闭环和验收流程。",
        "responsibilities": [
            "建立质量检查项、责任分工、验收资料清单和问题整改闭环。",
            "对施工/调试/测试资料进行完整性和一致性检查。",
            "输出质量风险、缺项清单和下一步补资料建议。",
        ],
        "workflow": ["先按工程阶段建立检查框架。", "再识别缺资料和高风险项。", "最后输出整改优先级。"],
        "deliverables": ["质量检查清单", "缺项清单", "整改闭环表", "验收资料目录"],
    },
    "文档编写专家": {
        "desc": "工程文档与办公交付专家，擅长 Word、PPT、Excel 资料结构化和专业表达。",
        "responsibilities": [
            "把零散资料整理成方案、报告、周报、汇报 PPT 和台账。",
            "保持标题层级、术语、编号、表格和交付格式专业统一。",
            "根据用途调整文风：投标严谨、汇报清晰、记录可追溯。",
        ],
        "workflow": ["先确定文档用途和读者。", "再生成目录和关键表格。", "最后输出完整正文或文件生成指令。"],
        "deliverables": ["Word 草稿", "PPT 大纲", "Excel 表头/台账", "格式规范"],
    },
    "电商运营专家": {
        "desc": "电商增长运营专家，擅长选品、流量、转化、复购、活动和店铺经营分析。",
        "responsibilities": [
            "设计电商运营策略、活动节奏、商品卖点和转化漏斗。",
            "分析流量来源、页面转化、客单价、复购和库存风险。",
            "输出可执行的运营动作和数据复盘指标。",
        ],
        "workflow": ["先识别平台、品类、客群和目标。", "再做流量-转化-复购拆解。", "最后给出 7/30 天行动计划。"],
        "deliverables": ["运营计划", "商品卖点", "活动方案", "指标看板"],
    },
    "产品经理": {
        "desc": "产品设计与需求管理专家，擅长需求澄清、用户旅程、功能优先级、原型结构和 PRD。",
        "responsibilities": [
            "把模糊想法转成目标用户、场景、痛点、功能和验收标准。",
            "拆解 MVP、版本路线、交互流程和风险假设。",
            "连接设计、开发、运营和数据，形成可执行产品方案。",
        ],
        "workflow": ["先澄清用户和目标。", "再画功能边界和流程。", "最后输出 PRD/用户故事/验收标准。"],
        "deliverables": ["PRD", "用户故事", "功能优先级", "验收标准"],
    },
    "技术专家": {
        "provider": "技术派",
        "category": "技术工程",
        "tags": ["技术方案", "架构评审", "工程落地"],
        "desc": "面向非纯代码项目的技术顾问，擅长技术选型、系统方案、接口边界和落地风险评估。",
        "responsibilities": [
            "评估技术方案可行性、实施成本、风险和依赖。",
            "组织系统架构、接口、数据流、部署和运维建议。",
            "把业务需求翻译成工程实现路径。",
        ],
        "workflow": ["先确认目标和约束。", "再给出方案对比。", "最后输出推荐方案和实施清单。"],
        "deliverables": ["技术方案", "架构说明", "风险清单", "实施步骤"],
        "recommended_skills": ["code_review_pro", "mcp_setup_guide"],
    },
    "销售教练": {
        "provider": "销售派",
        "category": "小微企业",
        "tags": ["销售话术", "客户跟进", "成交策略"],
        "desc": "销售流程和客户沟通教练，擅长线索筛选、需求挖掘、异议处理和跟进话术。",
        "responsibilities": [
            "设计客户画像、销售漏斗、跟进节奏和成交路径。",
            "输出电话/微信/邮件话术和异议处理。",
            "帮助复盘丢单原因和下一步行动。",
        ],
        "workflow": ["先识别客户阶段。", "再给出沟通目标和话术。", "最后产出跟进计划。"],
        "deliverables": ["销售话术", "跟进计划", "异议处理表", "成交复盘"],
    },
    "微信公众号运营专家": {
        "provider": "内容增长",
        "category": "内容创作",
        "tags": ["公众号", "长文", "私域"],
        "desc": "公众号与私域内容运营专家，擅长长文结构、栏目规划、转化路径和用户沉淀。",
        "responsibilities": [
            "设计公众号栏目、选题日历、文章结构和转化组件。",
            "把技术/业务内容写成专业可信的长文。",
            "给出私域引导、评论互动和复盘指标。",
        ],
        "workflow": ["先确定读者和转化目标。", "再组织标题、摘要、正文和结尾 CTA。"],
        "deliverables": ["公众号文章", "选题日历", "摘要和标题", "转化 CTA"],
    },
    "资深合同法务专家": {
        "provider": "法务通",
        "category": "法律咨询",
        "tags": ["合同审查", "条款修改", "风险控制"],
        "desc": "专注合同审查与商务条款风险控制，适合采购、销售、服务和项目合同。",
        "responsibilities": [
            "逐条审查合同风险，识别付款、验收、违约、保密、知识产权、争议解决条款。",
            "给出风险等级、修改理由和替代条款文本。",
        ],
        "workflow": ["先识别合同类型。", "再输出风险条款表。", "最后给出可复制修改稿。"],
        "deliverables": ["合同风险表", "条款修改建议", "谈判底线", "需律师复核事项"],
        "guardrails": ["不替代正式法律服务。"],
    },
    "财税合规专家": {
        "provider": "财税通",
        "category": "法律咨询",
        "tags": ["财税合规", "发票", "内控"],
        "desc": "财税流程和合规内控顾问，擅长发票、报销、合同付款、成本归集和基础内控。",
        "responsibilities": [
            "梳理财税风险、票据链条、合同付款和报销合规问题。",
            "输出内控检查清单、资料归档要求和整改建议。",
        ],
        "workflow": ["先确认业务场景和资料。", "再识别税务/内控风险。", "最后输出整改清单。"],
        "deliverables": ["财税风险清单", "票据资料清单", "内控流程建议", "整改计划"],
    },
}


TEAM_ROLE_BLUEPRINTS: dict[str, dict] = {
    "内容创作专家团": {
        "desc": "由内容策略、平台运营、文档表达组成的创作小队，负责从选题到成稿到发布建议。",
        "workflow": [
            "团长先判断目标受众、平台和转化目标。",
            "内容创作专家负责主线、结构和故事表达。",
            "小红书/公众号运营专家负责平台标题、标签、封面和分发节奏。",
            "最终合并为可发布内容和复盘指标。",
        ],
        "deliverables": ["内容策略", "平台成稿", "标题/标签", "发布节奏", "复盘指标"],
        "members": ["内容创作专家", "小红书运营专家", "微信公众号运营专家"],
    },
    "交易分析团队": {
        "desc": "投资研究与数据分析双视角团队，负责从事实、数据、假设和风险四层输出投资研究。",
        "workflow": [
            "投资分析师负责宏观、行业、公司和风险框架。",
            "数据分析师负责数据口径、指标、图表和异常验证。",
            "团长整合为情景分析和跟踪清单。",
        ],
        "deliverables": ["投资备忘录", "数据分析摘要", "风险提示", "跟踪指标"],
    },
    "法律合规审查团": {
        "desc": "合同、合规、财税基础内控联合审查团队，适合商务合同、采购销售和项目交付场景。",
        "workflow": [
            "法律顾问识别法律条款风险。",
            "资深合同法务专家输出替代条款和谈判底线。",
            "财税合规专家检查发票、付款、归档和内控风险。",
        ],
        "deliverables": ["风险条款表", "修改建议", "合规清单", "需复核事项"],
        "members": ["法律顾问", "资深合同法务专家", "财税合规专家"],
    },
    "小微增长顾问团": {
        "desc": "面向小微企业的一站式增长顾问团，覆盖客户获取、销售转化、内容运营和投标/文档交付。",
        "workflow": [
            "销售教练负责客户沟通与成交路径。",
            "内容创作专家负责获客内容。",
            "投标专家负责项目型机会和方案响应。",
            "文档编写专家负责交付文件和模板沉淀。",
        ],
        "deliverables": ["7/30 天行动计划", "销售话术", "内容选题", "投标/方案模板"],
        "members": ["销售教练", "内容创作专家", "投标专家", "文档编写专家"],
    },
    "中国电商运营专家团": {
        "desc": "电商运营、产品、内容和数据协同团队，负责从选品到流量到转化到复盘的闭环。",
        "workflow": [
            "电商运营专家负责平台打法、活动和店铺经营。",
            "产品经理负责商品结构、页面体验和转化路径。",
            "数据分析师负责指标拆解和复盘。",
            "内容创作专家负责卖点表达和素材方向。",
        ],
        "deliverables": ["运营策略", "商品卖点", "转化优化清单", "数据看板", "复盘计划"],
        "members": ["电商运营专家", "产品经理", "数据分析师", "内容创作专家"],
    },
    "公路机电交付专家团": {
        "provider": "DNA",
        "category": "技术工程",
        "tags": ["专家团", "公路机电", "项目交付"],
        "desc": "围绕公路机电项目的方案、测试、质量、资料和交付闭环协同。",
        "workflow": [
            "公路机电专家负责技术路线和标准依据。",
            "测试专家负责现场测试步骤和记录。",
            "质量管理专家负责验收、评定和问题闭环。",
            "文档编写专家负责资料归档和报告表达。",
        ],
        "deliverables": ["技术方案", "测试计划", "质量检查清单", "验收资料目录", "整改闭环建议"],
        "members": ["公路机电专家", "测试专家", "质量管理专家", "文档编写专家"],
        "recommended_skills": ["weekly_report_gen", "file_organizer"],
    },
}


def _apply_expert_role_blueprints() -> None:
    existing = {item["name"]: item for item in BUNDLED_EXPERTS if item.get("name")}
    for name, blueprint in EXPERT_ROLE_BLUEPRINTS.items():
        item = existing.get(name)
        if not item:
            item = {
                "name": name,
                "provider": blueprint.get("provider", "Buddy"),
                "kind": "expert",
                "category": blueprint.get("category", "办公效率"),
                "desc": blueprint.get("desc", ""),
                "tags": list(blueprint.get("tags", [])),
                "recommended_skills": list(blueprint.get("recommended_skills", CATEGORY_DEFAULT_SKILLS.get(blueprint.get("category", "办公效率"), []))),
            }
            BUNDLED_EXPERTS.append(item)
            existing[name] = item
        item["desc"] = blueprint.get("desc", item.get("desc", ""))
        item["category"] = blueprint.get("category", item.get("category", "办公效率"))
        item["provider"] = blueprint.get("provider", item.get("provider", "Buddy"))
        item["tags"] = _merge_tags(list(item.get("tags") or []), list(blueprint.get("tags") or []))
        if blueprint.get("recommended_skills"):
            item["recommended_skills"] = list(blueprint["recommended_skills"])
        for key in ("responsibilities", "workflow", "deliverables", "guardrails"):
            if blueprint.get(key):
                item[key] = list(blueprint[key])
        item["prompt"] = _rich_prompt(item)


def _apply_team_role_blueprints() -> None:
    existing = {item["name"]: item for item in BUNDLED_EXPERT_TEAMS if item.get("name")}
    for name, blueprint in TEAM_ROLE_BLUEPRINTS.items():
        item = existing.get(name)
        if not item:
            item = {
                "name": name,
                "kind": "team",
                "provider": blueprint.get("provider", "Buddy"),
                "category": blueprint.get("category", "办公效率"),
                "desc": blueprint.get("desc", ""),
                "tags": list(blueprint.get("tags", ["专家团"])),
                "members": list(blueprint.get("members", [])),
                "recommended_skills": list(blueprint.get("recommended_skills", [])),
            }
            BUNDLED_EXPERT_TEAMS.append(item)
            existing[name] = item
        item["desc"] = blueprint.get("desc", item.get("desc", ""))
        item["category"] = blueprint.get("category", item.get("category", "办公效率"))
        item["provider"] = blueprint.get("provider", item.get("provider", "Buddy"))
        item["tags"] = _merge_tags(list(item.get("tags") or []), list(blueprint.get("tags") or []))
        if blueprint.get("members"):
            item["members"] = list(blueprint["members"])
        if blueprint.get("recommended_skills"):
            item["recommended_skills"] = list(blueprint["recommended_skills"])
        for key in ("workflow", "deliverables"):
            if blueprint.get(key):
                item[key] = list(blueprint[key])


_apply_expert_role_blueprints()
_apply_team_role_blueprints()


def all_merged_experts(custom_experts: list[dict] | None = None) -> list[dict]:
    custom = custom_experts or []
    for e in custom:
        e.setdefault("kind", "expert")
        e.setdefault("provider", "自定义")
    merged = remote_experts_merged_with_local(BUNDLED_EXPERTS + custom)
    for e in merged:
        e.setdefault("kind", "expert")
    return merged


def all_merged_teams(custom_experts: list[dict] | None = None) -> list[dict]:
    experts = all_merged_experts(custom_experts)
    teams = [dict(t) for t in BUNDLED_EXPERT_TEAMS]
    try:
        from core.remote_catalog import cached_remote_manifest
        remote = cached_remote_manifest()
        for rt in remote.get("expert_teams") or []:
            if isinstance(rt, dict) and rt.get("name"):
                teams.append({**rt, "kind": "team", "remote": True})
    except Exception:
        pass
    for team in teams:
        team.setdefault("kind", "team")
        if not team.get("prompt"):
            team["prompt"] = build_team_prompt(team, experts)
    return teams


def marketplace_items(
    *,
    custom_experts: list[dict] | None = None,
    kind_filter: str = "全部",
    category: str = "全部",
    query: str = "",
) -> list[dict]:
    """合并专家 + 专家团，供专家中心网格展示。"""
    experts = all_merged_experts(custom_experts)
    teams = all_merged_teams(custom_experts)
    items: list[dict] = []
    if kind_filter in ("全部", "专家"):
        items.extend(experts)
    if kind_filter in ("全部", "专家团"):
        items.extend(teams)

    if category != "全部":
        items = [x for x in items if x.get("category") == category]

    q = (query or "").strip().lower()
    if q:
        items = [
            x for x in items
            if q in x.get("name", "").lower()
            or q in x.get("desc", "").lower()
            or q in x.get("provider", "").lower()
            or any(q in str(t).lower() for t in x.get("tags") or [])
            or any(q in str(m).lower() for m in x.get("members") or [])
        ]
    return items


def resolve_summon_prompt(item: dict, custom_experts: list[dict] | None = None) -> str:
    experts = all_merged_experts(custom_experts)
    if item.get("kind") == "team":
        return build_team_prompt(item, experts)
    for ce in custom_experts or []:
        if ce.get("name") == item.get("name") and ce.get("prompt"):
            return ce["prompt"]
    return build_expert_prompt(item)


def record_recent_expert(name: str) -> None:
    try:
        from core.settings_store import get_setting, set_setting
        raw = get_setting("recent_experts", "[]")
        recent = json.loads(raw) if raw else []
        recent = [name] + [n for n in recent if n != name]
        set_setting("recent_experts", json.dumps(recent[:10], ensure_ascii=False), "json")
    except Exception:
        pass


def load_recent_experts() -> list[str]:
    try:
        from core.settings_store import get_setting
        raw = get_setting("recent_experts", "[]")
        return json.loads(raw) if raw else []
    except Exception:
        return []


def _slug_from_install_url(url: str) -> str:
    parsed = urlparse(url.strip())
    parts = [p for p in parsed.path.strip("/").split("/") if p and p not in ("archive", "tree", "blob")]
    if "github.com" in parsed.netloc.lower() and len(parts) >= 2:
        slug = re.sub(r"[^a-z0-9_]+", "_", f"{parts[0]}_{parts[1]}".lower()).strip("_")
        return f"github_{slug}"[:64]
    slug = re.sub(r"[^a-z0-9_]+", "_", (parsed.path or parsed.netloc).lower()).strip("_")
    return f"url_{slug}"[:64] or "github_skill"


def _skill_dict_from_url_entry(entry: dict) -> dict | None:
    url = (entry.get("install_url") or entry.get("url") or entry.get("package_url") or "").strip()
    if not url:
        return None
    name = (entry.get("name") or _slug_from_install_url(url)).strip().lower().replace(" ", "_")
    display = entry.get("display") or entry.get("name") or name
    return {
        "name": name,
        "display": display,
        "desc": (entry.get("desc") or entry.get("description") or "专家指定的 GitHub Skill 仓库。")[:300],
        "category": "远程",
        "icon": "🌐",
        "skill_type": "prompt",
        "tags": list(entry.get("tags") or ["专家指定", "GitHub"]),
        "install_url": url,
        "source_url": entry.get("source_url") or url,
        "discovered": True,
        "remote": True,
        "pinned": True,
    }


def parse_recommended_entries(item: dict) -> tuple[list[str], list[dict]]:
    """解析 recommended_skills：支持 catalog 名称字符串或带 install_url 的对象。"""
    catalog_names: list[str] = []
    pinned: list[dict] = []
    for entry in item.get("recommended_skills") or []:
        if isinstance(entry, dict):
            skill = _skill_dict_from_url_entry(entry)
            if skill:
                pinned.append(skill)
            elif entry.get("name"):
                catalog_names.append(str(entry["name"]))
        elif isinstance(entry, str):
            text = entry.strip()
            if not text:
                continue
            if text.startswith("http://") or text.startswith("https://"):
                skill = _skill_dict_from_url_entry({"install_url": text, "name": _slug_from_install_url(text)})
                if skill:
                    pinned.append(skill)
            else:
                catalog_names.append(text)
    return catalog_names, pinned


def _skill_name_candidates(item: dict) -> list[str]:
    names, _ = parse_recommended_entries(item)
    if names:
        return [n.strip().lower().replace(" ", "_") for n in names]
    cat = item.get("category") or ""
    return list(CATEGORY_DEFAULT_SKILLS.get(cat, ["weekly_report_gen"]))


def _tag_skill_row(skill: dict, *, source_kind: str, installed_names: set[str]) -> dict:
    from core.skill_catalog import is_skill_installed

    row = dict(skill)
    row["source_kind"] = source_kind
    row["installed"] = is_skill_installed(skill, installed_names)
    return row


def _official_skill_rows(item: dict, installed: set[str], seen: set[str]) -> list[dict]:
    from core.skill_catalog import skill_by_name

    catalog_names, _ = parse_recommended_entries(item)
    explicit = {n.strip().lower().replace(" ", "_") for n in catalog_names}
    out: list[dict] = []
    for raw in _skill_name_candidates(item):
        if raw in seen:
            continue
        skill = skill_by_name(raw)
        if not skill:
            continue
        seen.add(raw)
        row = _tag_skill_row(skill, source_kind="bundled" if skill.get("bundled") else "official", installed_names=installed)
        row["suggested"] = raw not in explicit
        out.append(row)
    return out


def _pinned_github_skill_rows(item: dict, installed: set[str], seen: set[str]) -> list[dict]:
    _, pinned = parse_recommended_entries(item)
    out: list[dict] = []
    for skill in pinned:
        key = skill.get("name", "").lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(_tag_skill_row(skill, source_kind="pinned", installed_names=installed))
    return out


def _remote_catalog_skill_rows(item: dict, installed: set[str], seen: set[str], *, limit: int = 3) -> list[dict]:
    from core.skill_catalog import all_catalog_skills

    cats = EXPERT_TO_SKILL_CATEGORIES.get(item.get("category") or "", [])
    out: list[dict] = []
    for skill in all_catalog_skills():
        if skill.get("bundled"):
            continue
        key = skill.get("name", "").lower()
        if not key or key in seen:
            continue
        if skill.get("category") not in cats and not skill.get("remote"):
            continue
        seen.add(key)
        out.append(_tag_skill_row(skill, source_kind="remote", installed_names=installed))
        if len(out) >= limit:
            break
    return out


def _github_skill_rows(
    item: dict,
    installed: set[str],
    seen: set[str],
    *,
    limit: int = 5,
    domain_skills: list[dict] | None = None,
) -> list[dict]:
    pool = list(domain_skills or [])
    if not pool:
        from core.skill_discovery import load_trending_cache

        cached = load_trending_cache() or {}
        pool = list(cached.get("skills") or [])
    if not pool:
        return []

    keywords = [k.lower() for k in EXPERT_GITHUB_KEYWORDS.get(item.get("category") or "", [])]
    for tag in item.get("tags") or []:
        keywords.append(str(tag).lower())
    for member in item.get("members") or []:
        keywords.append(str(member).lower())
    for piece in re.findall(r"[\u4e00-\u9fff]{2,}|[a-z0-9]{2,}", expert_github_search_query(item).lower()):
        keywords.append(piece)

    scored: list[tuple[int, dict]] = []
    for skill in pool:
        key = skill.get("name", "").lower()
        if not key or key in seen:
            continue
        text = " ".join([
            skill.get("name", ""),
            skill.get("display", ""),
            skill.get("desc", ""),
            " ".join(str(t) for t in skill.get("tags") or []),
        ]).lower()
        score = sum(1 for kw in keywords if kw and kw in text)
        rel = int(skill.get("_relevance") or 0)
        if rel > 0:
            score += min(12, rel // 3)
        if domain_skills and score <= 0:
            score = max(1, rel // 4)
        if not domain_skills and score <= 0:
            continue
        scored.append((score, skill))

    scored.sort(key=lambda x: (-x[0], -int(x[1].get("stars") or 0), -int(x[1].get("_relevance") or 0)))
    out: list[dict] = []
    for _, skill in scored[:limit]:
        key = skill.get("name", "").lower()
        seen.add(key)
        out.append(_tag_skill_row(skill, source_kind="github", installed_names=installed))
    return out


def companion_skills_for_expert(
    item: dict,
    *,
    installed_names: set[str] | None = None,
    domain_github_skills: list[dict] | None = None,
) -> dict[str, list[dict]]:
    """官方 catalog + 远程目录 + GitHub 热门（按专家工作方向匹配）。"""
    installed = installed_names or set()
    seen: set[str] = set()
    official = _official_skill_rows(item, installed, seen)
    pinned = _pinned_github_skill_rows(item, installed, seen)
    remote = _remote_catalog_skill_rows(item, installed, seen)
    github = _github_skill_rows(item, installed, seen, domain_skills=domain_github_skills)
    return {"official": official, "pinned": pinned, "remote": remote, "github": github}


def skill_source_label(skill: dict) -> str:
    kind = skill.get("source_kind") or ("bundled" if skill.get("bundled") else "official")
    return {
        "bundled": "随应用附带",
        "official": "官方目录",
        "remote": "远程目录",
        "pinned": "专家指定 GitHub",
        "github": "GitHub 方向热门",
    }.get(kind, "Skill")


def recommended_skill_items(
    item: dict,
    *,
    installed_names: set[str] | None = None,
) -> list[dict]:
    """扁平列表（兼容旧调用）：官方 + 远程 + GitHub。"""
    groups = companion_skills_for_expert(item, installed_names=installed_names)
    return groups["official"] + groups["pinned"] + groups["remote"] + groups["github"]


def missing_recommended_skills(item: dict, *, installed_names: set[str] | None = None) -> list[dict]:
    return [s for s in recommended_skill_items(item, installed_names=installed_names) if not s.get("installed")]

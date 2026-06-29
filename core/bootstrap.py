from __future__ import annotations

import json
from pathlib import Path

from db.database import insert, query_all, query_one


PROVIDERS = [
    ("腾讯混元", "https://api.hunyuan.cloud.tencent.com/v1", "hunyuan-lite"),
    ("阿里通义千问", "https://dashscope.aliyuncs.com/compatible-mode/v1", "qwen-plus"),
    ("百度千帆", "https://qianfan.baidubce.com/v2", "ernie-4.0-turbo-8k"),
    ("智谱 GLM", "https://open.bigmodel.cn/api/paas/v4", "glm-4-flash"),
    ("Moonshot Kimi", "https://api.moonshot.cn/v1", "moonshot-v1-8k"),
    ("DeepSeek", "https://api.deepseek.com", "deepseek-v4-pro"),
    ("火山方舟/豆包", "https://ark.cn-beijing.volces.com/api/v3", "doubao-lite"),
    ("讯飞星火", "", "spark"),
    ("MiniMax", "https://api.minimax.chat/v1", "abab6.5s-chat"),
    ("零一万物", "https://api.lingyiwanwu.com/v1", "yi-lightning"),
    ("百川智能", "https://api.baichuan-ai.com/v1", "Baichuan4"),
    ("OpenAI", "https://api.openai.com/v1", "gpt-4o-mini"),
    ("Anthropic Claude", "", "claude-3-5-sonnet"),
    ("Google Gemini", "", "gemini-1.5-pro"),
    ("Mistral", "https://api.mistral.ai/v1", "mistral-small-latest"),
    ("Groq", "https://api.groq.com/openai/v1", "llama-3.1-8b-instant"),
    ("OpenRouter", "https://openrouter.ai/api/v1", "openai/gpt-4o-mini"),
    ("Together AI", "https://api.together.xyz/v1", "meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo"),
    ("Perplexity", "https://api.perplexity.ai", "sonar"),
    ("Ollama 本地模型", "http://localhost:11434/v1", "llama3.1"),
    ("LM Studio 本地模型", "http://localhost:1234/v1", "local-model"),
]

SKILLS = [
    ("read_file", "读取文件", "读取文本、Markdown、PDF、DOCX 文件内容", "low", "skills.file_skill.read_file"),
    ("summarize_document", "生成文件摘要", "根据文件文本生成简要摘要", "low", "skills.document_skill.summarize_text"),
    ("current_time", "获取当前时间", "返回当前日期时间", "low", "skills.time_skill.current_time"),
    ("generate_python_script", "生成 Python 脚本", "生成自动化脚本草稿", "low", "skills.code_skill.generate_python_script"),
    ("open_software", "打开外部软件", "启动已配置的软件工具", "medium", "skills.software_skill.open_software"),
    ("search_highway_standard", "查询公路机电标准", "搜索公路机电标准片段", "low", "skills.highway_mechatronics_skill.search_highway_standard"),
    ("generate_site_test_record", "生成现场测试记录", "生成现场测试记录模板", "low", "skills.highway_mechatronics_skill.generate_site_test_record"),
    ("generate_quality_inspection_table", "生成质量检验表", "生成质量检验评定表草稿", "low", "skills.highway_mechatronics_skill.generate_quality_inspection_table"),
    ("generate_bid_technical_response", "生成投标技术响应", "生成投标技术响应段落", "low", "skills.highway_mechatronics_skill.generate_bid_technical_response"),
    ("generate_acceptance_checklist", "生成验收检查清单", "生成机电工程验收检查清单", "low", "skills.highway_mechatronics_skill.generate_acceptance_checklist"),
]

SOFTWARE = ["VS Code", "PyCharm", "Keil uVision", "Chrome", "Edge", "Word", "Excel", "WPS Writer", "Git", "Windows Terminal", "Notepad++", "AutoCAD", "串口调试助手", "Modbus 调试工具", "网络测试工具"]


def bootstrap_seed_data() -> None:
    existing_models = {
        (r["provider_name"], r["model_name"])
        for r in query_all("SELECT provider_name, model_name FROM models")
    }
    for provider, api_base, model_name in PROVIDERS:
        if (provider, model_name) not in existing_models:
            insert("models", {
                "provider_name": provider,
                "provider_type": "openai_compatible",
                "api_base": api_base,
                "api_key": "",
                "model_name": model_name,
                "temperature": 1.0 if "deepseek-v4" in model_name else 0.7,
                "max_tokens": 8192 if "deepseek-v4" in model_name else 2000,
                "context_window": 1_000_000 if "deepseek-v4" in model_name else 128000,
                "thinking_enabled": 1 if "deepseek-v4" in model_name else 0,
                "reasoning_effort": "max" if "deepseek-v4" in model_name else "",
                "enabled": 0,
                "is_default": 0,
                "remark": "DeepSeek V4 Pro · 请填写 API Key 后启用" if model_name == "deepseek-v4-pro"
                else ("内置模板，请填写 API Key 后启用" if api_base else "预留模板"),
            })

    existing_skills = {r["skill_name"] for r in query_all("SELECT skill_name FROM skills")}
    for name, display, desc, risk, func in SKILLS:
        if name not in existing_skills:
            insert("skills", {
                "skill_name": name,
                "display_name": display,
                "description": desc,
                "input_schema": "{}",
                "output_schema": "{}",
                "risk_level": risk,
                "enabled": 1,
                "function_path": func,
            })

    existing_software = {r["software_name"] for r in query_all("SELECT software_name FROM software_tools")}
    for tool in SOFTWARE:
        if tool not in existing_software:
            insert("software_tools", {
                "software_name": tool,
                "software_type": "preset",
                "executable_path": "",
                "remark": "请配置本机可执行文件路径",
                "enabled": 0,
            })
    try:
        from agent_runtime.mcp_client import ensure_default_mcp_config
        ensure_default_mcp_config()
    except Exception:
        pass
    try:
        from core.remote_catalog import ensure_catalog_url_configured
        ensure_catalog_url_configured()
    except Exception:
        pass
    try:
        from core.ensure_deepseek_v4 import ensure_deepseek_v4_default
        ensure_deepseek_v4_default()
    except Exception:
        pass
    if not query_all("SELECT id FROM workflows LIMIT 1"):
        examples = [
            ("投标文件响应", ["导入招标文件", "总结", "提取技术要求", "生成投标响应大纲"]),
            ("标准测试记录", ["导入标准", "建立索引", "查询测试方法", "生成现场测试记录"]),
            ("项目资料方案", ["导入项目文件", "总结资料", "生成项目方案"]),
        ]
        for name, steps in examples:
            insert("workflows", {"workflow_name": name, "description": "第一阶段输出步骤说明", "steps_json": json.dumps(steps, ensure_ascii=False)})

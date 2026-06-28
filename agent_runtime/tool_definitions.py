from __future__ import annotations

TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "shell_run",
            "description": "在用户电脑上执行 Shell 命令（PowerShell / cmd），返回 stdout 和 stderr。可用于安装软件、运行脚本、管理文件等。",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "要执行的命令，例如 'dir C:\\Users' 或 'pip install flask'",
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "超时秒数，默认 60",
                    },
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "file_read",
            "description": "读取指定路径的文件内容并返回文本。适用于查看代码、配置文件、日志等。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "文件的绝对路径或相对路径",
                    },
                    "encoding": {
                        "type": "string",
                        "description": "文件编码，默认 utf-8",
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "file_write",
            "description": "将内容写入指定路径的文件。如果文件不存在则创建，父目录也会自动创建。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "文件的绝对路径",
                    },
                    "content": {
                        "type": "string",
                        "description": "要写入的文本内容",
                    },
                    "encoding": {
                        "type": "string",
                        "description": "文件编码，默认 utf-8",
                    },
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "file_list",
            "description": "列出指定目录下的文件和子目录，返回名称、大小、类型信息。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "要列出的目录路径",
                    },
                    "recursive": {
                        "type": "boolean",
                        "description": "是否递归列出子目录，默认 false",
                    },
                    "max_depth": {
                        "type": "integer",
                        "description": "递归最大深度，默认 2",
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "file_delete",
            "description": "删除指定路径的文件或空目录。这是高风险操作，删除后无法恢复。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "要删除的文件路径",
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "software_launch",
            "description": (
                "启动本机桌面程序。会自动从注册表、开始菜单、安装目录动态查找，"
                "无需事先配置软件别名。若窗口已打开则切换到前台。"
                "失败时可先调用 find_application 查看候选，再换名称或 exe 路径重试。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "应用名称（中文/英文均可）、或 exe 完整路径。如「酷狗」「微信」「Spotify」",
                    },
                    "args": {
                        "type": "string",
                        "description": "启动参数，例如要打开的文件路径或 URL",
                    },
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_application",
            "description": (
                "在本机搜索已安装应用（注册表 Uninstall、开始菜单、Program Files 等），"
                "返回候选列表与路径。打开不熟悉的软件前可先调用，再据此 software_launch。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "要搜索的应用名称，可尝试中文名、英文名、简称等不同写法",
                    },
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "open_url",
            "description": "在用户默认浏览器中打开指定 URL。不要用来替代本地桌面软件（如用网页版酷狗代替酷狗客户端）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "要打开的网址，例如 'https://www.google.com'",
                    },
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "office_word_create",
            "description": "生成一份 Word (.docx) 文档。你需要用你的专业知识生成详细、高质量的文档内容。每个章节的 body 应包含完整的段落文字，不是简短摘要。",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "文档标题",
                    },
                    "sections": {
                        "type": "array",
                        "description": "章节列表。每个章节的 body 必须是完整的正文内容（至少2-3段话），不要只写一句话概括。",
                        "items": {
                            "type": "object",
                            "properties": {
                                "heading": {"type": "string", "description": "章节标题"},
                                "body": {"type": "string", "description": "章节正文内容，要详细、专业、有深度，至少100字"},
                            },
                            "required": ["heading", "body"],
                        },
                    },
                    "filename": {
                        "type": "string",
                        "description": "输出文件名，例如 'report.docx'",
                    },
                },
                "required": ["title", "sections", "filename"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "office_excel_create",
            "description": "生成一份 Excel (.xlsx) 表格。需要提供标题、表头和数据行。",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "工作表标题",
                    },
                    "headers": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "列标题列表",
                    },
                    "rows": {
                        "type": "array",
                        "items": {
                            "type": "array",
                            "items": {},
                        },
                        "description": "数据行，每行是一个数组",
                    },
                    "filename": {
                        "type": "string",
                        "description": "输出文件名，例如 'data.xlsx'",
                    },
                },
                "required": ["title", "headers", "rows", "filename"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "office_ppt_create",
            "description": "生成一份高质量的 PowerPoint (.pptx) 演示文稿。你必须用你的专业知识精心设计每一页的内容。每页至少3-5个要点，每个要点是一句完整有信息量的话（不是几个词的罗列）。整个PPT至少8-12页。",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "演示文稿标题",
                    },
                    "slides": {
                        "type": "array",
                        "description": "幻灯片列表，至少8页。每页应有明确主题和3-5个有信息量的要点。",
                        "items": {
                            "type": "object",
                            "properties": {
                                "slide_title": {"type": "string", "description": "幻灯片标题，简洁有力"},
                                "bullets": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": "要点列表，每个要点是一句完整的话（15-40字），不是几个词的罗列。以'  '开头表示子级要点。",
                                },
                            },
                            "required": ["slide_title", "bullets"],
                        },
                    },
                    "filename": {
                        "type": "string",
                        "description": "输出文件名，例如 'presentation.pptx'",
                    },
                },
                "required": ["title", "slides", "filename"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "code_create",
            "description": "创建一个代码文件。LLM 生成完整代码内容，写入指定路径。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "代码文件路径，例如 'D:/projects/app.py'",
                    },
                    "content": {
                        "type": "string",
                        "description": "完整的代码内容",
                    },
                    "language": {
                        "type": "string",
                        "description": "编程语言，如 python, javascript, html",
                    },
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "keyboard_type",
            "description": "在当前焦点窗口中输入文字。支持中文（自动通过剪贴板粘贴）和英文。注意：此工具只能输入文字，不能按快捷键，快捷键请用 hotkey_press。",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "要输入的文本内容，支持中文和英文",
                    },
                    "interval": {
                        "type": "number",
                        "description": "每个字符之间的间隔秒数，默认 0.02",
                    },
                    "window_title": {
                        "type": "string",
                        "description": "目标窗口标题关键词；输入前会自动重新聚焦该窗口（权限确认后必需）",
                    },
                },
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "hotkey_press",
            "description": "按下键盘快捷键。在 ui_click 聚焦输入框后使用。不能输入文字。",
            "parameters": {
                "type": "object",
                "properties": {
                    "keys": {
                        "type": "string",
                        "description": "快捷键组合，用+连接。例如：'ctrl+f'、'ctrl+c'、'ctrl+v'、'alt+tab'、'enter'、'escape'、'tab'、'ctrl+a'",
                    },
                    "window_title": {
                        "type": "string",
                        "description": "目标窗口标题关键词；按键前会自动重新聚焦该窗口",
                    },
                },
                "required": ["keys"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "window_focus",
            "description": "将指定窗口切换到前台并获取焦点。title 为窗口标题关键词。GUI 操作前应先 window_focus。",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "窗口标题关键词，例如：酷狗、微信、Chrome",
                    },
                },
                "required": ["title"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_apps",
            "description": (
                "列出当前所有可见顶层窗口（标题、PID）。"
                "GUI 操作第一步：确认目标应用窗口标题，再 window_focus。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "max_items": {
                        "type": "integer",
                        "description": "最多返回窗口数，默认 50",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ui_locate",
            "description": (
                "【GUI 主路径】本地定位界面元素（UIA → OCR），无需 vision。"
                "返回像素坐标，供后续操作或 mouse_click 使用。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "target": {
                        "type": "string",
                        "description": "要查找的文字或控件名，如「搜索音乐」「文件传输助手」",
                    },
                    "window_title": {
                        "type": "string",
                        "description": "限定在某个窗口内查找，填窗口标题关键词，如「酷狗」「微信」",
                    },
                    "control_type": {
                        "type": "string",
                        "description": "可选控件类型：edit / button / text / menu / combo",
                    },
                    "method": {
                        "type": "string",
                        "description": "定位方式：auto（默认，UIA→OCR）、uia、ocr",
                    },
                    "exact": {
                        "type": "boolean",
                        "description": "是否精确匹配文字，默认 false（包含即可）",
                    },
                },
                "required": ["target"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ui_click",
            "description": (
                "【GUI 主路径】本地定位并点击界面元素（UIA → OCR）。"
                "Electron 应用（酷狗、微信等）优先用此工具，不要先截屏猜坐标。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "target": {
                        "type": "string",
                        "description": "要点击的文字或控件名",
                    },
                    "window_title": {
                        "type": "string",
                        "description": "窗口标题关键词",
                    },
                    "control_type": {
                        "type": "string",
                        "description": "可选：edit / button / text",
                    },
                    "method": {
                        "type": "string",
                        "description": "auto / uia / ocr",
                    },
                    "exact": {"type": "boolean"},
                    "clicks": {"type": "integer", "description": "点击次数，默认 1"},
                },
                "required": ["target"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "mouse_click",
            "description": "在屏幕指定坐标点击。仅 ui_locate 已给出坐标、或 ui_click 失败后的兜底，不要作为 GUI 首选。",
            "parameters": {
                "type": "object",
                "properties": {
                    "x": {
                        "type": "integer",
                        "description": "屏幕 X 坐标",
                    },
                    "y": {
                        "type": "integer",
                        "description": "屏幕 Y 坐标",
                    },
                    "button": {
                        "type": "string",
                        "description": "鼠标按键：left / right / middle，默认 left",
                    },
                    "clicks": {
                        "type": "integer",
                        "description": "点击次数，默认 1",
                    },
                },
                "required": ["x", "y"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "screen_capture",
            "description": (
                "截取屏幕并保存到文件。默认不传给 vision 模型。"
                "仅 ui_click/ui_locate 失败后的诊断；需要模型看图时设 for_vision=true。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "save_path": {
                        "type": "string",
                        "description": "截图保存路径，不提供则自动生成",
                    },
                    "for_vision": {
                        "type": "boolean",
                        "description": "为 true 时将截图注入 vision 模型分析（最后手段），默认 false",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "skill_install",
            "description": "从 URL 或 GitHub 仓库地址安装一个 Skill 技能包。",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "Skill 包的下载地址或 GitHub 仓库地址",
                    },
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "image_analyze",
            "description": "分析一张图片的内容。可以识别图片中的文字(OCR)、物体、场景、图表等。传入图片路径即可。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "图片文件的绝对路径",
                    },
                    "question": {
                        "type": "string",
                        "description": "关于图片的问题，例如'图片里有什么？'或'提取图中的文字'",
                    },
                },
                "required": ["path"],
            },
        },
    },
]

TOOL_RISK_LEVELS: dict[str, str] = {
    "shell_run": "medium",
    "file_read": "low",
    "file_write": "medium",
    "file_list": "low",
    "file_delete": "high",
    "software_launch": "medium",
    "find_application": "low",
    "open_url": "low",
    "office_word_create": "low",
    "office_excel_create": "low",
    "office_ppt_create": "low",
    "code_create": "medium",
    "keyboard_type": "high",
    "hotkey_press": "high",
    "window_focus": "medium",
    "list_apps": "low",
    "ui_locate": "low",
    "ui_click": "high",
    "mouse_click": "high",
    "screen_capture": "low",
    "skill_install": "medium",
    "image_analyze": "low",
}


def get_active_tools() -> list[dict]:
    """Return the merged list of built-in + installed tools, excluding disabled ones."""
    import json

    from core.settings_runtime import plugins_disabled
    from db.database import query_all
    from core.settings_store import get_setting

    disabled_raw = get_setting("disabled_tools", "[]")
    try:
        disabled_set = set(json.loads(disabled_raw))
    except Exception:
        disabled_set = set()

    active: list[dict] = []
    for tool in TOOLS:
        name = tool.get("function", {}).get("name", "")
        if name not in disabled_set:
            active.append(tool)

    if plugins_disabled():
        return active

    rows = query_all(
        "SELECT manifest_json FROM installed_skill_packages WHERE enabled = 1"
    )
    for row in rows:
        manifest_raw = row.get("manifest_json", "")
        if not manifest_raw:
            continue
        try:
            manifest = json.loads(manifest_raw)
        except Exception:
            continue
        for tool_def in manifest.get("tools", []):
            t_name = tool_def.get("name", "")
            if not t_name or t_name in disabled_set:
                continue
            active.append({
                "type": "function",
                "function": {
                    "name": t_name,
                    "description": tool_def.get("description", ""),
                    "parameters": tool_def.get("parameters", {
                        "type": "object", "properties": {}, "required": []
                    }),
                },
            })

    from agent_runtime.mcp_client import ensure_mcp_tools_loaded, get_mcp_tool_definitions, mcp_enabled
    if mcp_enabled():
        ensure_mcp_tools_loaded()
        for tool in get_mcp_tool_definitions():
            t_name = tool.get("function", {}).get("name", "")
            if t_name and t_name not in disabled_set:
                active.append(tool)

    return active


def get_tool_risk_level(name: str) -> str:
    if name in TOOL_RISK_LEVELS:
        return TOOL_RISK_LEVELS[name]
    if name.startswith("mcp__"):
        from agent_runtime.mcp_client import get_mcp_tool_risk
        return get_mcp_tool_risk(name)
    return "medium"

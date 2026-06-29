from __future__ import annotations

from agent_runtime.tool_definitions import TOOL_RISK_LEVELS, get_tool_risk_level

HIGH_RISK_TOOLS = {"file_delete", "keyboard_type", "mouse_click"}

MEDIUM_RISK_TOOLS = {"shell_run", "file_write", "software_launch", "code_create", "skill_install"}

LOW_RISK_TOOLS = {"file_read", "file_list", "open_url", "web_search", "web_fetch",
                  "office_word_create",
                  "office_excel_create", "office_ppt_create", "screen_capture", "list_apps",
                  "ui_locate", "library_list", "library_search"}


def get_risk_level(tool_name: str) -> str:
    return get_tool_risk_level(tool_name)


def requires_confirmation(tool_name: str, full_access: bool = False) -> bool:
    if full_access:
        return False
    from core.settings_store import get_bool

    risk = get_risk_level(tool_name)
    if get_bool("auto_execute_low_risk", False) and risk in ("low", "medium"):
        return False
    if not get_bool("confirm_dangerous_ops", True):
        return False
    return risk == "high"


def describe_risk(tool_name: str) -> str:
    descriptions = {
        "shell_run": "执行系统命令",
        "file_read": "读取文件",
        "file_write": "写入/创建文件",
        "file_list": "列出目录内容",
        "file_delete": "删除文件（不可恢复）",
        "software_launch": "启动程序",
        "open_url": "打开网页",
        "web_search": "联网搜索",
        "web_fetch": "抓取网页正文",
        "office_word_create": "生成 Word 文档",
        "office_excel_create": "生成 Excel 表格",
        "office_ppt_create": "生成 PPT 演示文稿",
        "code_create": "创建代码文件",
        "keyboard_type": "模拟键盘输入",
        "mouse_click": "模拟鼠标点击",
        "screen_capture": "截取屏幕",
        "list_apps": "列出可见窗口",
        "ui_locate": "定位界面元素",
        "ui_click": "点击界面元素",
        "window_focus": "聚焦窗口",
        "skill_install": "安装技能包",
        "library_list": "列出资料库文件",
        "library_search": "检索资料库内容",
    }
    return descriptions.get(tool_name, tool_name)

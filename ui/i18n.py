"""UI 国际化：所有界面文案集中管理，便于扩展更多语言。"""

from __future__ import annotations

from core.settings_store import get_setting
from core.app_identity import APP_NAME, APP_VERSION

_STRINGS: dict[str, dict[str, str]] = {
    "zh": {
        # --- 主窗口 ---
        "window_title": "{app_name}",
        "status_model": "模型",
        "status_project": "项目",
        "status_no_model": "未设置模型",
        "status_no_project": "未设置项目",
        "status_applied": "✓ 设置已应用 — 字体:{font}  主题:{theme}  简洁:{compact}",
        "toggle_results": "◧ 结果面板",
        "result_artifacts": "产物",
        "result_files": "文件",
        "result_preview": "预览",
        "result_changes": "变更",
        "result_refresh": "刷新",
        "workspace_unset": "未设置工作目录",
        # --- 侧栏 ---
        "nav_assistant": "助理",
        "nav_project": "项目",
        "nav_expert": "专家",
        "nav_automation": "自动化",
        "nav_more": "更多",
        "nav_skills": "技能",
        "nav_connectors": "快捷启动",
        "nav_resources": "资料库",
        "nav_inspiration": "灵感",
        "new_task": "＋  新建任务",
        "search_tasks": "搜索任务…",
        "task_section": "任务",
        "default_user": "🐷🐷Buddy 用户",
        # --- 对话 ---
        "chat_model": "模型",
        "chat_input_placeholder": "今天想让我做些什么？拖拽图片/音频到此处，或点击 ＋ 附加文件",
        "chat_auto": "🤖 自动",
        "chat_auto_tip": "开启后自动选用默认模型",
        "chat_skill_store": "⚡ 技能商店",
        "chat_skill_store_tip": "安装 / 管理 Skill\n· 推荐技能 → 安装\n·「我的 Skill」→ 查看编辑 SKILL.md",
        "chat_my_skills": "📄 我的 Skill",
        "chat_my_skills_tip": "直接打开「我的 Skill」，查看 / 编辑 SKILL.md",
        "chat_mcp": "MCP",
        "chat_mcp_tip": "配置 MCP 外部工具（Filesystem、GitHub、Fetch 等）",
        "chat_perm_default": "🔒 默认权限",
        "chat_perm_full": "🔓 完全访问",
        "chat_perm_tip": "完全访问：跳过高风险确认；默认：需确认危险操作",
        "chat_stop": "停止",
        "chat_stop_tip": "停止生成",
        "chat_attach": "＋",
        "chat_attach_tip": "附加文件",
        "chat_workspace_tip": "工作目录",
        "chat_local_search": "本地检索（不调用模型）",
        "send_enter": "发送 (Enter)",
        "send_ctrl_enter": "发送 (Ctrl+Enter)",
        "mode_ask": "问一问",
        "mode_craft": "做一做",
        "mode_plan": "想一想",
        # --- 菜单 ---
        "menu_app": "{app_name}",
        "menu_edit": "编辑(E)",
        "menu_window": "窗口(W)",
        "menu_help": "帮助(H)",
        "menu_settings": "设置…",
        "menu_about": "关于 {app_name} {version}",
        "menu_quit": "退出",
        "menu_undo": "撤销输入",
        "menu_cut": "剪切",
        "menu_copy": "复制",
        "menu_paste": "粘贴",
        "menu_clear_input": "清空输入框",
        "menu_clear_chat": "清空当前对话显示",
        "menu_toggle_sidebar": "显示/隐藏侧边栏",
        "menu_toggle_results": "显示/隐藏结果面板",
        "menu_maximize": "最大化/还原",
        "menu_minimize": "最小化",
        "menu_help_doc": "使用帮助",
        "menu_feedback": "提交反馈…",
        "menu_logs": "查看运行日志",
        "menu_open_settings": "打开设置",
        # --- 设置对话框 ---
        "settings.title": "设置",
        "settings.nav.account": "账户管理",
        "settings.nav.system": "系统设置",
        "settings.nav.agent": "智能体设置",
        "settings.nav.memory": "记忆",
        "settings.nav.models": "模型",
        "settings.nav.tools": "工具管理",
        "settings.nav.assistant": "助理设置",
        "settings.nav.personalization": "个性化",
        "settings.nav.data": "数据管理",
        "settings.nav.security": "安全中心",
        "settings.nav.help": "帮助与反馈",
        "settings.feedback.saved": "设置已保存并应用",
        "settings.feedback.language": "显示语言已切换",
        "settings.feedback.font": "字体大小已调整",
        "settings.feedback.compact": "简洁模式已更新",
        "settings.feedback.send_key": "发送快捷键已更新",
        "settings.feedback.theme": "主题已切换",
        "settings.feedback.sidebar": "侧边栏位置已调整",
        "settings.feedback.workspace": "工作空间路径已更新",
        "settings.feedback.username": "用户名已更新",
        "settings.system.language": "显示语言",
        "settings.system.language_desc": "界面显示语言",
        "settings.system.font": "字体大小",
        "settings.system.font_desc": "调整界面字体大小",
        "settings.system.font_small": "小",
        "settings.system.font_large": "大",
        "settings.system.preview": "预览效果",
        "settings.system.preview_text": "{app_name} — 这是一段预览文字，用于查看字体与主题效果。",
        "settings.system.compact": "简洁模式",
        "settings.system.compact_desc": "减少界面元素间距",
        "settings.system.send_key": "发送消息",
        "settings.system.send_key_desc": "发送消息快捷键",
        "settings.system.skill_update": "技能自动更新",
        "settings.system.skill_update_desc": "启动时从 source_url 重新拉取已安装 Skill（仅 URL 安装包）",
        "settings.system.auto_install": "非高风险技能自动安装",
        "settings.system.auto_install_desc": "自动安装经过安全审核的低风险技能",
        "settings.system.lock_remote": "锁屏远程",
        "settings.system.lock_remote_desc": "锁屏后允许远程操作",
        "settings.system.workspace": "默认工作空间存储路径",
        "settings.system.workspace_desc": "文件和项目的默认保存位置",
        "settings.system.workspace_ph": "选择默认工作空间路径",
        "settings.browse": "浏览",
        "settings.account.username": "用户名",
        "settings.account.username_desc": "显示在对话中的名称",
        "settings.account.username_ph": "设置用户名",
        "settings.theme.dark": "深色",
        "settings.theme.light": "浅色",
        "settings.theme.system": "跟随系统",
        "settings.sidebar.left": "左侧",
        "settings.sidebar.right": "右侧",
        "settings.lang.zh": "简体中文",
        "settings.lang.en": "English",
        "settings.send.enter": "Enter",
        "settings.send.ctrl_enter": "Ctrl+Enter",
        "settings.font.default": "默认",
        "settings.models.add": "添加模型",
        "settings.models.saved": "已保存模型",
        "settings.models.custom": "自定义模型",
        "settings.models.config_path": "配置文件: {path}",
        "settings.models.default": "默认",
        "settings.models.edit": "编辑",
        "settings.models.delete": "删除",
        "settings.models.set_default": "设为默认",
        "settings.common.on": "开",
        "settings.common.off": "关",
    },
    "en": {
        "window_title": "{app_name}",
        "status_model": "Model",
        "status_project": "Project",
        "status_no_model": "No model configured",
        "status_no_project": "No project selected",
        "status_applied": "✓ Settings applied — Font:{font}  Theme:{theme}  Compact:{compact}",
        "toggle_results": "◧ Results",
        "result_artifacts": "Artifacts",
        "result_files": "Files",
        "result_preview": "Preview",
        "result_changes": "Changes",
        "result_refresh": "Refresh",
        "workspace_unset": "No workspace set",
        "nav_assistant": "Assistant",
        "nav_project": "Projects",
        "nav_expert": "Experts",
        "nav_automation": "Automation",
        "nav_more": "More",
        "nav_skills": "Skills",
        "nav_connectors": "Quick Launch",
        "nav_resources": "Resources",
        "nav_inspiration": "Inspiration",
        "new_task": "＋  New Task",
        "search_tasks": "Search tasks…",
        "task_section": "Tasks",
        "default_user": "🐷🐷Buddy User",
        "chat_model": "Model",
        "chat_input_placeholder": "What would you like me to do today? Drop images/audio here, or click + to attach",
        "chat_auto": "🤖 Auto",
        "chat_auto_tip": "Automatically use the default model when enabled",
        "chat_skill_store": "⚡ Skill Store",
        "chat_skill_store_tip": "Install / manage Skills\n· Recommended → Install\n· My Skills → Edit SKILL.md",
        "chat_my_skills": "📄 My Skills",
        "chat_my_skills_tip": "Open My Skills to view / edit SKILL.md",
        "chat_mcp": "MCP",
        "chat_mcp_tip": "Configure MCP servers (Filesystem, GitHub, Fetch, …)",
        "chat_perm_default": "🔒 Default",
        "chat_perm_full": "🔓 Full Access",
        "chat_perm_tip": "Full access skips high-risk confirmations; Default requires approval",
        "chat_stop": "Stop",
        "chat_stop_tip": "Stop generation",
        "chat_attach": "＋",
        "chat_attach_tip": "Attach files",
        "chat_workspace_tip": "Workspace folder",
        "chat_local_search": "Local search (no LLM)",
        "send_enter": "Send (Enter)",
        "send_ctrl_enter": "Send (Ctrl+Enter)",
        "mode_ask": "Ask",
        "mode_craft": "Craft",
        "mode_plan": "Plan",
        "menu_app": "{app_name}",
        "menu_edit": "Edit",
        "menu_window": "Window",
        "menu_help": "Help",
        "menu_settings": "Settings…",
        "menu_about": "About {app_name} {version}",
        "menu_quit": "Quit",
        "menu_undo": "Undo Input",
        "menu_cut": "Cut",
        "menu_copy": "Copy",
        "menu_paste": "Paste",
        "menu_clear_input": "Clear Input",
        "menu_clear_chat": "Clear Chat View",
        "menu_toggle_sidebar": "Toggle Sidebar",
        "menu_toggle_results": "Toggle Results Panel",
        "menu_maximize": "Maximize / Restore",
        "menu_minimize": "Minimize",
        "menu_help_doc": "Help",
        "menu_feedback": "Send Feedback…",
        "menu_logs": "View Logs",
        "menu_open_settings": "Open Settings",
        "settings.title": "Settings",
        "settings.nav.account": "Account",
        "settings.nav.system": "System",
        "settings.nav.agent": "Agent",
        "settings.nav.memory": "Memory",
        "settings.nav.models": "Models",
        "settings.nav.tools": "Tools",
        "settings.nav.assistant": "Assistant",
        "settings.nav.personalization": "Personalization",
        "settings.nav.data": "Data",
        "settings.nav.security": "Security",
        "settings.nav.help": "Help & Feedback",
        "settings.feedback.saved": "Settings saved and applied",
        "settings.feedback.language": "Display language updated",
        "settings.feedback.font": "Font size updated",
        "settings.feedback.compact": "Compact mode updated",
        "settings.feedback.send_key": "Send shortcut updated",
        "settings.feedback.theme": "Theme updated",
        "settings.feedback.sidebar": "Sidebar position updated",
        "settings.feedback.workspace": "Workspace path updated",
        "settings.feedback.username": "Username updated",
        "settings.system.language": "Display Language",
        "settings.system.language_desc": "Interface display language",
        "settings.system.font": "Font Size",
        "settings.system.font_desc": "Adjust interface font size",
        "settings.system.font_small": "S",
        "settings.system.font_large": "L",
        "settings.system.preview": "Preview",
        "settings.system.preview_text": "{app_name} — Sample text to preview font and theme.",
        "settings.system.compact": "Compact Mode",
        "settings.system.compact_desc": "Reduce spacing between UI elements",
        "settings.system.send_key": "Send Message",
        "settings.system.send_key_desc": "Keyboard shortcut to send messages",
        "settings.system.skill_update": "Auto-update Skills",
        "settings.system.skill_update_desc": "On startup re-fetch URL-installed skills from source_url",
        "settings.system.auto_install": "Auto-install Low-risk Skills",
        "settings.system.auto_install_desc": "Install low-risk skills that passed security review",
        "settings.system.lock_remote": "Remote While Locked",
        "settings.system.lock_remote_desc": "Allow remote operations when the screen is locked",
        "settings.system.workspace": "Default Workspace Path",
        "settings.system.workspace_desc": "Default save location for files and projects",
        "settings.system.workspace_ph": "Select default workspace path",
        "settings.browse": "Browse",
        "settings.account.username": "Username",
        "settings.account.username_desc": "Name shown in conversations",
        "settings.account.username_ph": "Set username",
        "settings.theme.dark": "Dark",
        "settings.theme.light": "Light",
        "settings.theme.system": "Follow System",
        "settings.sidebar.left": "Left",
        "settings.sidebar.right": "Right",
        "settings.lang.zh": "简体中文",
        "settings.lang.en": "English",
        "settings.send.enter": "Enter",
        "settings.send.ctrl_enter": "Ctrl+Enter",
        "settings.font.default": "Default",
        "settings.models.add": "Add Model",
        "settings.models.saved": "Saved Models",
        "settings.models.custom": "Custom Models",
        "settings.models.config_path": "Config file: {path}",
        "settings.models.default": "Default",
        "settings.models.edit": "Edit",
        "settings.models.delete": "Delete",
        "settings.models.set_default": "Set Default",
        "settings.common.on": "On",
        "settings.common.off": "Off",
    },
}

# 打开设置对话框的实例，语言切换时统一刷新
_open_settings_dialogs: list = []


def register_settings_dialog(dialog) -> None:
    if dialog not in _open_settings_dialogs:
        _open_settings_dialogs.append(dialog)


def unregister_settings_dialog(dialog) -> None:
    try:
        _open_settings_dialogs.remove(dialog)
    except ValueError:
        pass


def retranslate_all_settings_dialogs() -> None:
    for dlg in list(_open_settings_dialogs):
        if dlg is not None and hasattr(dlg, "retranslate_ui"):
            dlg.retranslate_ui()


def current_lang() -> str:
    lang = get_setting("language", "简体中文")
    return "en" if lang == "English" else "zh"


def t(key: str, **kwargs) -> str:
    kwargs.setdefault("app_name", APP_NAME)
    kwargs.setdefault("version", APP_VERSION)
    lang = current_lang()
    text = _STRINGS.get(lang, _STRINGS["zh"]).get(key, _STRINGS["zh"].get(key, key))
    if kwargs:
        try:
            return text.format(**kwargs)
        except Exception:
            return text
    return text


def retranslate_main_window(window) -> None:
    from ui.app_menu import retranslate_app_menus

    window.setWindowTitle(t("window_title"))

    if hasattr(window, "_toggle_result_btn"):
        window._toggle_result_btn.setText(t("toggle_results"))

    if hasattr(window, "_results"):
        tabs = getattr(window._results, "_tabs", {})
        mapping = {
            "artifacts": "result_artifacts",
            "files": "result_files",
            "preview": "result_preview",
            "changes": "result_changes",
        }
        for key, i18n_key in mapping.items():
            btn = tabs.get(key)
            if btn:
                btn.setText(t(i18n_key))

    if hasattr(window, "_sidebar") and hasattr(window._sidebar, "retranslate_ui"):
        window._sidebar.retranslate_ui()

    if hasattr(window, "_conversation") and hasattr(window._conversation, "retranslate_ui"):
        window._conversation.retranslate_ui()

    retranslate_app_menus(window)

    if hasattr(window, "_refresh_status"):
        window._refresh_status()

    retranslate_all_settings_dialogs()

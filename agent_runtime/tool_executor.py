from __future__ import annotations

import json
import os
import shutil
import subprocess
import webbrowser
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime
from pathlib import Path
from collections.abc import Iterator
from typing import Any

from artifacts.artifact_manager import ensure_export_dir, register_artifact
from agent_runtime.gui_hooks import focus_window_by_title, prepare_for_gui_automation
from agent_runtime.gui_session import (
    ensure_target_foreground,
    resolve_window_title,
    set_active_window,
)
from agent_runtime.dialog_guard import dismiss_blocking_dialogs, format_dismiss_note

_TRUNCATE_LIMIT = 8000
_TOOL_TASK_ID: ContextVar[int | None] = ContextVar("tool_task_id", default=None)
_TOOL_PROJECT_ID: ContextVar[int | None] = ContextVar("tool_project_id", default=None)

_DIALOG_CHECK_TOOLS = frozenset({
    "shell_run", "software_launch", "file_delete", "file_write",
    "ui_click", "ui_locate", "keyboard_type", "hotkey_press",
    "mouse_click", "window_focus", "open_url",
})


@contextmanager
def tool_context(task_id: int | None = None, project_id: int | None = None) -> Iterator[None]:
    task_token = _TOOL_TASK_ID.set(task_id)
    project_token = _TOOL_PROJECT_ID.set(project_id)
    try:
        yield
    finally:
        _TOOL_PROJECT_ID.reset(project_token)
        _TOOL_TASK_ID.reset(task_token)


def execute_tool(name: str, args: dict[str, Any]) -> str:
    from core.settings_runtime import is_tool_allowed

    blocked = is_tool_allowed(name)
    if blocked:
        return blocked

    from agent_runtime.mcp_client import execute_mcp_tool, is_mcp_tool
    if is_mcp_tool(name):
        try:
            return execute_mcp_tool(name, args)
        except Exception as exc:
            return f"MCP tool error ({name}): {exc}"

    handler = _HANDLERS.get(name)
    if not handler:
        return f"错误：未知工具 '{name}'"
    try:
        result = handler(args)
    except Exception as exc:
        return f"工具执行出错 ({name}): {exc}"

    if name in _DIALOG_CHECK_TOOLS:
        try:
            dismissed = dismiss_blocking_dialogs()
            if dismissed:
                result = result + format_dismiss_note(dismissed)
        except Exception:
            pass
    return result


def _refocus_target(args: dict) -> str:
    """Refocus GUI target after permission pause (user clicked back to Agent)."""
    title = resolve_window_title(args.get("window_title", ""))
    if not title:
        return ""
    result = ensure_target_foreground(title)
    if result:
        return "已重新聚焦目标窗口。"
    return ""


def _shell_run(args: dict) -> str:
    command = args["command"]
    timeout = args.get("timeout", 60)
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )
        output = f"exit_code: {result.returncode}\n"
        if result.stdout:
            stdout = result.stdout[:_TRUNCATE_LIMIT]
            output += f"stdout:\n{stdout}\n"
        if result.stderr:
            stderr = result.stderr[:_TRUNCATE_LIMIT]
            output += f"stderr:\n{stderr}\n"
        if not result.stdout and not result.stderr:
            output += "(no output)\n"
        return output.strip()
    except subprocess.TimeoutExpired:
        return f"命令超时（{timeout}秒）: {command}"


def _file_read(args: dict) -> str:
    path = Path(args["path"])
    encoding = args.get("encoding", "utf-8")
    if not path.exists():
        return f"文件不存在: {path}"
    if not path.is_file():
        return f"路径不是文件: {path}"
    try:
        content = path.read_text(encoding=encoding, errors="replace")
        if len(content) > _TRUNCATE_LIMIT:
            return content[:_TRUNCATE_LIMIT] + f"\n\n... (文件过大，已截断，共 {len(content)} 字符)"
        return content
    except Exception as exc:
        return f"读取失败: {exc}"


def _file_write(args: dict) -> str:
    path = Path(args["path"])
    content = args["content"]
    encoding = args.get("encoding", "utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding=encoding)
    return f"文件已写入: {path} ({len(content)} 字符)"


def _file_list(args: dict) -> str:
    path = Path(args["path"])
    recursive = args.get("recursive", False)
    max_depth = args.get("max_depth", 2)
    if not path.exists():
        return f"路径不存在: {path}"
    if not path.is_dir():
        return f"路径不是目录: {path}"

    ignored = {".git", ".idea", ".venv", "venv", "__pycache__", "node_modules", ".mypy_cache"}
    lines: list[str] = []

    def _walk(p: Path, depth: int, prefix: str = "") -> None:
        if depth > max_depth:
            return
        try:
            entries = sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
        except PermissionError:
            lines.append(f"{prefix}[权限不足]")
            return
        for entry in entries:
            if entry.name in ignored:
                continue
            if entry.is_dir():
                lines.append(f"{prefix}📁 {entry.name}/")
                if recursive:
                    _walk(entry, depth + 1, prefix + "  ")
            else:
                size = _format_size(entry)
                lines.append(f"{prefix}📄 {entry.name}  ({size})")

    _walk(path, 0)
    if not lines:
        return f"目录为空: {path}"
    result = f"目录: {path}\n" + "\n".join(lines[:200])
    if len(lines) > 200:
        result += f"\n... (共 {len(lines)} 项，已截断)"
    return result


def _file_delete(args: dict) -> str:
    path = Path(args["path"])
    if not path.exists():
        return f"路径不存在: {path}"
    if path.is_file():
        path.unlink()
        return f"文件已删除: {path}"
    if path.is_dir():
        if any(path.iterdir()):
            return f"目录非空，拒绝删除: {path}。如需删除非空目录，请使用 shell_run 执行 rmdir /s。"
        path.rmdir()
        return f"空目录已删除: {path}"
    return f"无法删除: {path}"


def _find_application(args: dict) -> str:
    """列出与本机名称可能匹配的应用（注册表/开始菜单/安装目录）。"""
    from agent_runtime.app_resolver import format_matches_for_agent, resolve_application

    name = args["name"]
    matches = resolve_application(name, limit=8)
    return format_matches_for_agent(name, matches)


def _software_launch(args: dict) -> str:
    from agent_runtime.app_resolver import (
        find_best_executable,
        format_matches_for_agent,
        launch_match,
        resolve_application,
    )

    name = args["name"]
    extra_args = args.get("args", "")

    key = name.strip()
    if key:
        focus_result = focus_window_by_title(key)
        if not focus_result.startswith("未找到"):
            set_active_window(key)
            title = focus_result.replace("已将窗口置于前台: ", "")
            return f"窗口已存在，已切换到前台: {title}"

    if Path(name).exists() and Path(name).is_file():
        os.startfile(name)
        return f"已启动: {name}"

    exe_path, hint = find_best_executable(name)
    if exe_path:
        try:
            msg = launch_match(exe_path, name)
            set_active_window(name)
            if extra_args:
                msg += f"（启动参数: {extra_args}）"
            return f"{msg}\n定位方式: {hint}"
        except Exception as exc:
            return f"找到程序但启动失败 ({hint}): {exc}"

    matches = resolve_application(name, limit=6)
    detail = format_matches_for_agent(name, matches)
    return (
        f"未能自动启动「{name}」。\n"
        f"{detail}\n"
        "可调用 find_application 查看候选，或用更精确的名称 / exe 路径重试 software_launch。"
    )


def _open_url(args: dict) -> str:
    url = args["url"]
    webbrowser.open(url)
    return f"已在浏览器中打开: {url}"


def _web_search(args: dict) -> str:
    from utils.web_access import format_search_results, search_web

    query = (args.get("query") or "").strip()
    if not query:
        return "错误：请提供 query 搜索词。"
    limit = int(args.get("limit") or 8)
    results = search_web(query, max_results=limit)
    return format_search_results(query, results)


def _web_fetch(args: dict) -> str:
    from utils.web_access import fetch_web_page

    url = (args.get("url") or "").strip()
    if not url:
        return "错误：请提供 url。"
    max_chars = int(args.get("max_chars") or 12000)
    try:
        page = fetch_web_page(url, max_chars=max_chars)
    except Exception as exc:
        return f"网页抓取失败：{exc}"
    title = page.get("title") or url
    text = page.get("text") or ""
    return f"# {title}\n\nURL: {page.get('url') or url}\n\n{text}"


def _office_word_create(args: dict) -> str:
    from adapters.office_word_adapter import create_word_document, normalize_word_sections, validate_word_input

    title = args.get("title", "文档")
    filename = args.get("filename", f"{title}.docx")
    if not filename.endswith(".docx"):
        filename += ".docx"
    sections = normalize_word_sections(
        sections=args.get("sections"),
        content=args.get("content"),
    )
    validate_word_input(sections=sections)
    path = create_word_document(title, sections, filename)
    _register_artifact(str(path), filename, "docx")
    return f"Word 文档已生成: {path}"


def _office_excel_create(args: dict) -> str:
    from adapters.office_excel_adapter import create_excel_workbook, validate_excel_input

    filename = args.get("filename", f"{args.get('title', 'workbook')}.xlsx")
    if not filename.endswith(".xlsx"):
        filename += ".xlsx"

    sheets = args.get("sheets")
    title = args.get("title", "")
    headers = args.get("headers")
    rows = args.get("rows")
    validate_excel_input(title=title, headers=headers, rows=rows, sheets=sheets)

    if sheets:
        path = create_excel_workbook(
            title=title,
            output_name=filename,
            sheets=sheets,
        )
    else:
        path = create_excel_workbook(title or "Sheet1", headers or [], rows or [], filename)

    _register_artifact(str(path), filename, "xlsx")
    return f"Excel 表格已生成: {path}"


def _office_ppt_create(args: dict) -> str:
    from adapters.office_ppt_adapter import create_presentation
    title = args["title"]
    slides = [(s["slide_title"], s["bullets"]) for s in args["slides"]]
    filename = args.get("filename", f"{title}.pptx")
    if not filename.endswith(".pptx"):
        filename += ".pptx"
    path = create_presentation(title, slides, filename)
    _register_artifact(str(path), filename, "pptx")
    return f"PPT 演示文稿已生成: {path}"


def _code_create(args: dict) -> str:
    path = Path(args["path"])
    content = args["content"]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    _register_artifact(str(path), path.name, path.suffix.lstrip(".") or "txt")
    return f"代码文件已创建: {path} ({len(content)} 字符)"


def _window_focus(args: dict) -> str:
    title = args.get("title", "")
    prepare_for_gui_automation(0.1)
    result = focus_window_by_title(title)
    if not result.startswith("未找到"):
        set_active_window(title)
    return result


def _list_apps(args: dict) -> str:
    """List visible top-level windows (WorkBuddy window_manager list)."""
    max_items = int(args.get("max_items", 50))
    try:
        import uiautomation as auto
    except ImportError:
        return "list_apps 需要 uiautomation: pip install uiautomation"

    lines: list[str] = []
    for win in auto.GetRootControl().GetChildren():
        title = (win.Name or "").strip()
        if not title:
            continue
        try:
            pid = win.ProcessId
        except Exception:
            pid = 0
        try:
            cls = win.ClassName or ""
        except Exception:
            cls = ""
        suffix = f", class={cls}" if cls else ""
        lines.append(f"- {title} (pid={pid}{suffix})")

    if not lines:
        return "未找到可见窗口"
    lines.sort(key=lambda s: s.lower())
    if len(lines) > max_items:
        extra = len(lines) - max_items
        lines = lines[:max_items]
        lines.append(f"... 另有 {extra} 个窗口未列出")
    return "可见窗口：\n" + "\n".join(lines)


def _keyboard_type(args: dict) -> str:
    """Type text into the currently focused window.

    For Chinese/non-ASCII text: copies to clipboard then pastes (Ctrl+V).
    For ASCII text: types directly.
    Handles \\n as Enter key press.
    """
    text = args["text"]
    interval = args.get("interval", 0.02)
    import time

    prepare_for_gui_automation(0.1)
    refocus = _refocus_target(args)

    try:
        import pyautogui
        pyautogui.PAUSE = 0.02
    except ImportError:
        return "键盘输入需要安装 pyautogui: pip install pyautogui"

    if text == "\n" or text == "\\n":
        pyautogui.press("enter")
        prefix = f"{refocus} " if refocus else ""
        return f"{prefix}已按下回车键"

    if not text.isascii():
        try:
            import pyperclip
        except ImportError:
            try:
                subprocess.run(["pip", "install", "pyperclip"], capture_output=True, timeout=30)
                import pyperclip
            except Exception:
                pass

        try:
            import pyperclip
            old_clipboard = ""
            try:
                old_clipboard = pyperclip.paste()
            except Exception:
                pass
            pyperclip.copy(text)
            time.sleep(0.1)
            pyautogui.hotkey("ctrl", "v")
            time.sleep(0.2)
            try:
                pyperclip.copy(old_clipboard)
            except Exception:
                pass
            return f"{refocus + ' ' if refocus else ''}已输入文本: {text[:30]}{'...' if len(text) > 30 else ''} ({len(text)} 字符)"
        except Exception:
            pass

        try:
            subprocess.run(
                ["powershell", "-Command", f"Set-Clipboard -Value '{text.replace(chr(39), chr(39)+chr(39))}'"],
                capture_output=True, timeout=5,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            time.sleep(0.1)
            pyautogui.hotkey("ctrl", "v")
            time.sleep(0.2)
            return f"{refocus + ' ' if refocus else ''}已输入文本: {text[:30]}{'...' if len(text) > 30 else ''} ({len(text)} 字符)"
        except Exception as exc:
            return f"中文输入失败: {exc}"

    parts = text.split("\\n")
    for i, part in enumerate(parts):
        if part:
            pyautogui.typewrite(part, interval=interval)
        if i < len(parts) - 1:
            pyautogui.press("enter")
            time.sleep(0.1)
    prefix = f"{refocus} " if refocus else ""
    return f"{prefix}已输入文本 ({len(text)} 字符)"


def _hotkey_press(args: dict) -> str:
    """Press a keyboard shortcut or special key."""
    keys_str = args["keys"]
    import time

    prepare_for_gui_automation(0.05)
    refocus = _refocus_target(args)

    try:
        import pyautogui
        pyautogui.PAUSE = 0.02
    except ImportError:
        return "快捷键需要安装 pyautogui: pip install pyautogui"

    keys_lower = keys_str.strip().lower()

    single_keys = {
        "enter": "enter", "return": "enter", "回车": "enter",
        "tab": "tab", "escape": "escape", "esc": "escape",
        "space": "space", "backspace": "backspace", "delete": "delete",
        "up": "up", "down": "down", "left": "left", "right": "right",
        "home": "home", "end": "end", "pageup": "pageup", "pagedown": "pagedown",
        "f1": "f1", "f2": "f2", "f3": "f3", "f4": "f4", "f5": "f5",
        "f6": "f6", "f7": "f7", "f8": "f8", "f9": "f9", "f10": "f10",
        "f11": "f11", "f12": "f12",
    }

    if keys_lower in single_keys:
        pyautogui.press(single_keys[keys_lower])
        return f"已按下: {keys_str}"

    if "+" in keys_str:
        parts = [k.strip().lower() for k in keys_str.split("+")]
        key_map = {
            "ctrl": "ctrl", "control": "ctrl",
            "alt": "alt", "shift": "shift",
            "win": "win", "windows": "win", "super": "win",
            "enter": "enter", "return": "enter",
            "tab": "tab", "escape": "escape", "esc": "escape",
            "space": "space", "backspace": "backspace", "delete": "delete",
            "up": "up", "down": "down", "left": "left", "right": "right",
        }
        mapped = [key_map.get(k, k) for k in parts]
        pyautogui.hotkey(*mapped)
        time.sleep(0.1)
        prefix = f"{refocus} " if refocus else ""
        return f"{prefix}已按下快捷键: {keys_str}"

    pyautogui.press(keys_lower)
    prefix = f"{refocus} " if refocus else ""
    return f"{prefix}已按下: {keys_str}"


def _mouse_click(args: dict) -> str:
    x = args["x"]
    y = args["y"]
    button = args.get("button", "left")
    clicks = args.get("clicks", 1)
    prepare_for_gui_automation(0.1)
    try:
        import pyautogui
        pyautogui.click(x, y, clicks=clicks, button=button)
        return f"已在 ({x}, {y}) {button}键点击 {clicks} 次"
    except ImportError:
        return "鼠标控制需要安装 pyautogui: pip install pyautogui"


SCREENSHOT_PREFIX = "[SCREENSHOT_FILE]"


def _screen_capture(args: dict) -> str:
    save_path = args.get("save_path", "")
    if not save_path:
        export_dir = ensure_export_dir()
        save_path = str(export_dir / f"screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
    Path(save_path).parent.mkdir(parents=True, exist_ok=True)
    prepare_for_gui_automation(0.2)
    try:
        import pyautogui
        screenshot = pyautogui.screenshot()
        screenshot.save(save_path)
        w, h = screenshot.size
        return f"{SCREENSHOT_PREFIX}{w}x{h}|{save_path}"
    except ImportError:
        try:
            subprocess.run(
                ["powershell", "-Command",
                 f"Add-Type -AssemblyName System.Windows.Forms; "
                 f"[System.Windows.Forms.Screen]::PrimaryScreen | Out-Null; "
                 f"$bmp = New-Object System.Drawing.Bitmap([System.Windows.Forms.Screen]::PrimaryScreen.Bounds.Width, "
                 f"[System.Windows.Forms.Screen]::PrimaryScreen.Bounds.Height); "
                 f"$g = [System.Drawing.Graphics]::FromImage($bmp); "
                 f"$g.CopyFromScreen(0,0,0,0,$bmp.Size); "
                 f"$bmp.Save('{save_path}')"],
                shell=False, timeout=10,
            )
            try:
                from PIL import Image
                w, h = Image.open(save_path).size
            except Exception:
                w, h = 0, 0
            size_tag = f"{w}x{h}|" if w and h else ""
            return f"{SCREENSHOT_PREFIX}{size_tag}{save_path}"
        except Exception as exc:
            return f"截图失败: {exc}。请安装 pyautogui: pip install pyautogui"


def _image_analyze(args: dict) -> str:
    img_path = Path(args.get("path", ""))
    question = args.get("question", "请描述这张图片的内容。")
    if not img_path.exists():
        return f"图片文件不存在: {img_path}"
    if not img_path.is_file():
        return f"路径不是文件: {img_path}"
    suffix = img_path.suffix.lower()
    if suffix not in {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tiff"}:
        return f"不支持的图片格式: {suffix}"

    import base64
    try:
        raw = img_path.read_bytes()
        if len(raw) > 20 * 1024 * 1024:
            return "图片文件过大（>20MB），请压缩后重试。"
        b64 = base64.b64encode(raw).decode("ascii")
        mime = {
            ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".gif": "image/gif", ".bmp": "image/bmp", ".webp": "image/webp",
            ".tiff": "image/tiff",
        }.get(suffix, "image/png")
    except Exception as exc:
        return f"读取图片失败: {exc}"

    from core.agent_context import default_model
    from core.model_client import ModelClient, ModelClientError
    model = default_model()
    if not model:
        return f"未配置模型，无法分析图片。图片路径: {img_path}，大小: {len(raw)} 字节"

    messages = [
        {"role": "user", "content": [
            {"type": "text", "text": question},
            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
        ]}
    ]
    try:
        client = ModelClient()
        result = client.chat(messages, model, max_tokens=2048)
        return result
    except ModelClientError as exc:
        return f"图片分析失败: {exc}"


def _skill_install(args: dict) -> str:
    from agent_runtime.skill_installer import install_skill_from_url

    url = args["url"]
    result = install_skill_from_url(url)
    from core.settings_runtime import reload_skill_handlers
    reload_skill_handlers()
    return f"技能已安装: {result.get('package_name', '')}，路径: {result.get('install_path', '')}"


def _register_artifact(file_path: str, name: str, artifact_type: str) -> None:
    try:
        register_artifact(
            file_path,
            artifact_type,
            task_id=_TOOL_TASK_ID.get(),
            project_id=_TOOL_PROJECT_ID.get(),
            description=f"由工具生成：{name}",
        )
    except Exception:
        pass


def _format_size(path: Path) -> str:
    try:
        size = path.stat().st_size
    except OSError:
        return "?"
    if size < 1024:
        return f"{size}B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f}KB"
    return f"{size / 1024 / 1024:.1f}MB"


def _ui_locate(args: dict) -> str:
    from agent_runtime.ui_locator import locate_with_diagnostics

    target = args.get("target", "")
    window_title = resolve_window_title(args.get("window_title", ""))
    control_type = args.get("control_type", "")
    method = args.get("method", "auto")
    exact = bool(args.get("exact", False))

    refocus = _refocus_target({**args, "window_title": window_title})

    hit, err = locate_with_diagnostics(target, window_title, control_type, exact, method)
    if not hit:
        return err
    prefix = f"{refocus} " if refocus else ""
    return f"{prefix}已定位 ({hit.method}): {hit.detail} → 坐标 ({hit.x}, {hit.y})"


def _ui_click(args: dict) -> str:
    from agent_runtime.gui_hooks import prepare_for_gui_automation
    from agent_runtime.ui_locator import locate_with_diagnostics

    target = args.get("target", "")
    window_title = resolve_window_title(args.get("window_title", ""))
    control_type = args.get("control_type", "")
    method = args.get("method", "auto")
    exact = bool(args.get("exact", False))
    clicks = int(args.get("clicks", 1))

    prepare_for_gui_automation(0.1)
    refocus = _refocus_target({**args, "window_title": window_title})

    hit, err = locate_with_diagnostics(target, window_title, control_type, exact, method)
    if not hit:
        return err

    try:
        import pyautogui
        pyautogui.click(hit.x, hit.y, clicks=clicks)
        prefix = f"{refocus} " if refocus else ""
        return f"{prefix}已点击 ({hit.method}): {hit.detail} @ ({hit.x}, {hit.y})"
    except ImportError:
        return f"已定位 ({hit.x}, {hit.y}) 但缺少 pyautogui，无法点击"


def _library_list(args: dict) -> str:
    from core.agent_context import current_project
    from core.file_manager import list_library_files

    project = current_project()
    project_id = project["id"] if project else None
    rows = list_library_files(project_id)
    if not rows:
        return "资料库为空。请提示用户在「更多 → 资料库」中导入 PDF/Word 等文档。"
    lines = ["# 资料库文件（data/uploads，非 exports）", ""]
    for row in rows:
        name = row.get("file_name", "")
        ftype = row.get("file_type", "")
        path = row.get("file_path", "")
        summary = row.get("summary", "")
        lines.append(f"- {name} ({ftype})")
        lines.append(f"  路径: {path}")
        if summary:
            lines.append(f"  备注: {summary}")
    return "\n".join(lines)


def _library_search(args: dict) -> str:
    from core.agent_context import current_project
    from rag.retriever import search_chunks

    query = (args.get("query") or "").strip()
    if not query:
        return "错误：请提供 query 检索词。"
    limit = int(args.get("limit") or 6)
    project = current_project()
    project_id = project["id"] if project else None
    chunks = search_chunks(query, project_id=project_id, include_standards=True, limit=limit)
    if not chunks:
        return (
            f"资料库与标准库中未检索到与「{query}」高度相关的内容。"
            "请确认已导入对应资料；财务/分析类任务可直接让 Agent 生成表格，不必强行引用无关标准。"
        )
    weak = all(float(chunk.get("keyword_score") or 0) < 0.34 for chunk in chunks)
    lines = [f"# 资料库检索：{query}", ""]
    if weak:
        lines.append(
            "> 提示：未找到与检索词高度匹配的资料，以下结果相关度较低，请勿当作财务/模板依据。"
        )
        lines.append("")
    for idx, chunk in enumerate(chunks, 1):
        source = chunk.get("file_name") or chunk.get("standard_code") or "未知来源"
        page = chunk.get("page_number")
        page_hint = f" 页{page}" if page else ""
        content = (chunk.get("content") or "")[:800]
        lines.append(f"## [{idx}] {source}{page_hint}")
        lines.append(content)
        lines.append("")
    return "\n".join(lines).strip()


def _escape_sendkeys(text: str) -> str:
    special = {"+": "{+}", "^": "{^}", "%": "{%}", "~": "{~}", "(": "{(}", ")": "{)}", "{": "{{}", "}": "{}}"}
    return "".join(special.get(c, c) for c in text)


_HANDLERS: dict[str, Any] = {
    "shell_run": _shell_run,
    "file_read": _file_read,
    "file_write": _file_write,
    "file_list": _file_list,
    "file_delete": _file_delete,
    "software_launch": _software_launch,
    "find_application": _find_application,
    "open_url": _open_url,
    "web_search": _web_search,
    "web_fetch": _web_fetch,
    "office_word_create": _office_word_create,
    "office_excel_create": _office_excel_create,
    "office_ppt_create": _office_ppt_create,
    "code_create": _code_create,
    "keyboard_type": _keyboard_type,
    "hotkey_press": _hotkey_press,
    "mouse_click": _mouse_click,
    "window_focus": _window_focus,
    "list_apps": _list_apps,
    "ui_locate": _ui_locate,
    "ui_click": _ui_click,
    "screen_capture": _screen_capture,
    "skill_install": _skill_install,
    "image_analyze": _image_analyze,
    "library_list": _library_list,
    "library_search": _library_search,
}


_BUILTIN_HANDLERS = dict(_HANDLERS)


def load_installed_handlers() -> None:
    """Dynamically load handlers from installed skill packages into _HANDLERS.

    Each installed package's manifest_json may contain an ``entry`` field pointing
    to a Python module (dotted path) relative to the package install_path.  The
    module must expose a ``handle(args: dict) -> str`` function, or individual
    handler functions named after each tool (e.g. ``def get_weather(args)``).
    """
    import importlib.util
    import sys

    from core.settings_runtime import plugins_disabled
    from db.database import query_all

    _HANDLERS.clear()
    _HANDLERS.update(_BUILTIN_HANDLERS)

    if plugins_disabled():
        return

    rows = query_all(
        "SELECT install_path, manifest_json FROM installed_skill_packages WHERE enabled = 1"
    )

    for row in rows:
        install_path = row.get("install_path", "")
        manifest_raw = row.get("manifest_json", "")
        if not install_path or not manifest_raw:
            continue
        try:
            manifest = json.loads(manifest_raw)
        except Exception:
            continue

        tools = manifest.get("tools", [])
        entry = manifest.get("entry", "")
        if not tools or not entry:
            continue

        pkg_dir = Path(install_path)
        if not pkg_dir.is_dir():
            continue

        entry_file = pkg_dir / entry.replace(".", os.sep)
        if not entry_file.suffix:
            entry_file = entry_file.with_suffix(".py")
        if not entry_file.is_file():
            continue

        mod_name = f"_dna_skill_{manifest.get('name', 'unknown')}_{id(row)}"
        try:
            spec = importlib.util.spec_from_file_location(mod_name, str(entry_file))
            if spec is None or spec.loader is None:
                continue
            mod = importlib.util.module_from_spec(spec)
            sys.modules[mod_name] = mod
            spec.loader.exec_module(mod)
        except Exception:
            continue

        generic_handle = getattr(mod, "handle", None) or getattr(mod, "run", None)

        for tool_def in tools:
            t_name = tool_def.get("name", "")
            if not t_name or t_name in _HANDLERS:
                continue
            specific = getattr(mod, t_name, None)
            if callable(specific):
                _HANDLERS[t_name] = specific
            elif callable(generic_handle):
                def _make_handler(fn, tn):
                    return lambda args, _fn=fn, _tn=tn: _fn({**args, "_tool": _tn})
                _HANDLERS[t_name] = _make_handler(generic_handle, t_name)

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any, Generator

from core.app_identity import APP_NAME
from agent_runtime.tool_definitions import TOOLS, TOOL_RISK_LEVELS, get_active_tools
from agent_runtime.tool_executor import execute_tool, load_installed_handlers, SCREENSHOT_PREFIX
from core.task_tracker import complete_task, log_tool_step, start_task
from core.agent_context import current_project, default_model
from core.model_client import ModelClient, ModelClientError
from rag.citation_builder import build_citations
from rag.retriever import search_chunks


_SYSTEM_PROMPT_TEMPLATE = """你是 __APP_NAME__ —— 一个运行在用户本地 Windows 电脑上的智能工作伙伴。

## 核心理念

你是一个有独立思考能力的智能体。面对任何任务，你的工作方式是：
1. **理解意图** —— 用户到底想做什么？
2. **制定方案** —— 基于你对软件和操作系统的了解，规划出最合理的操作步骤
3. **逐步执行** —— 调用工具执行你规划的每一步
4. **观察反馈** —— 如果涉及 GUI 操作，通过截屏确认当前状态，再决定下一步
5. **诚实汇报** —— 告诉用户你做了什么、结果如何

**你不是在执行预设脚本，而是在用你的智慧解决问题。** 每个软件的界面不同、操作方式不同，你需要自己思考怎么操作，而不是套用固定模板。

## 什么时候用工具，什么时候不用

- **问答、分析、翻译、写文案** → 直接回答，不需要工具
- **生成文档（Word/PPT/Excel）** → 你负责构思全部内容，工具只负责存成文件
- **操作电脑** → 调用工具

## 性格与风格

温暖、专业、有亲和力。回答要详尽完整，善用标题和列表组织信息。

## 文档生成

你生成的内容质量代表你的水平：

**PPT**：至少 8-12 页，每页 3-5 个完整的要点句（15-40字），像行业专家做报告。
  - ❌ "自主性"、"感知能力" ← 只是关键词
  - ✅ "自主性 —— 能独立分析任务目标、制定执行计划，无需人类逐步指令"

**Word**：每个章节至少 2-3 段正文（100字以上），有观点有论据。

文档生成只需要一次工具调用，内容深度是关键。

## 打开本地软件（重要）

用户要求「打开某桌面软件」或「在某某里播放 / 搜索」时：

1. **主动检索**：可用 `find_application` 在本机搜索（注册表、开始菜单、安装目录），再根据返回的路径/名称调用 `software_launch`
2. **多名称尝试**：中文名、英文名、简称、全称都可作为检索词；一次失败应换写法重试，而不是立刻改用浏览器
3. **必须优先** `software_launch` 启动/聚焦**本地客户端**，再用 `ui_click` / `keyboard_type` 完成操作
4. **禁止**用 `open_url` 打开网页版、搜索引擎或官网来替代本地软件，除非：
   - 用户**明确**要求网页版；或
   - 已多次检索/启动仍失败且用户同意改用网页
5. 「播放歌曲 / 看视频」→ 先打开对应**桌面 App**，再在 App 内搜索播放，不要默认开浏览器

## GUI 操作：WorkBuddy 方法（本地脚本驱动）

你负责规划步骤，**本地工具负责定位和操作**。不要靠 vision 看截图猜坐标，不要写死「某软件 = 某快捷键」。

### 标准流程

1. **list_apps** — 确认目标窗口标题
2. **software_launch** + **window_focus** — 启动并激活目标应用（窗口已开则只聚焦，勿重复启动）
3. **ui_click / ui_locate** — **主路径**：本地 UIA 或 OCR 定位，**必须带 window_title**
4. **keyboard_type / hotkey_press** — 输入与确认，**必须带 window_title**
5. 同一轮可 **批量** 多个 tool_calls（如 ui_click + keyboard_type + hotkey_press），减少往返
6. **screen_capture** — 仅 ui_* 失败后的诊断，或用户要求留档；**默认不注入 vision**
7. 仍无法定位时 → **image_analyze** 分析已保存截图，或 screen_capture(for_vision=true)

### 窗口焦点

- 用户可能在 __APP_NAME__ 内点「执行」确认，焦点会短暂回到 Agent；工具会自动重新聚焦目标窗口
- list_apps 已看到目标窗口时，**禁止**再 software_launch，只需 window_focus 或直接 ui_*（带 window_title）
- 同一任务连续操作时，始终复用同一 window_title 关键词

### 系统弹窗

- 路径错误、找不到文件等 Windows 报错框会自动点「确定」关闭，工具结果里会附带 `[系统弹窗已自动关闭: …]`
- 若仍被弹窗阻塞，用 list_apps 查看顶层窗口，必要时 screen_capture 诊断
- **用户账户控制 (UAC)** 不会自动关闭，需用户手动确认

### 禁止

- 默认 screen_capture → vision → mouse_click(x,y)
- 无依据硬编码 Ctrl+F 等快捷键
- shell_run Start-Sleep

### 验证

用 ui_locate 或工具返回文字确认；不要为了验证专门开 vision 轮。

## 执行效率

1. 优先 ui_click 定位后批量操作
2. 调用工具时不写长文，直接 tool_calls
3. GUI 任务不依赖 vision 模型
4. 用户通过聊天内按钮确认（执行/拒绝/以下都执行），不要反复用文字询问是否继续

## 工具说明

- list_apps：列出可见窗口
- ui_click / ui_locate：GUI 主路径（本地 OCR/UIA）
- window_focus / software_launch / find_application：窗口、启动与本机应用检索
- keyboard_type / hotkey_press：键盘输入
- screen_capture：调试/失败诊断（for_vision=true 时才给模型看图）
- mouse_click：仅 ui_locate 已给出坐标时的兜底
- image_analyze：分析已有图片文件

## Skill（SKILL.md）

用户可在「技能商店」安装 Skill。已启用 Skill 的 SKILL.md 说明会注入本提示词末尾；匹配任务时优先遵循 Skill 步骤，用内置工具执行。

## 重要规则

- 操作系统是 Windows，Shell 用 PowerShell。
- 不要限制回答长度。
- 工具失败最多重试 1 次。
- **GUI 操作后诚实汇报**：你无法 100% 确定 GUI 操作是否成功，应该说"我已执行操作，请确认效果"而不是"已完成"。
- 如果用户附带了图片，可以直接分析。"""

SYSTEM_PROMPT = _SYSTEM_PROMPT_TEMPLATE.replace("__APP_NAME__", APP_NAME)


PLAN_MODE_SUFFIX = """

当前是「想一想」模式。用户希望你：
1. 先分析需求，列出你打算执行的步骤（不实际执行）
2. 等用户确认后再开始执行
3. 如果用户直接说"执行"或"开始"，则直接执行"""

PLAN_DRAFT_SUFFIX = """

**重要：当前仅输出计划，禁止调用任何工具。**
请用 Markdown 输出：
- 第一行：`# 计划：{简短标题}`
- 随后 numbered list，每步一句话说明做什么、用什么方式。"""

ASK_MODE_SUFFIX = """

**当前是「问一问」模式：仅文字问答与分析，禁止调用任何工具。**"""

TOOL_ROUND_MAX_TOKENS = 2048
_TOOL_MSG_LIMIT = 600
_SAFETY_MAX_ROUNDS = 500


class Agent:
    def run(
        self,
        user_text: str,
        model: dict | None = None,
        project: dict | None = None,
        expert_prompt: str = "",
        mode: str = "craft",
        full_access: bool = False,
        max_rounds: int = 0,
        history: list[dict] | None = None,
        attachments: list[str] | None = None,
        request_permission: Callable[[dict], bool] | None = None,
        *,
        local_search_only: bool = False,
        plan_execute: bool = False,
        plan_context: str = "",
        conversation_id: int | None = None,
    ) -> Generator[dict[str, Any], None, None]:
        """LLM-driven agent loop.

        Yields: tool_call, thinking, token, plan_ready, task_started, final_reply, error
        """
        project = project or current_project()

        if local_search_only:
            yield from self._run_local_search(user_text, project)
            return

        if mode == "ask":
            model = model or default_model()
            if not model:
                yield from self._run_local_search(user_text, project)
                return
            yield from self._run_ask(user_text, model, project, expert_prompt, history, attachments)
            return

        if mode == "plan" and not plan_execute:
            model = model or default_model()
            if not model:
                yield {"type": "error", "content": "想一想模式需要配置 AI 模型。"}
                return
            yield from self._run_plan_draft(user_text, model, project, expert_prompt, history, attachments)
            return

        model = model or default_model()
        if not model:
            action = self._try_local_action(user_text)
            if action:
                yield action
            yield {"type": "final_reply", "content": self._local_answer(user_text, project)}
            return

        task_id = start_task(
            conversation_id=conversation_id,
            goal=user_text,
            task_type="plan_execute" if plan_execute else "craft",
            plan_json=plan_context or "",
        )
        yield {"type": "task_started", "task_id": task_id}

        try:
            yield from self._run_tool_loop(
                user_text=user_text,
                model=model,
                project=project,
                expert_prompt=expert_prompt,
                mode="craft" if plan_execute else mode,
                full_access=full_access,
                max_rounds=max_rounds,
                history=history,
                attachments=attachments,
                request_permission=request_permission,
                plan_context=plan_context,
                task_id=task_id,
            )
            complete_task(task_id, status="completed")
        except Exception:
            complete_task(task_id, status="failed")
            raise

    def _run_local_search(
        self, user_text: str, project: dict | None,
    ) -> Generator[dict[str, Any], None, None]:
        action = self._try_local_action(user_text)
        if action:
            yield action
        text = self._local_answer(user_text, project)
        for i in range(0, len(text), 48):
            yield {"type": "token", "content": text[i:i + 48]}
        yield {"type": "final_reply", "content": text}

    def _run_ask(
        self,
        user_text: str,
        model: dict,
        project: dict | None,
        expert_prompt: str,
        history: list[dict] | None,
        attachments: list[str] | None,
    ) -> Generator[dict[str, Any], None, None]:
        system = self._build_system_prompt(expert_prompt, "ask", project)
        messages = self._build_messages(system, user_text, project, history, attachments, model)
        yield from self._stream_chat_events(messages, model)

    def _run_plan_draft(
        self,
        user_text: str,
        model: dict,
        project: dict | None,
        expert_prompt: str,
        history: list[dict] | None,
        attachments: list[str] | None,
    ) -> Generator[dict[str, Any], None, None]:
        system = self._build_system_prompt(expert_prompt, "plan", project) + PLAN_DRAFT_SUFFIX
        messages = self._build_messages(system, user_text, project, history, attachments, model)
        full = ""
        for event in self._stream_chat_events(messages, model):
            if event.get("type") == "token":
                yield event
            elif event.get("type") == "final_reply":
                full = event.get("content", "")
        yield {"type": "plan_ready", "content": full}
        yield {"type": "final_reply", "content": full}

    def _stream_chat_events(
        self, messages: list[dict], model: dict,
    ) -> Generator[dict[str, Any], None, None]:
        client = ModelClient()
        parts: list[str] = []
        try:
            for chunk in client.stream_chat(messages, model):
                parts.append(chunk)
                yield {"type": "token", "content": chunk}
            yield {"type": "final_reply", "content": "".join(parts)}
        except ModelClientError as exc:
            yield {"type": "error", "content": str(exc)}

    def _build_messages(
        self,
        system: str,
        user_text: str,
        project: dict | None,
        history: list[dict] | None,
        attachments: list[str] | None,
        model: dict,
    ) -> list[dict]:
        user_content = self._build_user_content(user_text, project)
        messages: list[dict] = [{"role": "system", "content": system}]
        if history:
            for h in history[-20:]:
                role = h.get("role", "")
                content = h.get("content", "")
                if role in ("user", "assistant") and content:
                    if role == "assistant" and len(content) > 2000:
                        content = content[:2000] + "…"
                    messages.append({"role": role, "content": content})
        attachment_list = attachments or []
        if attachment_list:
            model_name = model.get("model_name", "")
            if self._vision_supported.get(model_name) is not False:
                image_parts = self._encode_image_attachments(attachment_list)
                if image_parts:
                    content_array: list[dict] = [{"type": "text", "text": user_content}]
                    content_array.extend(image_parts)
                    messages.append({"role": "user", "content": content_array})
                else:
                    messages.append({"role": "user", "content": user_content})
            else:
                desc = "\n".join(f"[图片: {p}]" for p in attachment_list)
                messages.append({"role": "user", "content": user_content + "\n" + desc})
        else:
            messages.append({"role": "user", "content": user_content})
        return messages

    def _run_tool_loop(
        self,
        *,
        user_text: str,
        model: dict,
        project: dict | None,
        expert_prompt: str,
        mode: str,
        full_access: bool,
        max_rounds: int,
        history: list[dict] | None,
        attachments: list[str] | None,
        request_permission: Callable[[dict], bool] | None,
        plan_context: str,
        task_id: int,
    ) -> Generator[dict[str, Any], None, None]:
        system = self._build_system_prompt(expert_prompt, mode, project)
        if plan_context:
            system += f"\n\n用户已确认以下计划，请按步骤执行：\n{plan_context}"
        user_content = self._build_user_content(user_text, project)
        messages: list[dict] = [{"role": "system", "content": system}]
        if history:
            for h in history[-20:]:
                role = h.get("role", "")
                content = h.get("content", "")
                if role in ("user", "assistant") and content:
                    if role == "assistant" and len(content) > 2000:
                        content = content[:2000] + "…"
                    messages.append({"role": role, "content": content})
        attachment_list = attachments or []
        if attachment_list:
            model_name = model.get("model_name", "")
            if self._vision_supported.get(model_name) is not False:
                image_parts = self._encode_image_attachments(attachment_list)
                if image_parts:
                    content_array: list[dict] = [{"type": "text", "text": user_content}]
                    content_array.extend(image_parts)
                    messages.append({"role": "user", "content": content_array})
                else:
                    messages.append({"role": "user", "content": user_content})
            else:
                desc_parts = [f"[用户附带了图片: {fpath}]" for fpath in attachment_list]
                messages.append({"role": "user", "content": user_content + "\n" + "\n".join(desc_parts)})
        else:
            messages.append({"role": "user", "content": user_content})

        client = ModelClient()
        load_installed_handlers()
        active_tools = get_active_tools()
        from agent_runtime.gui_session import clear_active_window
        clear_active_window()
        from agent_runtime.permissions import requires_confirmation

        step_index = 0
        round_idx = 0
        round_limit = max_rounds if max_rounds > 0 else _SAFETY_MAX_ROUNDS
        while True:
            round_idx += 1
            if round_idx > round_limit:
                yield {"type": "error", "content": f"已达到安全轮数上限 ({round_limit})，任务已停止。"}
                return

            self._compact_messages_for_llm(messages)
            try:
                response = client.chat_with_tools(
                    messages, model, tools=active_tools, max_tokens=TOOL_ROUND_MAX_TOKENS,
                )
            except ModelClientError as exc:
                if "400" in str(exc) and self._strip_images_from_messages(messages):
                    model_name = model.get("model_name", "")
                    self._vision_supported[model_name] = False
                    try:
                        response = client.chat_with_tools(messages, model, tools=active_tools)
                    except ModelClientError as exc2:
                        yield {"type": "error", "content": str(exc2)}
                        return
                else:
                    yield {"type": "error", "content": str(exc)}
                    return

            if response.tool_calls:
                messages.append(response.raw_message)
                if response.content and len(response.content.strip()) > 20:
                    yield {"type": "thinking", "content": response.content}

                vision_screenshot_paths: list[str] = []
                vision_screenshot_sizes: dict[str, str] = {}

                for tc in response.tool_calls:
                    if requires_confirmation(tc.name, full_access):
                        approved = True
                        if request_permission:
                            approved = request_permission({
                                "name": tc.name,
                                "args": tc.arguments,
                                "risk": TOOL_RISK_LEVELS.get(tc.name, "medium"),
                            })
                        if not approved:
                            result = (
                                f"用户未批准执行 {tc.name}。"
                                "请在完全访问模式下运行，或改用低风险工具。"
                            )
                            step_index += 1
                            log_tool_step(task_id, step_index, tc.name, tc.arguments, result, status="failed")
                            yield {"type": "tool_call", "name": tc.name, "args": tc.arguments, "result": result}
                            messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})
                            continue

                    result = execute_tool(tc.name, tc.arguments)
                    step_index += 1
                    log_tool_step(task_id, step_index, tc.name, tc.arguments, result)

                    display_result = result
                    if result.startswith(SCREENSHOT_PREFIX):
                        payload = result[len(SCREENSHOT_PREFIX):]
                        size_hint = ""
                        if "|" in payload:
                            maybe_size, img_path = payload.split("|", 1)
                            if "x" in maybe_size:
                                size_hint = maybe_size
                            else:
                                img_path = payload
                        else:
                            img_path = payload
                        display_result = f"截图已保存: {img_path}" + (f"（{size_hint}）" if size_hint else "")
                        if tc.arguments.get("for_vision"):
                            vision_screenshot_paths.append(img_path)
                            if size_hint:
                                vision_screenshot_sizes[img_path] = size_hint

                    yield {"type": "tool_call", "name": tc.name, "args": tc.arguments, "result": display_result}
                    messages.append({"role": "tool", "tool_call_id": tc.id, "content": display_result})

                if vision_screenshot_paths:
                    model_name = model.get("model_name", "")
                    if self._vision_supported.get(model_name) is False:
                        for spath in vision_screenshot_paths:
                            messages.append({"role": "user", "content": self._screenshot_fallback(spath)})
                    else:
                        vision_parts = self._encode_image_attachments(vision_screenshot_paths)
                        if vision_parts:
                            size_lines = "\n".join(
                                f"- {p}: {vision_screenshot_sizes.get(p, '未知分辨率')}"
                                for p in vision_screenshot_paths
                            )
                            vision_content: list[dict] = [
                                {"type": "text", "text": (
                                    "【诊断截图】ui_click/ui_locate 未能定位，已注入截图。\n"
                                    f"分辨率：{size_lines}\n请换 target 后 ui_click。"
                                )},
                            ]
                            vision_content.extend(vision_parts)
                            messages.append({"role": "user", "content": vision_content})
            else:
                content = response.content or ""
                if content:
                    for i in range(0, len(content), 32):
                        yield {"type": "token", "content": content[i:i + 32]}
                yield {"type": "final_reply", "content": content}
                return

    def answer(
        self,
        user_text: str,
        model: dict | None = None,
        project: dict | None = None,
        expert_prompt: str = "",
        craft_mode: bool = False,
    ) -> str:
        """Legacy simple Q&A method (no tools). Kept for backward compatibility."""
        project = project or current_project()
        model = model or default_model()
        chunks = search_chunks(user_text, project_id=project["id"] if project else None, include_standards=True)
        context = "\n\n".join([f"来源{idx}: {c['content']}" for idx, c in enumerate(chunks, 1)])

        if not model:
            return self._local_answer(user_text, project)

        system = SYSTEM_PROMPT
        if expert_prompt:
            system = f"{expert_prompt}\n\n{system}"

        project_name = project.get("project_name") if project else "未选择"
        user_content = f"用户问题：{user_text}"
        if context:
            user_content = f"当前项目：{project_name}\n\n参考资料：\n{context}\n\n{user_content}"
        else:
            user_content = f"当前项目：{project_name}\n\n{user_content}"

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user_content},
        ]
        try:
            reply = ModelClient().chat(messages, model)
        except ModelClientError as exc:
            reply = f"{exc}"
        if chunks:
            reply += "\n\n来源：\n" + build_citations(chunks)
        return reply

    @staticmethod
    def _compact_messages_for_llm(messages: list[dict]) -> None:
        """Trim context so each LLM round stays fast."""
        stale_vision = 0
        for msg in messages:
            role = msg.get("role")
            content = msg.get("content")

            if role == "tool":
                text = content if isinstance(content, str) else str(content)
                if len(text) > _TOOL_MSG_LIMIT:
                    msg["content"] = text[:_TOOL_MSG_LIMIT] + "…(已截断)"

            if role == "user" and isinstance(content, list):
                has_image = any(p.get("type") == "image_url" for p in content)
                if has_image:
                    stale_vision += 1
                    if stale_vision > 1:
                        msg["content"] = "（此前的截图已过期，请基于最新截图判断）"

            if role == "assistant" and isinstance(content, str) and len(content) > 1500:
                msg["content"] = content[:1500] + "…"

    def _build_system_prompt(self, expert_prompt: str, mode: str, project: dict | None) -> str:
        from agent_runtime.skill_prompt_loader import build_skills_system_suffix
        from core.settings_runtime import build_agent_settings_suffix

        system = SYSTEM_PROMPT
        if expert_prompt:
            system = f"{expert_prompt}\n\n{system}"
        skills_suffix = build_skills_system_suffix()
        if skills_suffix:
            system += skills_suffix
        system += build_agent_settings_suffix()
        if mode == "ask":
            system += ASK_MODE_SUFFIX
        elif mode == "plan":
            system += PLAN_MODE_SUFFIX
        project_name = project.get("project_name") if project else "未选择"
        system += f"\n\n当前项目：{project_name}"
        desc = (project.get("project_description") or "").strip() if project else ""
        if desc:
            system += f"\n项目背景与指令：{desc}"
        return system

    def _build_user_content(self, user_text: str, project: dict | None) -> str:
        chunks = search_chunks(
            user_text,
            project_id=project["id"] if project else None,
            include_standards=True,
        )
        if chunks:
            context = "\n".join([f"- {c['content'][:300]}" for c in chunks[:3]])
            return f"参考资料（如果与问题相关则参考，不相关则忽略）：\n{context}\n\n用户指令：{user_text}"
        return user_text

    _vision_supported: dict[str, bool] = {}

    @staticmethod
    def _strip_images_from_messages(messages: list[dict]) -> bool:
        """Remove image_url parts from all messages in-place. Returns True if any were removed."""
        changed = False
        for msg in messages:
            content = msg.get("content")
            if isinstance(content, list):
                text_parts = [p.get("text", "") for p in content if p.get("type") == "text"]
                had_images = any(p.get("type") == "image_url" for p in content)
                if had_images:
                    msg["content"] = "\n".join(text_parts) or "(图片内容已移除，当前模型不支持图像识别)"
                    changed = True
        return changed

    def _describe_screenshot(self, img_path: str, model: dict, client: ModelClient) -> str:
        """Analyze screenshot via vision API; fall back to text if unsupported."""
        model_name = model.get("model_name", "")

        if self._vision_supported.get(model_name) is False:
            return self._screenshot_fallback(img_path)

        parts = self._encode_image_attachments([img_path])
        if not parts:
            return self._screenshot_fallback(img_path)

        try:
            vision_msgs = [{"role": "user", "content": [
                {"type": "text", "text": (
                    "请详细描述这张屏幕截图的内容。重点关注：\n"
                    "1. 当前打开的软件名称和窗口状态\n"
                    "2. 界面上所有可见的按钮、输入框、搜索栏的位置（估算像素坐标 x,y）\n"
                    "3. 是否有弹窗、广告或遮挡\n"
                    "4. 当前界面所处的页面/标签\n"
                    "用中文回答，尽量精确。"
                )},
                *parts,
            ]}]
            description = client.chat(vision_msgs, model, max_tokens=1024)
            self._vision_supported[model_name] = True
            return f"【屏幕截图分析结果】\n{description}\n\n请根据以上分析决定下一步操作。"
        except Exception:
            self._vision_supported[model_name] = False
            return self._screenshot_fallback(img_path)

    @staticmethod
    def _screenshot_fallback(img_path: str) -> str:
        """When vision is unavailable, give the LLM a text-based hint."""
        try:
            from PIL import Image
            im = Image.open(img_path)
            w, h = im.size
            size_info = f"（分辨率 {w}x{h}）"
        except Exception:
            size_info = ""
        return (
            f"截图已保存到 {img_path}{size_info}。\n"
            "当前模型不支持图像识别，无法直接看到截图内容。\n"
            "请继续用 ui_click/ui_locate 换不同 target 词重试，或请用户手动聚焦目标控件后再 keyboard_type。"
        )

    @staticmethod
    def _encode_image_attachments(attachments: list[str], max_long_edge: int = 1280) -> list[dict]:
        """Convert image files to compressed base64 JPEG for vision API."""
        import base64
        import io
        from pathlib import Path

        IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tiff"}
        parts: list[dict] = []
        for fpath in attachments:
            p = Path(fpath)
            if not p.is_file():
                continue
            if p.suffix.lower() not in IMAGE_EXTS:
                continue
            try:
                from PIL import Image
                img = Image.open(p)
                if img.mode in ("RGBA", "P", "LA"):
                    img = img.convert("RGB")

                w, h = img.size
                if max(w, h) > max_long_edge:
                    scale = max_long_edge / max(w, h)
                    img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=75)
                b64 = base64.b64encode(buf.getvalue()).decode("ascii")
                parts.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                })
            except ImportError:
                raw = p.read_bytes()
                if len(raw) > 10 * 1024 * 1024:
                    continue
                b64 = base64.b64encode(raw).decode("ascii")
                mime = "image/png" if p.suffix.lower() == ".png" else "image/jpeg"
                parts.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime};base64,{b64}"},
                })
            except Exception:
                continue
        return parts

    def _try_local_action(self, user_text: str) -> dict | None:
        """When no model is configured, try to handle simple action commands locally."""
        import re
        text = user_text.strip()

        launch_match = re.match(
            r"^(?:打开|启动|运行|开|帮我打开|帮我启动|请打开|请启动|open|launch|start)\s*(?:我的|我电脑上的|我电脑的|电脑上的)?\s*(.+?)$",
            text, re.IGNORECASE,
        )
        if launch_match:
            name = launch_match.group(1).strip().rstrip("。.！!？?")
            if name:
                result = execute_tool("software_launch", {"name": name})
                return {
                    "type": "tool_call",
                    "name": "software_launch",
                    "args": {"name": name},
                    "result": result,
                }

        url_match = re.match(
            r"^(?:打开|访问|帮我打开|请打开|open)\s*(https?://\S+)$",
            text, re.IGNORECASE,
        )
        if url_match:
            url = url_match.group(1)
            result = execute_tool("open_url", {"url": url})
            return {
                "type": "tool_call",
                "name": "open_url",
                "args": {"url": url},
                "result": result,
            }

        return None

    def _local_answer(self, user_text: str, project: dict | None = None) -> str:
        text = user_text.strip()
        launch_keywords = ["打开", "启动", "运行", "open", "launch", "start"]
        is_action = any(text.startswith(kw) for kw in launch_keywords)

        chunks = search_chunks(
            user_text,
            project_id=project["id"] if project else None,
            include_standards=True,
        )

        if is_action:
            return "已尝试执行操作。如需更智能的对话和复杂任务处理，请在 **设置 → 模型** 中配置 API Key。"

        if not chunks:
            return (
                "当前使用本地检索模式，知识库中暂无相关内容。\n\n"
                "**提示：** 在 **设置 → 模型** 中配置 AI 模型后，可以获得：\n"
                "- 智能对话与多轮推理\n"
                "- 工具调用（打开软件、生成文档、执行命令等）\n"
                "- 文档生成与代码编写\n\n"
                "推荐配置 DeepSeek 或其他 OpenAI 兼容模型。"
            )

        bullet = "\n".join([f"- {c['content'][:220].replace(chr(10), ' ')}..." for c in chunks[:4]])
        return f"以下是本地知识库检索结果：\n\n{bullet}"

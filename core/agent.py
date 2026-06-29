from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any, Generator

from core.app_identity import APP_NAME
from agent_runtime.tool_definitions import TOOLS, TOOL_RISK_LEVELS, get_active_tools, get_tool_risk_level
from agent_runtime.tool_executor import execute_tool, load_installed_handlers, SCREENSHOT_PREFIX, tool_context
from core.task_tracker import complete_task, log_tool_step, start_task
from core.agent_context import current_project, default_model
from core.file_references import build_referenced_files_context
from core.model_client import ModelClient, ModelClientError
from rag.citation_builder import build_citations
from rag.retriever import search_chunks


_SYSTEM_PROMPT_TEMPLATE = """你是 __APP_NAME__ —— 面向工程技术人员的本地 Agent 工作台。

## 核心理念

你的工作重点是 **文件级自动化**：查资料、写文档、生成可交付文件，而不是操控桌面 GUI。

推荐工作流：
1. **理解意图** —— 用户要交付什么（Word/PPT/Excel/分析报告）？
2. **查资料** —— 用 `library_search` / @ 引用 / 消息内参考资料
3. **生成内容** —— 你负责专业、完整的正文；工具负责落盘
4. **交付** —— 用 `office_word_create` / `office_ppt_create` / `office_excel_create` 输出到 exports
5. **诚实汇报** —— 说明生成了什么文件、依据了哪些资料

## 什么时候用工具

- **问答、分析、翻译** → 直接回答（可结合资料库检索结果）
- **写方案 / 报告 / PPT / 表格** → `library_search` 取依据 → 一次 `office_*` 生成文件
- **读用户资料** → `library_list` / `library_search` / `file_read`（路径来自资料库列表）
- **用户明确说「打开某软件」** → 可用 `find_application` + `software_launch` 启动，**默认不要在软件内自动点击/输入**

## 文档生成（核心能力）

**PPT**：8–12 页，每页 3–5 条完整要点句（15–40 字），像行业专家汇报。
**Word**：每节 2–3 段正文（100 字以上），有论据、可引用资料库。
**Excel**：表头清晰，行数据有意义，可来自资料清单类任务。

生成文档时：**先构思完整内容，再一次 office 工具调用写入**，不要空壳占位。

## 资料库与产物（必守）

- **资料库** = `data/uploads/`（用户在「更多 → 资料库」导入，已建索引）
- **exports** = 你**生成**的文件，不是资料库
- 用户 @ 引用的内容优先；其次消息中的「参考资料」向量检索片段
- 问标准/项目资料时：`library_search` → 必要时 `file_read`；**禁止**把 exports 当资料库去列目录

## 工具速查（优先使用）

- `library_search` / `library_list`：资料库检索与列表
- `office_word_create` / `office_ppt_create` / `office_excel_create`：生成 Office 文件
- `file_read` / `file_write` / `file_list`：读写工作区文件
- `find_application` / `software_launch`：仅「打开程序」类请求
- `code_create`：生成脚本到 exports

## Skill（SKILL.md）

已安装 Skill 的说明会注入末尾；匹配任务时优先遵循 Skill，用上述文件级工具执行。

## 重要规则

- Windows + PowerShell 环境
- 工具失败最多重试 1 次
- **不要**默认用浏览器代替本地软件完成业务交付；应生成文档或基于资料库回答
- 用户附图可用 `image_analyze` 分析"""

_GUI_EXPERIMENTAL_PROMPT = """

## GUI 自动化（实验性，需用户在设置中开启）

以下能力不稳定，仅当用户**明确要求**在软件内点击/输入时使用：
- `list_apps` / `window_focus` / `ui_locate` / `ui_click` / `keyboard_type` / `hotkey_press`
- `screen_capture` 仅作 ui_* 失败诊断

流程：启动并聚焦窗口 → UIA/OCR 定位（带 window_title）→ 操作 → `ui_locate` 验证。
**必须诚实汇报**：GUI 操作无法 100% 确认成功，勿声称「已完成」。
禁止：默认截图 + vision 猜坐标、无依据硬编码快捷键。"""

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
        referenced_files: list[str] | None = None,
        request_permission: Callable[[dict], bool] | None = None,
        *,
        local_search_only: bool = False,
        plan_execute: bool = False,
        plan_context: str = "",
        conversation_id: int | None = None,
        active_skill_package: str = "",
        guidance_poll: Callable[[], list[str]] | None = None,
    ) -> Generator[dict[str, Any], None, None]:
        """LLM-driven agent loop.

        Yields: tool_call, thinking, token, plan_ready, task_started, guidance, final_reply, error
        """
        project = project or current_project()

        if local_search_only:
            yield from self._run_local_search(user_text, project, referenced_files=referenced_files)
            return

        if mode == "ask":
            model = model or default_model()
            if not model:
                yield from self._run_local_search(user_text, project, referenced_files=referenced_files)
                return
            yield from self._run_ask(
                user_text, model, project, expert_prompt, history, attachments,
                referenced_files=referenced_files,
                active_skill_package=active_skill_package,
            )
            return

        if mode == "plan" and not plan_execute:
            model = model or default_model()
            if not model:
                yield {"type": "error", "content": "想一想模式需要配置 AI 模型。"}
                return
            yield from self._run_plan_draft(
                user_text, model, project, expert_prompt, history, attachments,
                active_skill_package=active_skill_package,
            )
            return

        model = model or default_model()
        if not model:
            action = self._try_local_action(user_text)
            if action:
                yield action
            yield {"type": "final_reply", "content": self._local_answer(user_text, project)}
            return

        from agent_runtime.executor import Executor
        from agent_runtime.planner import plan_from_confirmed_markdown, plan_with_llm

        if plan_execute and plan_context.strip():
            task_plan = plan_from_confirmed_markdown(user_text, plan_context, project)
        else:
            task_plan = plan_with_llm(user_text, model, project)

        task_id = start_task(
            conversation_id=conversation_id,
            goal=user_text,
            task_type=task_plan.task_type,
            plan_json=task_plan.to_json(),
        )
        yield {"type": "task_started", "task_id": task_id}

        executor = Executor()
        try:
            yield from executor.run_plan_streaming(
                task_plan,
                task_id=task_id,
                model=model,
                project=project,
                conversation_id=conversation_id,
                expert_prompt=expert_prompt,
                full_access=full_access,
                max_rounds=max_rounds,
                history=history,
                attachments=attachments,
                referenced_files=referenced_files,
                request_permission=request_permission,
                active_skill_package=active_skill_package,
                guidance_poll=guidance_poll,
            )
            complete_task(task_id, status="completed")
        except Exception:
            complete_task(task_id, status="failed")
            raise

    def _run_local_search(
        self, user_text: str, project: dict | None,
        referenced_files: list[str] | None = None,
    ) -> Generator[dict[str, Any], None, None]:
        action = self._try_local_action(user_text)
        if action:
            yield action
        text = self._local_answer(user_text, project, referenced_files=referenced_files)
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
        referenced_files: list[str] | None = None,
        *,
        active_skill_package: str = "",
    ) -> Generator[dict[str, Any], None, None]:
        system = self._build_system_prompt(
            expert_prompt, "ask", project, active_skill_package=active_skill_package,
        )
        messages = self._build_messages(
            system, user_text, project, history, attachments, model,
            referenced_files=referenced_files,
        )
        yield from self._stream_chat_events(messages, model)

    def _run_plan_draft(
        self,
        user_text: str,
        model: dict,
        project: dict | None,
        expert_prompt: str,
        history: list[dict] | None,
        attachments: list[str] | None,
        *,
        active_skill_package: str = "",
    ) -> Generator[dict[str, Any], None, None]:
        system = self._build_system_prompt(
            expert_prompt, "plan", project, active_skill_package=active_skill_package,
        ) + PLAN_DRAFT_SUFFIX
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
        referenced_files: list[str] | None = None,
    ) -> list[dict]:
        user_content = self._build_user_content(user_text, project, referenced_files)
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
        active_skill_package: str = "",
        referenced_files: list[str] | None = None,
        guidance_poll: Callable[[], list[str]] | None = None,
    ) -> Generator[dict[str, Any], None, None]:
        system = self._build_system_prompt(
            expert_prompt, mode, project, active_skill_package=active_skill_package,
        )
        if plan_context:
            system += f"\n\n用户已确认以下计划，请按步骤执行：\n{plan_context}"
        user_content = self._build_user_content(user_text, project, referenced_files)
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

            if guidance_poll:
                for note in guidance_poll():
                    hint = (
                        "【用户实时引导 — 不要中断或重头开始当前任务，"
                        "从下一步起按以下内容调整方向与输出】\n"
                        + note
                    )
                    messages.append({"role": "user", "content": hint})
                    yield {"type": "guidance", "content": note}

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
                                "risk": get_tool_risk_level(tc.name),
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

                    project_id = project["id"] if project and project.get("id") else None
                    with tool_context(task_id=task_id, project_id=project_id):
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

    def _build_system_prompt(
        self,
        expert_prompt: str,
        mode: str,
        project: dict | None,
        *,
        active_skill_package: str = "",
    ) -> str:
        from agent_runtime.skill_prompt_loader import build_skills_system_suffix
        from core.settings_runtime import build_agent_settings_suffix, gui_automation_enabled

        system = SYSTEM_PROMPT
        if gui_automation_enabled():
            system += _GUI_EXPERIMENTAL_PROMPT
        if expert_prompt:
            system = f"{expert_prompt}\n\n{system}"
        pf = active_skill_package.strip() or None
        skills_suffix = build_skills_system_suffix(package_filter=pf)
        if skills_suffix:
            system += skills_suffix
        system += build_agent_settings_suffix()
        from agent_runtime.mcp_client import build_mcp_prompt_suffix
        if mode in ("craft", "plan"):
            system += build_mcp_prompt_suffix()
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

    def _build_user_content(
        self,
        user_text: str,
        project: dict | None,
        referenced_files: list[str] | None = None,
    ) -> str:
        sections: list[str] = []
        if referenced_files:
            ref_ctx = build_referenced_files_context(referenced_files)
            if ref_ctx.strip():
                sections.append(
                    "用户通过 @ 引用的文件（请优先基于以下内容回答）：\n" + ref_ctx
                )
        chunks = search_chunks(
            user_text,
            project_id=project["id"] if project else None,
            include_standards=True,
        )
        if chunks:
            lines: list[str] = []
            for c in chunks[:5]:
                source = c.get("file_name") or c.get("standard_code") or "资料库"
                page = c.get("page_number")
                page_hint = f" p.{page}" if page else ""
                lines.append(f"- [{source}{page_hint}] {c['content'][:400]}")
            sections.append(
                "参考资料（来自资料库/标准库向量检索；若与问题相关则引用，不相关则忽略）：\n"
                + "\n".join(lines)
            )
        if sections:
            return "\n\n".join(sections) + f"\n\n用户指令：{user_text}"
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

    def _local_answer(
        self,
        user_text: str,
        project: dict | None = None,
        referenced_files: list[str] | None = None,
    ) -> str:
        text = user_text.strip()
        launch_keywords = ["打开", "启动", "运行", "open", "launch", "start"]
        is_action = any(text.startswith(kw) for kw in launch_keywords)

        if referenced_files:
            ref_ctx = build_referenced_files_context(referenced_files)
            if ref_ctx.strip() and not is_action:
                return f"基于你 @ 引用的文件：\n\n{ref_ctx}"

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

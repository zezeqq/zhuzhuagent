from __future__ import annotations

import queue
import threading

from PySide6.QtCore import QThread, Signal

from core.agent import Agent


class AgentWorker(QThread):
    """Event-driven agent worker that emits signals for each step of the LLM loop."""

    tool_call = Signal(dict)
    assistant_step = Signal(dict)
    thinking = Signal(str)
    token = Signal(str)
    plan_ready = Signal(str)
    task_started = Signal(int)
    final_reply = Signal(str)
    error = Signal(str)
    need_permission = Signal(dict)
    guidance_applied = Signal(str)

    def __init__(
        self,
        text: str,
        model: dict | None = None,
        project: dict | None = None,
        expert_prompt: str = "",
        mode: str = "craft",
        full_access: bool = False,
        history: list[dict] | None = None,
        attachments: list[str] | None = None,
        referenced_files: list[str] | None = None,
        conversation_id: int | None = None,
        auto_approve: bool = False,
        *,
        local_search_only: bool = False,
        plan_execute: bool = False,
        plan_context: str = "",
        active_skill_package: str = "",
    ):
        super().__init__()
        self.text = text
        self.model = model
        self.project = project
        self.expert_prompt = expert_prompt
        self.mode = mode
        self.full_access = full_access
        self.history = history or []
        self.attachments = attachments or []
        self.referenced_files = referenced_files or []
        self.conversation_id = conversation_id
        self.local_search_only = local_search_only
        self.plan_execute = plan_execute
        self.plan_context = plan_context
        self.active_skill_package = active_skill_package
        self._cancelled = False
        self._perm_event = threading.Event()
        self._perm_granted = False
        self._approve_all_remaining = bool(auto_approve or full_access)
        self._guidance_queue: queue.Queue[str] = queue.Queue()

    def cancel(self):
        self._cancelled = True
        self._perm_event.set()

    def submit_guidance(self, text: str) -> bool:
        """Inject mid-run user guidance without cancelling the worker."""
        if self._cancelled or not self.isRunning():
            return False
        cleaned = (text or "").strip()
        if not cleaned:
            return False
        self._guidance_queue.put(cleaned)
        return True

    def _drain_guidance(self) -> list[str]:
        items: list[str] = []
        while True:
            try:
                items.append(self._guidance_queue.get_nowait())
            except queue.Empty:
                break
        return items

    def submit_permission(self, granted: bool, *, approve_all: bool = False) -> None:
        if approve_all:
            self._approve_all_remaining = True
        self._perm_granted = granted or approve_all
        self._perm_event.set()

    def enable_auto_approve(self) -> None:
        self._approve_all_remaining = True

    def _request_permission(self, req: dict) -> bool:
        if self.full_access or self._approve_all_remaining:
            return True
        self._perm_event.clear()
        self._perm_granted = False
        self.need_permission.emit(req)
        self._perm_event.wait(timeout=600)
        return self._perm_granted

    def run(self):
        try:
            agent = Agent()
            perm_fn = None if self.full_access else self._request_permission
            guidance_poll = self._drain_guidance
            for event in agent.run(
                self.text,
                model=self.model,
                project=self.project,
                expert_prompt=self.expert_prompt,
                mode=self.mode,
                full_access=self.full_access or self._approve_all_remaining,
                history=self.history,
                attachments=self.attachments,
                referenced_files=self.referenced_files,
                request_permission=perm_fn,
                local_search_only=self.local_search_only,
                plan_execute=self.plan_execute,
                plan_context=self.plan_context,
                conversation_id=self.conversation_id,
                active_skill_package=self.active_skill_package,
                guidance_poll=guidance_poll,
            ):
                if self._cancelled:
                    self.final_reply.emit("已取消执行。")
                    return

                event_type = event.get("type", "")
                if event_type == "tool_call":
                    self.tool_call.emit(event)
                elif event_type == "assistant_step":
                    self.assistant_step.emit(event.get("message") or {})
                elif event_type == "thinking":
                    self.thinking.emit(event["content"])
                elif event_type == "token":
                    self.token.emit(event.get("content", ""))
                elif event_type == "plan_ready":
                    self.plan_ready.emit(event.get("content", ""))
                elif event_type == "task_started":
                    self.task_started.emit(int(event.get("task_id", 0)))
                elif event_type == "final_reply":
                    self.final_reply.emit(event["content"])
                elif event_type == "error":
                    self.error.emit(event["content"])
                elif event_type == "guidance":
                    self.guidance_applied.emit(event.get("content", ""))
        except Exception as exc:
            if not self._cancelled:
                self.error.emit(str(exc))


class ExpertTeamWorker(QThread):
    """专家团真并行：团长拆解 → 成员并发 LLM → 团长汇总。"""

    thinking = Signal(str)
    team_plan = Signal(str)
    member_done = Signal(str, str)
    final_reply = Signal(str)
    error = Signal(str)

    def __init__(
        self,
        text: str,
        team: dict,
        model: dict | None = None,
        *,
        custom_experts: list[dict] | None = None,
        conversation_id: int | None = None,
    ):
        super().__init__()
        self.text = text
        self.team = team
        self.model = model
        self.custom_experts = custom_experts or []
        self.conversation_id = conversation_id
        self._cancelled = False
        self._sections: list[tuple[str, str]] = []

    def cancel(self) -> None:
        self._cancelled = True

    def _progress(self, event: dict) -> None:
        if self._cancelled:
            return
        et = event.get("type")
        if et == "thinking":
            self.thinking.emit(str(event.get("content", "")))
        elif et == "team_plan":
            self.team_plan.emit(str(event.get("content", "")))
        elif et == "member_done":
            name = str(event.get("member", ""))
            content = str(event.get("content", ""))
            self._sections.append((name, content))
            self.member_done.emit(name, content)
        elif et == "team_sections":
            self._sections = list(event.get("sections") or self._sections)

    def run(self) -> None:
        from core.expert_team_runner import run_expert_team_parallel

        try:
            if not self.model:
                self.error.emit("专家团并行需要先在设置中配置 AI 模型。")
                return
            final = run_expert_team_parallel(
                self.team,
                self.text,
                self.model,
                custom_experts=self.custom_experts,
                progress=self._progress,
            )
            if self._cancelled:
                self.final_reply.emit("已取消执行。")
                return
            body_parts = [f"# 👥 {self.team.get('name', '专家团')} · 协作报告\n"]
            if self._sections:
                body_parts.append("## 成员并行产出\n")
                for name, content in self._sections:
                    body_parts.append(f"### {name}\n{content}\n")
            body_parts.append(f"## 团长汇总交付\n{final}")
            self.final_reply.emit("\n".join(body_parts))
        except Exception as exc:
            if not self._cancelled:
                self.error.emit(str(exc))


class VoiceTranscribeWorker(QThread):
    transcribed = Signal(str)
    error = Signal(str)

    def __init__(self, audio_path: str, model: dict | None):
        super().__init__()
        self.audio_path = audio_path
        self.model = model

    def run(self) -> None:
        try:
            if not self.model:
                self.error.emit("语音输入需要先选择一个已配置 API Key 的在线模型。")
                return
            from core.model_client import ModelClient
            text = ModelClient().transcribe_audio(self.audio_path, self.model)
            if text:
                self.transcribed.emit(text)
            else:
                self.error.emit("没有识别到语音内容。")
        except Exception as exc:
            self.error.emit(str(exc))

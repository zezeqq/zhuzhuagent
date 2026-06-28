from __future__ import annotations

import threading

from PySide6.QtCore import QThread, Signal

from core.agent import Agent


class AgentWorker(QThread):
    """Event-driven agent worker that emits signals for each step of the LLM loop."""

    tool_call = Signal(dict)
    thinking = Signal(str)
    token = Signal(str)
    plan_ready = Signal(str)
    task_started = Signal(int)
    final_reply = Signal(str)
    error = Signal(str)
    need_permission = Signal(dict)

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
        conversation_id: int | None = None,
        auto_approve: bool = False,
        *,
        local_search_only: bool = False,
        plan_execute: bool = False,
        plan_context: str = "",
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
        self.conversation_id = conversation_id
        self.local_search_only = local_search_only
        self.plan_execute = plan_execute
        self.plan_context = plan_context
        self._cancelled = False
        self._perm_event = threading.Event()
        self._perm_granted = False
        self._approve_all_remaining = bool(auto_approve or full_access)

    def cancel(self):
        self._cancelled = True
        self._perm_event.set()

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
            for event in agent.run(
                self.text,
                model=self.model,
                project=self.project,
                expert_prompt=self.expert_prompt,
                mode=self.mode,
                full_access=self.full_access or self._approve_all_remaining,
                history=self.history,
                attachments=self.attachments,
                request_permission=perm_fn,
                local_search_only=self.local_search_only,
                plan_execute=self.plan_execute,
                plan_context=self.plan_context,
                conversation_id=self.conversation_id,
            ):
                if self._cancelled:
                    self.final_reply.emit("已取消执行。")
                    return

                event_type = event.get("type", "")
                if event_type == "tool_call":
                    self.tool_call.emit(event)
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
        except Exception as exc:
            if not self._cancelled:
                self.error.emit(str(exc))

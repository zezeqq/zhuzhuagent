"""将数据库对话历史还原为 LLM 消息，并按 token 预算做 Cursor 式全量上下文管理。"""

from __future__ import annotations

import json
from typing import Any, Callable

from core.settings_store import get_setting

DEFAULT_CONTEXT_TOKENS = 128_000
RESERVE_OUTPUT_TOKENS = 4_096
RESERVE_TOOLS_SCHEMA_TOKENS = 8_000
MAX_STORED_TOOL_RESULT = 80_000
_GUIDE_PREFIX = "💡 引导 · "


def resolve_context_budget(model: dict | None = None) -> int:
    if model:
        for key in ("context_window", "max_context_tokens", "context_length"):
            raw = model.get(key)
            if raw:
                try:
                    return max(8_192, int(raw))
                except (TypeError, ValueError):
                    pass
    raw = get_setting("context_window_tokens", str(DEFAULT_CONTEXT_TOKENS))
    try:
        return max(8_192, int(raw or DEFAULT_CONTEXT_TOKENS))
    except (TypeError, ValueError):
        return DEFAULT_CONTEXT_TOKENS


def estimate_tokens(content: Any) -> int:
    if content is None:
        return 0
    if isinstance(content, str):
        text = content
    elif isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, dict):
                if part.get("type") == "text":
                    parts.append(str(part.get("text") or ""))
                elif part.get("type") == "image_url":
                    parts.append("[image]")
            else:
                parts.append(str(part))
        text = "\n".join(parts)
    else:
        text = str(content)
    if not text:
        return 0
    return max(1, len(text) // 3)


def estimate_messages_tokens(messages: list[dict]) -> int:
    total = 0
    for msg in messages:
        total += estimate_tokens(msg.get("content"))
        for tc in msg.get("tool_calls") or []:
            fn = tc.get("function") or {}
            total += estimate_tokens(fn.get("name"))
            total += estimate_tokens(fn.get("arguments"))
    return total


def _parse_tool_payload(content: str) -> dict[str, Any]:
    try:
        data = json.loads(content or "{}")
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def _normalize_user_text(text: str) -> str:
    raw = (text or "").strip()
    if raw.startswith(_GUIDE_PREFIX):
        raw = raw[len(_GUIDE_PREFIX):].strip()
    return raw


def _is_duplicate_user(stored: str, current_user_text: str) -> bool:
    a = _normalize_user_text(stored)
    b = (current_user_text or "").strip()
    if not a or not b:
        return False
    return a == b or a.endswith(b) or b in a


def history_rows_to_llm_messages(
    rows: list[dict],
    *,
    current_user_text: str = "",
    exclude_duplicate_user: bool = True,
) -> list[dict]:
    """把 DB messages 表记录还原为 OpenAI 格式（含 assistant.tool_calls + tool）。"""
    if not rows:
        return []

    work = list(rows)
    if (
        exclude_duplicate_user
        and current_user_text
        and work
        and work[-1].get("role") == "user"
        and _is_duplicate_user(work[-1].get("content", ""), current_user_text)
    ):
        work = work[:-1]

    out: list[dict] = []
    i = 0
    while i < len(work):
        row = work[i]
        role = row.get("role") or ""
        content = row.get("content") or ""

        if role == "agent_step":
            try:
                msg = json.loads(content)
            except json.JSONDecodeError:
                i += 1
                continue
            if isinstance(msg, dict):
                assistant = dict(msg)
                assistant.setdefault("role", "assistant")
                out.append(assistant)
            i += 1
            while i < len(work) and work[i].get("role") == "tool_call":
                data = _parse_tool_payload(work[i].get("content", ""))
                tc_id = str(data.get("id") or f"hist_{work[i].get('id', i)}")
                out.append({
                    "role": "tool",
                    "tool_call_id": tc_id,
                    "content": str(data.get("result") or ""),
                })
                i += 1
            continue

        if role == "user":
            out.append({"role": "user", "content": content})
            i += 1
            continue

        if role == "assistant":
            j = i + 1
            tool_rows: list[dict] = []
            while j < len(work) and work[j].get("role") == "tool_call":
                tool_rows.append(work[j])
                j += 1
            if tool_rows:
                tool_calls: list[dict] = []
                for tr in tool_rows:
                    data = _parse_tool_payload(tr.get("content", ""))
                    tc_id = str(data.get("id") or f"hist_{tr.get('id', len(out))}")
                    tool_calls.append({
                        "id": tc_id,
                        "type": "function",
                        "function": {
                            "name": str(data.get("name") or "unknown"),
                            "arguments": json.dumps(
                                data.get("args") or {},
                                ensure_ascii=False,
                            ),
                        },
                    })
                asst: dict[str, Any] = {
                    "role": "assistant",
                    "content": content or None,
                    "tool_calls": tool_calls,
                }
                out.append(asst)
                for tr, tc in zip(tool_rows, tool_calls):
                    data = _parse_tool_payload(tr.get("content", ""))
                    out.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": str(data.get("result") or ""),
                    })
                i = j
            else:
                out.append({"role": "assistant", "content": content})
                i += 1
            continue

        if role == "tool_call":
            data = _parse_tool_payload(content)
            tc_id = str(data.get("id") or f"hist_{row.get('id', i)}")
            out.append({
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": tc_id,
                    "type": "function",
                    "function": {
                        "name": str(data.get("name") or "unknown"),
                        "arguments": json.dumps(data.get("args") or {}, ensure_ascii=False),
                    },
                }],
            })
            out.append({
                "role": "tool",
                "tool_call_id": tc_id,
                "content": str(data.get("result") or ""),
            })
            i += 1
            continue

        i += 1
    return out


def _truncate_tool_text(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    head = max(limit // 2, 2000)
    tail = max(limit // 4, 1000)
    omitted = len(text) - head - tail
    return (
        text[:head]
        + f"\n\n…(中间省略约 {omitted} 字，完整结果已保存在对话记录中)…\n\n"
        + text[-tail:]
    )


def fit_messages_to_budget(
    messages: list[dict],
    max_tokens: int,
    *,
    protect_from_index: int = 1,
) -> None:
    """就地压缩最旧消息，优先保留最近轮次与完整工具链。protect_from_index 之后不压缩。"""
    if protect_from_index < 1:
        protect_from_index = 1

    budget = max(
        4_096,
        max_tokens - RESERVE_OUTPUT_TOKENS - RESERVE_TOOLS_SCHEMA_TOKENS,
    )
    if estimate_messages_tokens(messages) <= budget:
        return

    compressible = list(range(1, min(protect_from_index, len(messages))))
    if not compressible:
        return

    stale_vision = 0
    for idx in compressible:
        msg = messages[idx]
        role = msg.get("role")
        content = msg.get("content")

        if role == "tool":
            text = content if isinstance(content, str) else str(content)
            if len(text) > 12_000:
                msg["content"] = _truncate_tool_text(text, 12_000)
            elif len(text) > 6_000:
                msg["content"] = _truncate_tool_text(text, 6_000)

        if role == "user" and isinstance(content, list):
            has_image = any(
                isinstance(p, dict) and p.get("type") == "image_url"
                for p in content
            )
            if has_image:
                stale_vision += 1
                if stale_vision > 1:
                    msg["content"] = "（历史截图已移除，请基于最新截图或文字上下文继续）"

        if role == "assistant" and isinstance(content, str) and len(content) > 8_000:
            msg["content"] = _truncate_tool_text(content, 8_000)

    if estimate_messages_tokens(messages) <= budget:
        return

    for idx in compressible:
        msg = messages[idx]
        if msg.get("role") != "tool":
            continue
        text = msg.get("content")
        if isinstance(text, str) and len(text) > 3_000:
            msg["content"] = _truncate_tool_text(text, 3_000)
        if estimate_messages_tokens(messages) <= budget:
            return

    for idx in compressible:
        msg = messages[idx]
        if msg.get("role") != "assistant":
            continue
        content = msg.get("content")
        if isinstance(content, str) and len(content) > 2_000:
            msg["content"] = content[:2_000] + "…"
        if estimate_messages_tokens(messages) <= budget:
            return


def append_current_user_message(
    messages: list[dict],
    user_content: str,
    attachments: list[str] | None,
    *,
    encode_images: Callable[[list[str]], list[dict]],
    vision_supported: bool,
) -> None:
    attachment_list = attachments or []
    if attachment_list and vision_supported:
        image_parts = encode_images(attachment_list)
        if image_parts:
            content_array: list[dict] = [{"type": "text", "text": user_content}]
            content_array.extend(image_parts)
            messages.append({"role": "user", "content": content_array})
            return
    if attachment_list and not vision_supported:
        desc = "\n".join(f"[附件: {p}]" for p in attachment_list)
        messages.append({"role": "user", "content": f"{user_content}\n{desc}"})
        return
    messages.append({"role": "user", "content": user_content})


def build_agent_messages(
    *,
    system: str,
    history_rows: list[dict] | None,
    user_content: str,
    current_user_text: str,
    attachments: list[str] | None,
    model: dict | None,
    encode_images: Callable[[list[str]], list[dict]],
    vision_supported: bool,
) -> tuple[list[dict], int]:
    """组装 system + 全量历史 + 当前用户消息，返回 (messages, history_end_index)。"""
    budget = resolve_context_budget(model)
    messages: list[dict] = [{"role": "system", "content": system}]
    history_msgs = history_rows_to_llm_messages(
        history_rows or [],
        current_user_text=current_user_text,
        exclude_duplicate_user=True,
    )
    messages.extend(history_msgs)
    history_end = len(messages)
    append_current_user_message(
        messages,
        user_content,
        attachments,
        encode_images=encode_images,
        vision_supported=vision_supported,
    )
    fit_messages_to_budget(messages, budget, protect_from_index=history_end)
    return messages, history_end


def clip_tool_result_for_storage(result: str, *, limit: int = MAX_STORED_TOOL_RESULT) -> str:
    text = result or ""
    if len(text) <= limit:
        return text
    return (
        text[: limit - 120]
        + f"\n\n…(工具输出过长，已截断存储；共约 {len(text)} 字)…"
    )

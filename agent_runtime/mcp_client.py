"""MCP (Model Context Protocol) client — connect servers, expose tools to Agent."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import threading
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.settings_store import get_bool, get_setting, set_setting

logger = logging.getLogger(__name__)

MCP_TOOL_PREFIX = "mcp__"
_TRUNCATE = 8000
_CONNECT_TIMEOUT = 90
_CALL_TIMEOUT = 120
_refresh_lock = threading.Lock()

_SERVER_ID_RE = re.compile(r"[^a-zA-Z0-9_-]+")


def _sanitize_server_id(name: str) -> str:
    cleaned = _SERVER_ID_RE.sub("_", (name or "server").strip())
    return cleaned.strip("_") or "server"


def qualify_tool_name(server_id: str, tool_name: str) -> str:
    return f"{MCP_TOOL_PREFIX}{_sanitize_server_id(server_id)}__{tool_name}"


def parse_qualified_tool_name(qualified: str) -> tuple[str, str] | None:
    if not qualified.startswith(MCP_TOOL_PREFIX):
        return None
    rest = qualified[len(MCP_TOOL_PREFIX):]
    if "__" not in rest:
        return None
    server_id, tool_name = rest.split("__", 1)
    if not server_id or not tool_name:
        return None
    return server_id, tool_name


def is_mcp_tool(name: str) -> bool:
    return name.startswith(MCP_TOOL_PREFIX)


def load_mcp_config() -> dict:
    from agent_runtime.mcp_presets import merge_config_with_presets

    raw = get_setting("mcp_config", "").strip()
    saved: dict | None = None
    if raw:
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                saved = data
        except json.JSONDecodeError:
            logger.warning("Invalid mcp_config JSON in settings")
    return merge_config_with_presets(saved)


def load_mcp_example_config() -> dict:
    from agent_runtime.mcp_presets import build_default_mcp_config
    return build_default_mcp_config()


def ensure_default_mcp_config() -> None:
    """Seed mainstream MCP presets on first run."""
    if get_setting("mcp_config", "").strip():
        return
    save_mcp_config(load_mcp_example_config())


def save_mcp_config(data: dict) -> None:
    set_setting("mcp_config", json.dumps(data, ensure_ascii=False, indent=2), "json")


def mcp_enabled() -> bool:
    if get_bool("disable_all_plugins", False):
        return False
    return get_bool("enable_mcp", True)


def _build_subprocess_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    """Merge env for MCP child processes; augment PATH so GUI launches find npx/node."""
    env = {**os.environ, **(extra or {})}
    path = env.get("PATH", "")
    seen = {p.lower() for p in path.split(os.pathsep) if p}
    extras: list[str] = []
    candidates = [
        os.path.expandvars(r"%ProgramFiles%\nodejs"),
        os.path.expandvars(r"%ProgramFiles(x86)%\nodejs"),
        os.path.join(os.path.expanduser("~"), "AppData", "Roaming", "npm"),
    ]
    tools_root = Path.home() / "tools"
    if tools_root.is_dir():
        for node_home in tools_root.glob("node*"):
            if node_home.is_dir():
                candidates.append(str(node_home))
            for nested in node_home.glob("node-*"):
                if nested.is_dir():
                    candidates.append(str(nested))
    for cand in candidates:
        if not cand or not os.path.isdir(cand):
            continue
        key = cand.lower()
        if key in seen:
            continue
        seen.add(key)
        extras.append(cand)
    if extras:
        env["PATH"] = os.pathsep.join(extras) + os.pathsep + path
    return env


def _resolve_command(command: str, env: dict[str, str]) -> str:
    """Resolve CLI to an absolute path (Windows GUI often lacks npx on PATH)."""
    import shutil

    path = env.get("PATH", "")
    found = shutil.which(command, path=path)
    if found:
        return found
    if os.name == "nt":
        for ext in (".cmd", ".exe", ".bat"):
            found = shutil.which(f"{command}{ext}", path=path)
            if found:
                return found
    return command


def infer_mcp_tool_risk(tool_name: str) -> str:
    lower = tool_name.lower()
    if any(k in lower for k in ("delete", "remove", "write", "edit", "create", "move", "exec", "run")):
        if any(k in lower for k in ("delete", "remove", "exec", "run")):
            return "high"
        return "medium"
    return "low"


def _schema_to_parameters(schema: dict | None) -> dict:
    if not schema or not isinstance(schema, dict):
        return {"type": "object", "properties": {}, "required": []}
    out = dict(schema)
    out.setdefault("type", "object")
    out.setdefault("properties", {})
    out.setdefault("required", [])
    return out


def _format_call_result(result: Any) -> str:
    if getattr(result, "isError", False):
        prefix = "MCP tool error: "
    else:
        prefix = ""
    parts: list[str] = []
    for block in getattr(result, "content", []) or []:
        text = getattr(block, "text", None)
        if text is not None:
            parts.append(str(text))
        else:
            parts.append(str(block))
    text = prefix + ("\n".join(parts) if parts else "(empty MCP result)")
    if len(text) > _TRUNCATE:
        return text[:_TRUNCATE] + "\n…(truncated)"
    return text


@dataclass
class _ServerState:
    server_id: str
    display_name: str
    config: dict
    stack: AsyncExitStack | None = None
    session: Any = None
    tools: list[Any] = field(default_factory=list)
    error: str = ""


class MCPClientManager:
    """Background asyncio loop + persistent MCP sessions per server."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._servers: dict[str, _ServerState] = {}
        self._tool_defs: list[dict] = []
        self._tool_risks: dict[str, str] = {}
        self._last_error: str = ""
        self._server_name_map: dict[str, str] = {}

    def _ensure_loop(self) -> asyncio.AbstractEventLoop:
        with self._lock:
            if self._loop and self._loop.is_running():
                return self._loop
            loop = asyncio.new_event_loop()
            self._loop = loop
            self._thread = threading.Thread(
                target=loop.run_forever, name="MCPAsyncLoop", daemon=True,
            )
            self._thread.start()
            return loop

    def _run_coro(self, coro, timeout: float = _CONNECT_TIMEOUT) -> Any:
        loop = self._ensure_loop()
        fut = asyncio.run_coroutine_threadsafe(coro, loop)
        return fut.result(timeout=timeout)

    def shutdown(self) -> None:
        with self._lock:
            if not self._loop or not self._loop.is_running():
                return
            try:
                self._run_coro(self._disconnect_all(), timeout=30)
            except Exception:
                pass
            self._loop.call_soon_threadsafe(self._loop.stop)
            self._loop = None
            self._thread = None

    async def _disconnect_all(self) -> None:
        for state in list(self._servers.values()):
            if state.stack:
                try:
                    await state.stack.aclose()
                except Exception as exc:
                    logger.debug("MCP disconnect %s: %s", state.server_id, exc)
            state.stack = None
            state.session = None
            state.tools = []
        self._servers.clear()
        self._tool_defs.clear()
        self._tool_risks.clear()
        self._server_name_map.clear()

    def refresh_sync(self) -> str:
        """Reconnect all enabled MCP servers. Returns status summary."""
        if not mcp_enabled():
            self._run_coro(self._disconnect_all(), timeout=30)
            self._last_error = ""
            return "MCP disabled in settings."
        try:
            msg = self._run_coro(self._refresh_all(), timeout=_CONNECT_TIMEOUT)
            self._last_error = ""
            return msg
        except Exception as exc:
            self._last_error = str(exc)
            logger.exception("MCP refresh failed")
            return f"MCP refresh failed: {exc}"

    async def _refresh_all(self) -> str:
        await self._disconnect_all()
        config = load_mcp_config()
        servers = config.get("mcpServers") or {}
        if not isinstance(servers, dict) or not servers:
            return "No MCP servers configured."

        ok, fail = 0, 0
        for name, cfg in servers.items():
            if not isinstance(cfg, dict):
                continue
            if cfg.get("enabled", True) is False:
                continue
            server_id = _sanitize_server_id(name)
            state = _ServerState(server_id=server_id, display_name=name, config=cfg)
            self._servers[server_id] = state
            self._server_name_map[server_id] = name
            try:
                await self._connect_server(state)
                ok += 1
            except Exception as exc:
                state.error = str(exc)
                fail += 1
                logger.warning("MCP server %s failed: %s", name, exc)

        self._rebuild_tool_cache()
        tool_count = len(self._tool_defs)
        return f"Connected {ok} server(s), {fail} failed, {tool_count} tool(s) available."

    async def _connect_server(self, state: _ServerState) -> None:
        from agent_runtime.mcp_presets import strip_meta_keys

        try:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client
        except ImportError as exc:
            raise ImportError(
                "MCP SDK not installed. Run: pip install mcp"
            ) from exc

        cfg = strip_meta_keys(state.config)
        stack = AsyncExitStack()
        state.stack = stack

        if cfg.get("url"):
            url = str(cfg["url"]).strip()
            transport_type = (cfg.get("transport") or "sse").lower()
            if transport_type in ("streamable-http", "http"):
                from mcp.client.streamable_http import streamablehttp_client
                ctx = streamablehttp_client(url)
            else:
                from mcp.client.sse import sse_client
                ctx = sse_client(url)
            read, write, *_ = await stack.enter_async_context(ctx)
        else:
            command = (cfg.get("command") or "").strip()
            if not command:
                raise ValueError(f"Server '{state.display_name}' needs command or url")
            args = [str(a) for a in (cfg.get("args") or [])]
            env = _build_subprocess_env(
                {str(k): str(v) for k, v in (cfg.get("env") or {}).items()}
            )
            command = _resolve_command(command, env)
            cwd = cfg.get("cwd")
            params = StdioServerParameters(
                command=command,
                args=args,
                env=env,
                cwd=str(cwd) if cwd else None,
            )
            read, write = await stack.enter_async_context(stdio_client(params))

        session = await stack.enter_async_context(ClientSession(read, write))
        await session.initialize()
        state.session = session

        tools_resp = await session.list_tools()
        state.tools = list(tools_resp.tools or [])
        state.error = ""

    def _rebuild_tool_cache(self) -> None:
        defs: list[dict] = []
        risks: dict[str, str] = {}
        for state in self._servers.values():
            if not state.session or state.error:
                continue
            for tool in state.tools:
                t_name = getattr(tool, "name", "") or ""
                if not t_name:
                    continue
                qualified = qualify_tool_name(state.server_id, t_name)
                desc = getattr(tool, "description", "") or ""
                full_desc = f"[MCP:{state.display_name}] {desc}".strip()
                schema = getattr(tool, "inputSchema", None) or getattr(tool, "input_schema", None)
                defs.append({
                    "type": "function",
                    "function": {
                        "name": qualified,
                        "description": full_desc[:2000],
                        "parameters": _schema_to_parameters(schema if isinstance(schema, dict) else {}),
                    },
                })
                risks[qualified] = infer_mcp_tool_risk(t_name)
        self._tool_defs = defs
        self._tool_risks = risks

    def get_cached_tool_definitions(self) -> list[dict]:
        with self._lock:
            return list(self._tool_defs)

    def get_tool_risk(self, qualified_name: str) -> str:
        with self._lock:
            return self._tool_risks.get(qualified_name, "medium")

    def get_summary(self) -> dict[str, Any]:
        with self._lock:
            connected = sum(
                1 for s in self._servers.values() if s.session and not s.error
            )
            failed = sum(1 for s in self._servers.values() if s.error)
            return {
                "tool_count": len(self._tool_defs),
                "connected": connected,
                "failed": failed,
                "last_error": self._last_error,
            }

    def get_status_lines(self) -> list[str]:
        lines: list[str] = []
        with self._lock:
            if not self._servers:
                lines.append("No MCP servers connected.")
                return lines
            for state in self._servers.values():
                if state.error:
                    lines.append(f"✗ {state.display_name}: {state.error}")
                else:
                    lines.append(
                        f"✓ {state.display_name}: {len(state.tools)} tool(s)"
                    )
            lines.append(f"Total MCP tools exposed: {len(self._tool_defs)}")
        return lines

    def call_tool_sync(self, qualified_name: str, arguments: dict[str, Any] | None) -> str:
        parsed = parse_qualified_tool_name(qualified_name)
        if not parsed:
            return f"Invalid MCP tool name: {qualified_name}"
        server_id, tool_name = parsed
        if not mcp_enabled():
            return "MCP is disabled in Settings → Security."

        async def _call() -> str:
            state = self._servers.get(server_id)
            if not state or not state.session:
                await self._refresh_all()
                state = self._servers.get(server_id)
            if not state or not state.session:
                err = state.error if state else "server not in config"
                return f"MCP server unavailable ({server_id}): {err}"
            result = await state.session.call_tool(tool_name, arguments=arguments or {})
            return _format_call_result(result)

        try:
            return self._run_coro(_call(), timeout=_CALL_TIMEOUT)
        except Exception as exc:
            logger.exception("MCP call_tool %s", qualified_name)
            return f"MCP call failed ({qualified_name}): {exc}"

    def build_prompt_suffix(self) -> str:
        tools = self.get_cached_tool_definitions()
        if not tools or not mcp_enabled():
            return ""
        names = [t["function"]["name"] for t in tools[:12]]
        more = len(tools) - len(names)
        extra = f" (+{more} more)" if more > 0 else ""
        return (
            "\n\n## MCP external tools\n"
            "Tools prefixed `mcp__` connect to configured MCP servers (Settings → Tools → MCP).\n"
            f"Available: {', '.join(names)}{extra}\n"
            "Prefer MCP tools when they match the task (e.g. filesystem read/list)."
        )


mcp_manager = MCPClientManager()


def refresh_mcp_tools() -> str:
    return mcp_manager.refresh_sync()


def ensure_mcp_tools_loaded() -> str:
    """Load MCP tools if enabled but cache is empty (fixes startup race / GUI PATH)."""
    if not mcp_enabled():
        return "MCP disabled"
    if mcp_manager.get_cached_tool_definitions():
        return "MCP already loaded"
    with _refresh_lock:
        if mcp_manager.get_cached_tool_definitions():
            return "MCP already loaded"
        return refresh_mcp_tools()


def get_mcp_status_summary() -> dict[str, Any]:
    return mcp_manager.get_summary()


def shutdown_mcp() -> None:
    mcp_manager.shutdown()


def get_mcp_tool_definitions() -> list[dict]:
    return mcp_manager.get_cached_tool_definitions()


def get_mcp_tool_risk(name: str) -> str:
    return mcp_manager.get_tool_risk(name)


def execute_mcp_tool(name: str, args: dict[str, Any]) -> str:
    return mcp_manager.call_tool_sync(name, args)


def build_mcp_prompt_suffix() -> str:
    return mcp_manager.build_prompt_suffix()

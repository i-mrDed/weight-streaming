"""
MCP host (P7.4).

Manages MCP server connections so the local model can call tools from MCP
servers (like Jan's MCP host). Supports stdin (stdio) and SSE transports.

Design:
- Config stored as JSON in ``data/mcp/servers.json`` (local-first, offline).
- Each server = { id, name, transport: stdio|sse, command|url, enabled }.
- `list_tools()` connects to enabled servers and returns their tools.
- `call_tool(server_id, name, args)` invokes a tool and returns the result.
- Permission model: `auto_approve` per server (default false → caller decides).

Honest scope: this is a thin MCP client host. It does NOT proxy MCP to the
OpenAI API (that's the IDE's job via tool-calling). It lets the *console*
use MCP tools directly. Requires the `mcp` extra (`pip install mcp`).
"""
from __future__ import annotations

import json
import logging
import os
import threading
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

MCP_DIR = "data/mcp"
MCP_SERVERS_FILE = "data/mcp/servers.json"

# Common MCP stdio runners. Arbitrary executables are refused (W3 — the
# POST /v1/mcp/servers endpoint must not become a remote RCE primitive).
# Extend with WS_MCP_ALLOWED_COMMANDS (comma-separated) for custom runners.
DEFAULT_MCP_ALLOWED_COMMANDS = (
    "npx", "npm", "uvx", "node", "python", "python3",
    "deno", "bun", "bunx", "claude", "mcp",
)

_ID_RE = r"^[A-Za-z0-9._-]+$"


def _allowed_mcp_commands() -> frozenset:
    cmds = set(DEFAULT_MCP_ALLOWED_COMMANDS)
    extra = os.environ.get("WS_MCP_ALLOWED_COMMANDS", "")
    cmds.update(c.strip() for c in extra.split(",") if c.strip())
    return frozenset(cmds)


def validate_mcp_command(command: Optional[str]) -> None:
    """Reject an MCP stdio command that could execute arbitrary programs.

    The command must be a bare, allowlisted executable name — no path
    separators, no parent-dir traversal, no shell metacharacters. Raises
    ValueError with a user-readable message.
    """
    import re as _re
    if not command:
        return  # SSE servers have no command
    if not _re.fullmatch(_ID_RE, command):
        raise ValueError(
            f"command must be a bare executable name (no path/separators), got {command!r}"
        )
    if command not in _allowed_mcp_commands():
        raise ValueError(
            f"command {command!r} is not in the MCP allowlist; "
            f"set WS_MCP_ALLOWED_COMMANDS to add it"
        )


def validate_mcp_server(server: Dict[str, Any]) -> None:
    """Security validation for an MCP server config (W3 / SSRF-lite).

    - stdio: ``command`` must be a bare allowlisted executable name.
    - sse:   ``url`` must be http/https (no file:// or arbitrary schemes).

    Raises ValueError with a user-readable message.
    """
    transport = server.get("transport", "stdio")
    if transport == "sse":
        url = server.get("url") or ""
        if not url.lower().startswith(("http://", "https://")):
            raise ValueError(f"sse url must be http(s), got {url!r}")
        return
    validate_mcp_command(server.get("command"))


def _servers_file() -> str:
    base = os.environ.get("WS_DATA_DIR", "data")
    return os.path.join(base, "mcp", "servers.json")


class MCPServerStore:
    """JSON-file-backed MCP server config store."""

    def __init__(self, file_path: Optional[str] = None):
        self._file = file_path or _servers_file()
        self._lock = threading.Lock()
        os.makedirs(os.path.dirname(self._file), exist_ok=True)

    def _read(self) -> List[Dict[str, Any]]:
        try:
            with open(self._file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def _write(self, servers: List[Dict[str, Any]]) -> None:
        with self._lock:
            with open(self._file, "w", encoding="utf-8") as f:
                json.dump(servers, f, ensure_ascii=False, indent=2)

    def list(self) -> List[Dict[str, Any]]:
        return self._read()

    def get(self, server_id: str) -> Optional[Dict[str, Any]]:
        for s in self._read():
            if s.get("id") == server_id:
                return s
        return None

    def upsert(self, server: Dict[str, Any]) -> Dict[str, Any]:
        servers = self._read()
        for i, s in enumerate(servers):
            if s.get("id") == server.get("id"):
                servers[i] = {**s, **server}
                break
        else:
            servers.append(server)
        self._write(servers)
        return server

    def delete(self, server_id: str) -> bool:
        servers = self._read()
        new = [s for s in servers if s.get("id") != server_id]
        if len(new) == len(servers):
            return False
        self._write(new)
        return True


# ── MCP client host (requires the `mcp` extra) ────────────────────────

class MCPHost:
    """Connect to MCP servers and list/call their tools."""

    def __init__(self, store: Optional[MCPServerStore] = None):
        self._store = store or MCPServerStore()
        self._sessions: Dict[str, Any] = {}  # server_id -> ClientSession
        # stdio transport context managers entered without exit (same
        # deliberate pattern as sse below) — keeps the subprocess alive for
        # the lifetime of the session. GC'ing the CM would __aexit__ it and
        # kill the spawned process.
        self._contexts: Dict[str, Any] = {}  # server_id -> context manager
        self._lock = threading.Lock()

    def _mcp_available(self) -> bool:
        try:
            import mcp  # noqa: F401
            return True
        except ImportError:
            return False

    async def _connect(self, server: Dict[str, Any]) -> Any:
        """Open a ClientSession to a single MCP server."""
        from mcp import ClientSession
        from mcp.client.sse import sse_client
        from mcp.client.stdio import StdioServerParameters, stdio_client

        # Defense-in-depth (W3): even a hand-edited servers.json goes
        # through the same command/url validation as the API.
        validate_mcp_server(server)
        transport = server.get("transport", "stdio")
        if transport == "sse":
            url = server.get("url")
            if not url:
                raise ValueError(f"server {server.get('id')} needs url for sse")
            # Deliberate "enter without async-with": the transport context
            # must outlive this frame, so the context is entered but never
            # exited here (closed in close()). mcp >= 1.2 returns an async
            # context manager (not an awaitable) — enter it explicitly and
            # keep it alive in self._contexts.
            sid = server.get("id")
            if not sid:
                raise ValueError(f"server {server.get('name') or server.get('id')} needs an id")
            cm = sse_client(url)
            read, write = await cm.__aenter__()
            self._contexts[sid] = cm
        else:
            cmd = server.get("command")
            args = server.get("args", [])
            if not cmd:
                raise ValueError(f"server {server.get('id')} needs command for stdio")
            # mcp >= 1.2 stdio_client is @asynccontextmanager: it returns an
            # async context manager, not an awaitable. We enter it WITHOUT
            # async-with (deliberate, like sse below) and keep the CM alive
            # in self._contexts so the spawned process outlives this frame.
            # P7.4 was never E2E'd until 2026-08-12 — the command=/args=
            # kwargs form AND the bare-await form both failed on mcp 1.27.
            sid = server.get("id")
            if not sid:
                raise ValueError(f"server {server.get('name') or server.get('id')} needs an id")
            cm = stdio_client(StdioServerParameters(command=cmd, args=args))
            read, write = await cm.__aenter__()
            self._contexts[sid] = cm
        session = await ClientSession(read, write).__aenter__()
        await session.initialize()
        return session

    async def list_tools(self, server_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """List tools from enabled MCP servers."""
        if not self._mcp_available():
            return []
        servers = self._store.list()
        if server_id:
            servers = [s for s in servers if s.get("id") == server_id]
        out: List[Dict[str, Any]] = []
        for s in servers:
            if not s.get("enabled", True):
                continue
            try:
                session = await self._connect(s)
                tools = await session.list_tools()
                sid = s.get("id") or ""
                self._sessions[sid] = session
                for t in tools.tools:
                    out.append({
                        "server_id": sid,
                        "server_name": s.get("name"),
                        "name": t.name,
                        "description": t.description or "",
                        "inputSchema": t.inputSchema,
                    })
            except Exception as e:
                logger.warning("MCP list_tools %s failed: %s", s.get("id"), e)
        return out

    async def call_tool(self, server_id: str, name: str, args: Dict[str, Any]) -> Any:
        """Call a tool on an MCP server."""
        if not self._mcp_available():
            raise RuntimeError("MCP not installed (pip install mcp)")
        # Reuse an open session or reconnect.
        session = self._sessions.get(server_id)
        if session is None:
            server = self._store.get(server_id)
            if not server:
                raise ValueError(f"MCP server {server_id} not found")
            session = await self._connect(server)
            self._sessions[server_id] = session
        result = await session.call_tool(name, args)
        return result

    async def close(self) -> None:
        for sid, session in self._sessions.items():
            try:
                await session.__aexit__(None, None, None)
            except Exception:
                pass
        self._sessions.clear()
        for sid, cm in self._contexts.items():
            try:
                await cm.__aexit__(None, None, None)
            except Exception:
                pass
        self._contexts.clear()


_store: Optional[MCPServerStore] = None
_host: Optional[MCPHost] = None


def get_mcp_store() -> MCPServerStore:
    global _store
    if _store is None:
        _store = MCPServerStore()
    return _store


def get_mcp_host() -> MCPHost:
    global _host
    if _host is None:
        _host = MCPHost()
    return _host
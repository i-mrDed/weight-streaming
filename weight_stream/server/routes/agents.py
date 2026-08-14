"""Agent routes: assistants, MCP servers/tools, built-in workspace tools."""
from __future__ import annotations

import os
from typing import Any, Dict

from fastapi import APIRouter, FastAPI, HTTPException

from ..assistants import get_assistant_store
from ..mcp_host import get_mcp_store, get_mcp_host, validate_mcp_server
from ..schemas import (
    AssistantCreate,
    AssistantUpdate,
    MCPServerCreate,
)
from .. import workspace_tools
from .context import ServerContext


def build_router(app: FastAPI, ctx: ServerContext) -> APIRouter:
    """Register assistant / MCP / workspace-tool routes."""
    router = APIRouter()
    _astore = get_assistant_store()
    _mcpstore = get_mcp_store()
    _mcp = get_mcp_host()

    # ── Assistants (P7.2): named chat personas (system prompt + model + params)

    @router.get("/v1/assistants")
    async def list_assistants():
        """List all assistants."""
        return _astore.list()

    @router.get("/v1/assistants/{assistant_id}")
    async def get_assistant(assistant_id: str):
        """Get a single assistant."""
        a = _astore.get(assistant_id)
        if not a:
            raise HTTPException(status_code=404, detail=f"Assistant {assistant_id} not found")
        return a

    @router.post("/v1/assistants", status_code=201)
    async def create_assistant(body: AssistantCreate):
        """Create a new assistant."""
        return _astore.create(
            name=body.name,
            system_prompt=body.system_prompt,
            description=body.description,
            model_id=body.model_id,
            params=body.params,
        )

    @router.patch("/v1/assistants/{assistant_id}")
    async def update_assistant(assistant_id: str, body: AssistantUpdate):
        """Update an assistant."""
        a = _astore.update(
            assistant_id,
            name=body.name,
            system_prompt=body.system_prompt,
            description=body.description,
            model_id=body.model_id,
            params=body.params,
        )
        if not a:
            raise HTTPException(status_code=404, detail=f"Assistant {assistant_id} not found")
        return a

    @router.delete("/v1/assistants/{assistant_id}")
    async def delete_assistant(assistant_id: str):
        """Delete an assistant."""
        if not _astore.delete(assistant_id):
            raise HTTPException(status_code=404, detail=f"Assistant {assistant_id} not found")
        return {"status": "deleted", "id": assistant_id}

    # ── MCP (P7.4): manage MCP servers + list/call tools ───────────────

    @router.get("/v1/mcp/servers")
    async def list_mcp_servers():
        """List configured MCP servers."""
        return _mcpstore.list()

    @router.post("/v1/mcp/servers", status_code=201)
    async def add_mcp_server(body: MCPServerCreate):
        """Add an MCP server config. `command` must be an allowlisted bare
        executable name and `url` (sse) must be http(s) — arbitrary commands
        are refused (W3: this endpoint must not be an RCE primitive)."""
        try:
            validate_mcp_server({
                "transport": body.transport,
                "command": body.command,
                "url": body.url,
            })
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        import uuid as _uuid
        server = {
            "id": _uuid.uuid4().hex[:12],
            "name": body.name,
            "transport": body.transport,
            "command": body.command,
            "args": body.args or [],
            "url": body.url,
            "enabled": body.enabled,
            "auto_approve": body.auto_approve,
        }
        return _mcpstore.upsert(server)

    @router.delete("/v1/mcp/servers/{server_id}")
    async def delete_mcp_server(server_id: str):
        """Delete an MCP server config."""
        if not _mcpstore.delete(server_id):
            raise HTTPException(status_code=404, detail=f"MCP server {server_id} not found")
        return {"status": "deleted", "id": server_id}

    @router.get("/v1/mcp/tools")
    async def list_mcp_tools(server_id: str | None = None):
        """List tools from enabled MCP servers (connects to servers)."""
        try:
            tools = await _mcp.list_tools(server_id)
            return tools
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    @router.post("/v1/mcp/tools/{server_id}/{tool_name}/call")
    async def call_mcp_tool(server_id: str, tool_name: str, body: Dict[str, Any]):
        """Call a tool on an MCP server."""
        try:
            result = await _mcp.call_tool(server_id, tool_name, body)
            return {"server_id": server_id, "tool": tool_name, "result": result}
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    # ── Built-in agent tools (AGENT_TOOLS_PLAN.md) ────────────────────────
    # Path-guarded workspace tools (read/list inside the configured root) —
    # the second tool source for the console agent loop alongside MCP.

    @router.get("/v1/agent/config")
    async def get_agent_config():
        return workspace_tools.load_config()

    @router.put("/v1/agent/config")
    async def put_agent_config(body: Dict[str, Any]):
        """Validate + persist agent config (workspace root must exist)."""
        cfg = workspace_tools.load_config()
        if "enabled" in body:
            cfg["enabled"] = bool(body["enabled"])
        if "workspace_root" in body and body["workspace_root"]:
            root = os.path.expanduser(str(body["workspace_root"]))
            if not os.path.isdir(root):
                raise HTTPException(status_code=400, detail=f"workspace root is not a directory: {root}")
            cfg["workspace_root"] = root
        return workspace_tools.save_config(cfg)

    @router.get("/v1/agent/tools")
    async def list_agent_tools():
        """List built-in workspace tools ([] when disabled or root missing)."""
        return workspace_tools.list_tools()

    @router.post("/v1/agent/tools/{tool_name}/call")
    async def call_agent_tool(tool_name: str, body: Dict[str, Any]):
        """Call a built-in workspace tool (path-guarded server-side)."""
        try:
            result = workspace_tools.call_tool(tool_name, body)
            return {"tool": tool_name, "result": result}
        except workspace_tools.ToolError as e:
            raise HTTPException(status_code=e.status, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    return router

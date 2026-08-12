"""Built-in workspace tools for the chat agent loop (AGENT_TOOLS_PLAN.md).

Tools run ONLY inside the configured workspace root — every path is
expanded, realpath'd, and containment-checked before any I/O. This is
defense-in-depth against prompt injection: a model can read files inside
the root, never outside it (no ``..``, no absolute paths elsewhere, no
symlink escape).

State file: ``data/agent.json`` (mirrors ``data/tiering.json`` — path is
env-overridable via ``WS_AGENT_FILE`` so tests stay hermetic). The root
itself is ``WS_WORKSPACE_ROOT`` or the server's working directory.
"""
import json
import logging
import os
import stat
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

#: read_file size cap — a model must not pull whole 100 MB files into context.
MAX_READ_BYTES = 256 * 1024
#: list_directory entry cap (depth-1 listing only).
MAX_LIST_ENTRIES = 500
#: Tool result text cap enforced by the client too (chat.ts), kept here for
#: the API surface documentation.
TOOL_ERROR_PREFIX = "error"

_DEFAULT_AGENT_FILE = "data/agent.json"


def agent_file() -> str:
    """Resolve the state path at CALL time (env-overridable for tests)."""
    return os.environ.get("WS_AGENT_FILE", _DEFAULT_AGENT_FILE)


def default_config() -> Dict[str, Any]:
    """Fresh config: enabled, root = $WS_WORKSPACE_ROOT or the server cwd."""
    root = os.environ.get("WS_WORKSPACE_ROOT") or str(Path.cwd())
    return {"enabled": True, "workspace_root": root}


def load_config() -> Dict[str, Any]:
    """Read data/agent.json; never raises (falls back to defaults)."""
    base = default_config()
    try:
        raw = Path(agent_file()).read_text(encoding="utf-8")
        cfg = json.loads(raw)
        if isinstance(cfg, dict):
            base.update(
                {
                    "enabled": bool(cfg.get("enabled", base["enabled"])),
                    "workspace_root": str(cfg.get("workspace_root", base["workspace_root"])),
                }
            )
    except (FileNotFoundError, OSError):
        pass
    except Exception:
        logger.warning("agent config unreadable, using defaults", exc_info=True)
    return base


def save_config(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Persist config to data/agent.json (creates data/ if needed)."""
    path = Path(agent_file())
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    return cfg


# ── path guard ──────────────────────────────────────────────────────────


def workspace_root() -> Optional[str]:
    """Resolved workspace root, or None when unusable."""
    root = load_config().get("workspace_root")
    if not root:
        return None
    root = os.path.realpath(os.path.expanduser(str(root)))
    if not os.path.isdir(root):
        return None
    return root


class ToolError(Exception):
    """Raised for expected tool failures (bad path, too large, missing)."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def resolve_within(root: str, path: Any) -> str:
    """Resolve `path` (absolute or relative) and require containment in root.

    Raises ToolError(403) on any escape attempt (.., absolute outside root,
    symlink leaving the root). Returns the realpath.
    """
    if not isinstance(path, str) or not path.strip():
        raise ToolError("path is required", status=400)
    candidate = os.path.expanduser(path.strip())
    if not os.path.isabs(candidate):
        candidate = os.path.join(root, candidate)
    resolved = os.path.realpath(candidate)
    root_real = os.path.realpath(root)
    if not (resolved == root_real or resolved.startswith(root_real + os.sep)):
        raise ToolError(
            f"path escapes the workspace root ({root_real})", status=403
        )
    return resolved


# ── tools ───────────────────────────────────────────────────────────────


def _workspace_info(root: str) -> Dict[str, Any]:
    total = 0
    count = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for name in filenames:
            try:
                total += os.path.getsize(os.path.join(dirpath, name))
                count += 1
            except OSError:
                continue
    return {"root": root, "file_count": count, "total_bytes": total}


def _list_directory(root: str, args: Dict[str, Any]) -> Dict[str, Any]:
    target = resolve_within(root, args.get("path", ""))
    if not os.path.isdir(target):
        raise ToolError(f"not a directory: {target}", status=400)
    entries = []
    try:
        names = sorted(os.listdir(target))[:MAX_LIST_ENTRIES]
    except OSError as e:
        raise ToolError(f"cannot list directory: {e}", status=400)
    for name in names:
        full = os.path.join(target, name)
        try:
            st = os.stat(full)
        except OSError:
            continue
        if stat.S_ISDIR(st.st_mode):
            entries.append({"name": name, "type": "dir", "size": 0})
        elif stat.S_ISREG(st.st_mode):
            entries.append({"name": name, "type": "file", "size": st.st_size})
        else:
            entries.append({"name": name, "type": "other", "size": 0})
    return {"path": target, "entries": entries, "count": len(entries)}


def _read_file(root: str, args: Dict[str, Any]) -> Dict[str, Any]:
    target = resolve_within(root, args.get("path", ""))
    if not os.path.isfile(target):
        raise ToolError(f"not a regular file: {target}", status=400)
    size = os.path.getsize(target)
    if size > MAX_READ_BYTES:
        raise ToolError(
            f"file too large: {size} bytes > {MAX_READ_BYTES} cap — read a smaller file or a snippet",
            status=400,
        )
    try:
        text = Path(target).read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        raise ToolError(f"cannot read file: {e}", status=400)
    return {"path": target, "size": size, "content": text}


TOOLS: list[Dict[str, Any]] = [
    {
        "name": "workspace_info",
        "description": (
            "Return the workspace root path, file count and total bytes. "
            "Call this first to learn the workspace layout."
        ),
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "list_directory",
        "description": (
            "List the entries (files and subdirectories) of a directory inside "
            "the workspace. The path may be absolute or relative to the workspace root."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Directory path, absolute or relative to the workspace root",
                }
            },
            "required": ["path"],
        },
    },
    {
        "name": "read_file",
        "description": (
            "Read a text file inside the workspace (UTF-8, up to 256 KB). "
            "Use for source files, docs, configs — not for binary files."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "File path, absolute or relative to the workspace root",
                }
            },
            "required": ["path"],
        },
    },
]


def list_tools() -> list[Dict[str, Any]]:
    """Built-in tool definitions for /v1/agent/tools ([] when disabled)."""
    cfg = load_config()
    if not cfg.get("enabled", False) or workspace_root() is None:
        return []
    return TOOLS


def call_tool(name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    """Dispatch a built-in tool call. Raises ToolError on bad input/escapes."""
    root = workspace_root()
    if root is None:
        raise ToolError("workspace tools are not available (root missing or disabled)", status=404)
    if name == "workspace_info":
        return _workspace_info(root)
    if name == "list_directory":
        return _list_directory(root, args or {})
    if name == "read_file":
        return _read_file(root, args or {})
    raise ToolError(f"unknown workspace tool: {name}", status=404)

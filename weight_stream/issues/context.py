"""Collect debug context for issue reports (with secret redaction)."""
from __future__ import annotations

import os
import platform
import re
import sys
from typing import Any, Dict, List, Optional

_SECRET_RE = re.compile(
    r"(token|key|secret|password|passwd|credential|authorization)",
    re.IGNORECASE,
)


def _redact_value(key: str, value: Any) -> Any:
    if _SECRET_RE.search(key):
        return "***REDACTED***"
    if isinstance(value, str) and (
        value.startswith("ghp_") or value.startswith("sk-") or "Bearer " in value
    ):
        return "***REDACTED***"
    return value


def _redact_dict(d: Dict[str, Any]) -> Dict[str, Any]:
    return {k: _redact_value(k, v) for k, v in d.items()}


def collect_debug_context(
    *,
    model_path: Optional[str] = None,
    model_architecture: Optional[str] = None,
    last_error: Optional[str] = None,
    last_endpoint: Optional[str] = None,
    extra: Optional[Dict[str, Any]] = None,
    log_tail: Optional[List[str]] = None,
    tiering: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build a privacy-safe debug bundle for issue reports."""
    app_version = "unknown"
    try:
        from weight_stream import __version__
        app_version = __version__
    except Exception:
        pass

    llama_ver = "not installed"
    try:
        import llama_cpp
        llama_ver = getattr(llama_cpp, "__version__", "unknown")
    except Exception:
        pass

    ctx: Dict[str, Any] = {
        "app_version": app_version,
        "llama_cpp_version": llama_ver,
        "python_version": sys.version.split()[0],
        "os": platform.platform(),
        "cwd": os.getcwd(),
        "model_path": model_path,
        "model_architecture": model_architecture,
        "last_error": last_error,
        "last_endpoint": last_endpoint,
        "env": _redact_dict({
            k: v for k, v in os.environ.items()
            if k.startswith("WS_")
        }),
    }
    if log_tail:
        ctx["server_log_tail"] = log_tail[-50:]
    if extra:
        ctx["extra"] = _redact_dict(extra)
    if tiering is not None:
        # Aggregated auto-tiering routing summary (enabled + per-tier/per-
        # reason totals). The server never sends prompts in a report.
        ctx["tiering"] = _redact_dict(tiering)
    return ctx

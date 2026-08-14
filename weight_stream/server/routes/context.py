"""Shared state handed to every route module.

``create_app`` builds one ``ServerContext`` with the services the route
handlers need, then each ``routes.*`` module's ``register(app, ctx)``
uses it. This replaces the closure captures the handlers previously
relied on, without changing any route behavior.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, List, Optional

from ..model_manager import ModelManager
from ..usage import UsageRecorder
from ...issues import IssueService
from ..hub import DownloadManager


@dataclass
class ServerContext:
    """Everything a route handler needs beyond its own request/body."""

    manager: ModelManager
    usage_recorder: Optional[UsageRecorder]
    issue_service: Optional[IssueService] = None
    hub_manager: Optional[DownloadManager] = None
    recent_errors: List[str] = field(default_factory=list)
    # WS_API_TOKEN ("" = auth disabled). The HTTP middleware and the
    # WebSocket handler share this exact value.
    api_token: str = ""
    # WebSocket Origin guard (scheme+host+port canonical match against
    # the CORS allowlist). Supplied by create_app (it owns the allowlist).
    ws_origin_allowed: Optional[Callable[[str], bool]] = None

"""
FastAPI REST API server for weight-streaming.

All frontends (TUI, Gradio, SPA, Desktop GUI) and Agentic IDEs
connect through this server. The server provides:

- POST /v1/generate         — text generation (streaming supported)
- GET  /v1/stats            — performance statistics
- GET  /v1/models           — list loaded models
- POST /v1/models/load      — load a model
- POST /v1/models/unload    — unload a model
- WS   /v1/stream           — WebSocket streaming
- POST /v1/chat/completions — OpenAI-compatible endpoint

Route handlers live in ``routes/`` modules (each registers via a
``build_router(app, ctx)`` factory); this module owns the application
factory: middleware, static mounts, lifespan, and router wiring.
"""

from __future__ import annotations

import logging
import os
import secrets
from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import get_config, ServerConfig
from .model_manager import ModelManager
from .usage import UsageRecorder
from .logs import (
    RecentLogsHandler,
    attach_server_logging,
    detach_server_logging,
    LOG_LINE_FORMAT,
)
from .hub import DownloadManager
from ..issues import IssueService
from .routes.context import ServerContext
from .routes import system as routes_system
from .routes import models as routes_models
from .routes import stream as routes_stream
from .routes import issues as routes_issues
from .routes import hub as routes_hub
from .routes import agents as routes_agents
from .routes import tiering as routes_tiering

logger = logging.getLogger(__name__)


def create_app(config: Optional[ServerConfig] = None) -> tuple[FastAPI, ModelManager]:
    """Create and configure the FastAPI application with ModelManager."""
    if config is None:
        config = get_config()

    from weight_stream import __version__  # lazy: avoid circular import at module load

    # Generation-usage recorder (P4): ring buffer + JSONL persistence. Path is
    # overridable so tests can point it at a temp file instead of data/.
    usage_path = os.environ.get(
        "WS_USAGE_HISTORY_FILE", os.path.join("data", "usage_history.jsonl")
    )
    usage_recorder = UsageRecorder(usage_path)
    manager = ModelManager(config, usage_recorder=usage_recorder)
    issue_service = IssueService()

    # Logging (P4): a ring-buffer handler feeds both the legacy `recent_errors`
    # list (fixing the dead /v1/debug/context log_tail) and the larger ring that
    # backs GET /v1/logs/tail. Handlers attach to the root logger on startup and
    # detach on shutdown — additive; console/uvicorn logging stays untouched.
    recent_errors: list[str] = []
    ring_handler = RecentLogsHandler(mirror=recent_errors)
    ring_handler.setFormatter(logging.Formatter(LOG_LINE_FORMAT))
    log_file = os.environ.get("WS_LOG_FILE", os.path.join("data", "server.log"))

    # Hugging Face Hub (P4): search + GGUF download. Uses injectable HTTP
    # callables so tests run fully offline (monkeypatch the urllib defaults).
    hub_manager = DownloadManager()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        """Startup and shutdown lifecycle."""
        app.state.recent_logs = ring_handler
        file_handler = attach_server_logging(config, ring_handler, log_file)
        logger.info(f"Server starting on {config.host}:{config.port}")
        yield
        logger.info("Server shutting down...")
        await manager.shutdown()
        logger.info("Server stopped")
        detach_server_logging(ring_handler, file_handler)

    app = FastAPI(
        title="Weight Streaming API",
        description=(
            "Run LLMs larger than your RAM — speculative weight streaming from NVMe. "
            "OpenAI-compatible API for IDE/agent integration."
        ),
        version=__version__,
        lifespan=lifespan,
    )

    # CORS — local-first hardening (W2): only loopback origins may call the
    # API with credentials. A wildcard + allow_credentials would let ANY
    # website open in a browser drive this local server (load/unload models,
    # delete files, invoke MCP tools — RCE). Extra origins for LAN/dev use
    # go through WS_CORS_ORIGINS (comma-separated).
    _cors_origins = [
        "http://localhost",
        "http://127.0.0.1",
        "http://localhost:8765",
        "http://127.0.0.1:8765",
    ]
    _cors_extra = os.environ.get("WS_CORS_ORIGINS", "").strip()
    if _cors_extra:
        _cors_origins += [
            o.strip() for o in _cors_extra.split(",") if o.strip()
        ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # WebSocket origin guard (fix/ws-security): CORS middleware does NOT
    # apply to websockets, so we check the Origin header ourselves using the
    # same allowlist (loopback + WS_CORS_ORIGINS). A browser page on any
    # other site cannot open ws://localhost:8765/v1/stream.
    def _ws_origin_allowed(origin: str) -> bool:
        """WS Origin guard — see routes/stream.py for the caller."""
        if not origin:
            # non-browser clients (CLI, curl, tests) send no Origin — allow
            return True
        try:
            from urllib.parse import urlparse

            def _norm(u: str) -> tuple[str, str, Optional[int]]:
                # canonical (scheme, host, port): lowercase, default port
                # folded away so "http://localhost:80" == "http://localhost"
                o = urlparse(u)
                scheme = (o.scheme or "").lower()
                host = (o.hostname or "").lower()
                port = o.port
                if port is not None and (
                    (scheme == "http" and port == 80)
                    or (scheme == "https" and port == 443)):
                    port = None
                return scheme, host, port

            target = _norm(origin)
            if not target[0] or not target[1]:
                return False
            for allowed in _cors_origins:
                if _norm(allowed) == target:
                    return True
        except Exception:
            return False
        return False

    # API auth (B1): when WS_API_TOKEN is set, every /v1/* request must
    # carry `Authorization: Bearer <token>` (constant-time compare). The
    # console/static/health pages stay open — the console sends the token
    # through its API client (localStorage 'ws-api-token') when configured.
    # Honest default: no token = no auth (local-first — isolate the server;
    # see the API docs note).
    _api_token = os.environ.get("WS_API_TOKEN", "").strip()
    if _api_token:

        @app.middleware("http")
        async def _require_api_token(request: Request, call_next):  # type: ignore[no-untyped-def]
            if request.url.path.startswith("/v1/"):
                auth = request.headers.get("authorization", "")
                if not secrets.compare_digest(auth, f"Bearer {_api_token}"):
                    return JSONResponse(
                        status_code=401,
                        content={
                            "error": "unauthorized",
                            "code": "UNAUTHORIZED",
                            "detail": (
                                "this server requires WS_API_TOKEN — send "
                                "Authorization: Bearer <token>"
                            ),
                        },
                    )
            return await call_next(request)

    # Mount static files (SPA)
    static_dir = os.path.join(os.path.dirname(__file__), "static")
    if os.path.isdir(static_dir):
        # Legacy SPA — kept at /app-legacy for one release after the P6
        # promote (rollback path). The Console is now the primary UI.
        app.mount("/app-legacy", StaticFiles(directory=static_dir, html=True), name="static-legacy")

    # Console — new dashboard (frontend/ built with Vite, prebuilt assets
    # committed so the server needs no Node toolchain). PRIMARY UI since P6.
    console_dir = os.path.join(static_dir, "console")
    if os.path.isdir(console_dir):
        app.mount("/console", StaticFiles(directory=console_dir, html=True), name="console")

    # Expose the ring-buffer log handler for GET /v1/logs/tail (it fills once
    # the lifespan attaches it to the root logger).
    app.state.recent_logs = ring_handler
    # Expose the Hub download manager (test access + P5 wiring convenience).
    app.state.hub_manager = hub_manager
    # Expose the usage recorder so feature endpoints (auto-tiering routing
    # stats) can append event telemetry to the same ring + JSONL.
    app.state.usage_recorder = usage_recorder

    # Shared context handed to every route module (replaces the closure
    # captures the handlers previously relied on).
    ctx = ServerContext(
        manager=manager,
        usage_recorder=usage_recorder,
        issue_service=issue_service,
        hub_manager=hub_manager,
        recent_errors=recent_errors,
        api_token=_api_token,
        ws_origin_allowed=_ws_origin_allowed,
    )

    # Route modules (see routes/ — each is a focused group with its own
    # build_router(app, ctx) factory; paths/responses unchanged).
    for module in (
        routes_system,
        routes_models,
        routes_stream,
        routes_issues,
        routes_hub,
        routes_agents,
        routes_tiering,
    ):
        app.include_router(module.build_router(app, ctx))

    return app, manager


# ── Default Application Instance ──────────────────────────────────
app, manager = create_app()


# ── Re-exports (kept for tests / external callers) ─────────────────
# These helpers moved to routes/hub.py with the route split; re-export
# here so existing imports (e.g. tests/test_p4_hub.py) keep working.
from .routes.hub import (  # noqa: E402  (after create_app for style parity)
    _assistants_referencing,
    _assistant_refs_batch,
    _reveal_in_explorer,
)

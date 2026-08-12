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
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import secrets
import time
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Dict, Optional

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from .config import (
    get_config,
    ServerConfig,
    get_model_search_dirs,
    describe_config,
    CONFIG_ENV_KEYS,
)
from .model_manager import ModelManager
from .usage import UsageRecorder
from .logs import (
    RecentLogsHandler,
    attach_server_logging,
    detach_server_logging,
    LOG_LINE_FORMAT,
    DEFAULT_TAIL_LINES,
)
from .hub import DownloadManager, HubUpstreamError, HubValidationError
from .recommended import to_payload as recommended_payload
from .research import ResearchValidationError, experiment as read_experiment
from .openai_compat import handle_chat_completion
from .anthropic_compat import handle_anthropic_messages
from ..issues import (
    IssueCreate,
    IssueService,
    IssueUpdate,
    IssueVerify,
    collect_debug_context,
)
from .schemas import (
    GenerateRequest,
    GenerateResponse,
    ModelLoadRequest,
    ModelUnloadRequest,
    ModelActionResponse,
    ModelStatus,
    ErrorResponse,
    ChatCompletionRequest,
    HubDownloadRequest,
    HubDeleteRequest,
    HubClearRequest,
    AssistantCreate,
    AssistantUpdate,
    MCPServerCreate,
    ConversationSummarizeRequest,
    ConversationSummarizeResponse,
)
from .streaming import sse_stream, ws_stream

logger = logging.getLogger(__name__)


def _reveal_in_explorer(path: str) -> dict:
    """Reveal a file in the OS file manager (server-side subprocess).

    Opens the parent folder with the file selected where the platform
    supports it (Windows ``explorer /select``, macOS ``open -R``); Linux
    falls back to opening the folder. Returns ``{"error": ...}`` honestly
    when the shell command fails — never a fake success.

    Known platform quirk (documented, not worked around): ``explorer``
    mis-parses ``/select,<path>`` when the path itself contains a comma
    (GGUF model paths almost never do; the list-form Popen keeps the arg
    intact with no shell involved, so only the comma case misbehaves).
    """
    import subprocess, sys
    folder = os.path.dirname(path)
    try:
        if sys.platform == "win32":
            # explorer /select needs the comma syntax; quoting is handled
            # by Popen's list form (no shell involved).
            subprocess.Popen(["explorer", f"/select,{os.path.normpath(path)}"])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-R", path])
        else:
            subprocess.Popen(["xdg-open", folder])
        return {"ok": True}
    except Exception as e:
        return {"error": str(e)}

def _assistant_refs_batch(filenames: list[str]) -> dict[str, list[str]]:
    """filename → assistant names pinned to that file's suggested model id.

    Model references across features are keyed by the SUGGESTED model id
    (basename without ``.gguf`` — the same rule as the Console's
    ``suggestModelId`` used when loading a downloaded model and when a
    conversation is created against it). So an assistant pinned to that id
    silently loses its model if the file is deleted — the delete dialogs
    warn about exactly these references.

    ONE store read for the whole batch (``clear`` can carry several done
    tasks — per-task scans would re-read every assistant JSON N times). The
    store is read LIVE at request time, so an assistant created in another
    tab counts. Returns {} on any store problem — a reference-scan failure
    must never block a delete.
    """
    wanted: dict[str, str] = {}
    for f in filenames:
        model_id = os.path.splitext(os.path.basename(f))[0]
        if model_id:
            wanted[f] = model_id
    if not wanted:
        return {}
    try:
        from .assistants import get_assistant_store
        store_list = get_assistant_store().list()
    except Exception:
        return {}
    by_id: dict[str, list[str]] = {m: [] for m in set(wanted.values())}
    for a in store_list:
        mid = a.get("model_id") or ""
        if mid in by_id:
            by_id[mid].append(a.get("name") or a.get("id", "?"))
    return {f: by_id[m] for f, m in wanted.items()}


def _assistants_referencing(filename: str) -> list[str]:
    """Assistant names for ONE file (see ``_assistant_refs_batch``)."""
    return _assistant_refs_batch([filename]).get(filename, [])


# ── PATCH /v1/config policy (P4 v1.1) ───────────────────────────────
# Which runtime config mutations are safe. ModelManager has no setters, so
# allowed keys mutate ``manager._cfg`` directly (it reads ``self._cfg`` live):
#   SAFE  — read on every relevant tick → effective immediately.
#   GATED — read only at model load → effective for models loaded afterward.
#   REJECT — restart-only, inconsistent mid-run, or never enforced (no-op);
#            answered with 409 + an env snippet (honest capability claim).
_CONFIG_SAFE_KEYS = {"idle_unload_timeout", "max_loaded_models"}
_CONFIG_GATED_KEYS = {
    "default_buffer_mb", "default_n_ctx", "default_n_threads",
    "default_gpu_layers", "default_kv_cache_type",
}
_CONFIG_INT_KEYS = {
    "default_buffer_mb", "default_n_ctx", "default_n_threads",
    "max_loaded_models", "default_gpu_layers",
}
_CONFIG_REJECT_REASONS = {
    "host": "bind address is fixed at startup; restart required",
    "port": "bind port is fixed at startup; restart required",
    "log_level": "logging is configured at startup; restart required",
    "lower_process_priority": "applied only on first model load / last unload; restart for a consistent state",
    "max_concurrent_requests": "not enforced by the model manager yet (no-op); set via env + restart",
    "request_queue_depth": "not enforced by the model manager yet (no-op); set via env + restart",
}

# ── Application factory ─────────────────────────────────────────────


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
    async def lifespan(app: FastAPI):
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

    # API auth (B1): when WS_API_TOKEN is set, every /v1/* request must
    # carry `Authorization: Bearer <token>` (constant-time compare). The
    # console/static/health pages stay open — the console sends the token
    # through its API client (localStorage 'ws-api-token') when configured.
    # Honest default: no token = no auth (local-first — isolate the server;
    # see the API docs note).
    _api_token = os.environ.get("WS_API_TOKEN", "").strip()
    if _api_token:

        @app.middleware("http")
        async def _require_api_token(request: Request, call_next):
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

    # Health check
    @app.get("/health")
    async def health():
        return {"status": "ok", "version": __version__}
    
    # Root → Console (primary UI since P6 promote; legacy at /app-legacy)
    @app.get("/")
    async def root():
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url="/console/", status_code=302)
    
    # API info (for developers / health dashboards)
    @app.get("/api")
    async def api_info():
        from weight_stream import __version__
        return {
            "message": f"Weight Streaming API v{__version__}",
            "docs": "/docs",
            "app": "/app-legacy",
            "console": "/console",
            "health": "/health",
            "issues": "/v1/issues",
        }
    
    # ── REST Endpoints ──────────────────────────────────────────────

    @app.get("/v1/config")
    async def read_config():
        """
        Effective server configuration.

        Each key reports `{"value": …, "source": "env"|"default"}` — the
        source is re-checked against the real `WS_*` environment variable.
        Also returns the model search directories (shared with
        `/v1/models/scan`), the issues directory, and the package version.

        Honest limitation: a value injected via the CLI constructor (no env
        var) is reported as `"default"`; the effective value is still correct.
        """
        from weight_stream import __version__
        return {
            "config": describe_config(manager._cfg),
            "models_dirs": get_model_search_dirs(),
            "issues_dir": str(issue_service.store.base),
            "version": __version__,
        }

    @app.patch("/v1/config")
    async def patch_config(body: dict):
        """
        Mutate the safe subset of server config at runtime (v1.1).

        - **Applied immediately**: `idle_unload_timeout`, `max_loaded_models`.
        - **Applied with a note** (next model load only): `default_buffer_mb`,
          `default_n_ctx`, `default_n_threads`.
        - **Everything else → 409** + an env snippet (restart-only, inconsistent
          mid-run, or not yet enforced — an honest capability claim).

        ModelManager has no setters, so allowed keys mutate the live config
        object it reads from. Applied keys are reported with `source: "runtime"`.
        """
        if not isinstance(body, dict) or not body:
            raise HTTPException(status_code=400, detail="provide a JSON object of config keys")

        rejected: dict[str, str] = {}
        coerced: dict[str, Any] = {}
        for key, val in body.items():
            if key in _CONFIG_REJECT_REASONS:
                rejected[key] = _CONFIG_REJECT_REASONS[key]
                continue
            if key not in _CONFIG_SAFE_KEYS and key not in _CONFIG_GATED_KEYS:
                raise HTTPException(status_code=400, detail=f"unknown config key: {key}")
            try:
                if key in _CONFIG_INT_KEYS:
                    coerced[key] = int(val)
                elif key == "idle_unload_timeout":
                    coerced[key] = float(val)
                else:
                    coerced[key] = val
            except (TypeError, ValueError):
                raise HTTPException(status_code=400, detail=f"{key}: invalid value {val!r}")
            if key in _CONFIG_INT_KEYS and coerced[key] < 1:
                # default_gpu_layers is special: -1 = auto (valid) and
                # 0 = CPU-only (valid). Anything below -1 is nonsense.
                if not (key == "default_gpu_layers" and coerced[key] >= -1):
                    raise HTTPException(status_code=400, detail=f"{key} must be >= 1")
            if key == "idle_unload_timeout" and coerced[key] < 0:
                raise HTTPException(status_code=400, detail="idle_unload_timeout must be >= 0")

        if rejected:
            snippet = "\n".join(
                f"{CONFIG_ENV_KEYS[k]}={body[k]}"
                for k in rejected if k in CONFIG_ENV_KEYS
            )
            return JSONResponse(
                status_code=409,
                content={
                    "detail": "these keys are not runtime-mutable (restart required or not enforced)",
                    "restart_required": True,
                    "rejected": rejected,
                    "snippet": snippet,
                },
            )

        overrides = set(getattr(manager._cfg, "_runtime_overrides", set()))
        applied: dict[str, dict] = {}
        notes: dict[str, str] = {}
        for key, val in coerced.items():
            setattr(manager._cfg, key, val)
            overrides.add(key)
            applied[key] = {"value": val, "source": "runtime"}
            if key in _CONFIG_GATED_KEYS:
                notes[key] = "applies to models loaded after this change"
        manager._cfg._runtime_overrides = overrides  # type: ignore[attr-defined]

        return {
            "status": "applied",
            "applied": applied,
            "notes": notes,
            "config": describe_config(manager._cfg),
        }

    @app.get("/v1/usage/history")
    async def usage_history(limit: int | None = None, since: int | None = None):
        """
        Generation usage history — real per-generation telemetry (tokens,
        tok/s, elapsed, paging summary) recorded from the single ModelManager
        choke point, so native `/v1/generate`, OpenAI/Anthropic compat, and
        WebSocket generations are all covered.

        - `?limit=N` — newest N records (0/omitted-negative → none).
        - `?since=<epoch_ms>` — only records with `ts >= since`.

        `tok_s` is `null` when a streaming path had no real measurement
        (never fabricated). Backed by a 500-entry ring buffer persisted to
        `data/usage_history.jsonl`.
        """
        records = manager.usage_history(limit=limit, since=since)
        return {
            "history": records,
            "count": len(records),
            "capacity": manager.usage_capacity(),
        }

    @app.get("/v1/logs/tail")
    async def logs_tail(lines: int = DEFAULT_TAIL_LINES):
        """
        Tail recent server log lines from the in-memory ring buffer fed by the
        root logging handler (default 100, capped at 1000). The same handler
        now also backs `/v1/debug/context`'s `log_tail` (previously always
        empty). Empty until the app lifespan attaches logging (running under
        uvicorn or a `with TestClient(app)` block).
        """
        handler = getattr(app.state, "recent_logs", None)
        if handler is None:
            return {"lines": [], "count": 0}
        items = handler.tail(lines)
        return {"lines": items, "count": len(items)}

    @app.post("/v1/generate", response_model=GenerateResponse)
    async def generate(request: GenerateRequest):
        """
        Generate text from a loaded model.
        
        **Non-streaming mode (default):**
        ```json
        {"model": "default", "prompt": "Hello", "max_tokens": 100}
        ```
        
        **Streaming mode:**
        ```json
        {"model": "default", "prompt": "Hello", "max_tokens": 100, "stream": true}
        ```
        Returns `text/event-stream` with token-by-token output.
        """
        if request.stream:
            return await _stream_generate(request, manager)
        
        try:
            result = await manager.generate(
                model_id=request.model,
                prompt=request.prompt,
                max_tokens=request.max_tokens,
                temperature=request.temperature,
                top_p=request.top_p,
            )
            return GenerateResponse(**result)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except Exception as e:
            logger.exception("Generation failed")
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.get("/v1/stats")
    async def stats(model: Optional[str] = None):
        """
        Get performance statistics.
        
        - No query param: returns stats for all loaded models + server status
        - `?model=default`: returns stats for a specific model
        """
        try:
            model_stats = await manager.get_stats(model)
            server_status = await manager.get_server_status()
            return {
                "models": model_stats if isinstance(model_stats, dict) else {model: model_stats},
                "server": server_status,
            }
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
    
    @app.get("/v1/models", response_model=list[ModelStatus])
    async def list_models():
        """List all loaded models."""
        return await manager.list_models()

    @app.get("/v1/hardware")
    async def hardware():
        """
        GPU info (total VRAM) via nvidia-smi — lets the Console suggest a
        quant that FITS before anything is loaded (the load dialog needs
        headroom; per-model stats only exist once a model runs).

        Returns ``{"gpu": null, "source": "nvidia-smi"}`` when nvidia-smi
        is unavailable — honest, never a fake number. Blocking subprocess
        runs in a worker thread (never the event loop).
        """
        def _probe() -> dict:
            import subprocess
            try:
                out = subprocess.run(
                    ["nvidia-smi", "--query-gpu=name,memory.total",
                     "--format=csv,noheader"],
                    capture_output=True, text=True, timeout=10,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                ).stdout or ""
                for line in out.splitlines():
                    name, _, total = line.partition(",")
                    total = total.strip()
                    if total.endswith("MiB"):
                        try:
                            return {
                                "gpu": {
                                    "name": name.strip(),
                                    "total_vram_mb": int(float(total[:-3])),
                                },
                                "source": "nvidia-smi",
                            }
                        except ValueError:
                            pass
            except Exception:
                pass
            return {"gpu": None, "source": "nvidia-smi"}

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _probe)
    
    def _run_browse_dialog(mode: str = "file") -> dict:
        """Run native browse dialog via helper script (subprocess)."""
        import subprocess, sys, os
        helper = os.path.join(os.path.dirname(__file__), "browse_dialog.py")
        try:
            # CREATE_NEW_CONSOLE helps dialog stay visible on Windows
            creationflags = 0
            if sys.platform == "win32":
                creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            result = subprocess.run(
                [sys.executable, helper, mode],
                capture_output=True,
                text=True,
                timeout=120,
                creationflags=creationflags,
            )
            lines = (result.stdout or "").strip().splitlines()
            path = lines[-1].strip() if lines else ""
            if result.returncode == 0 and path:
                if mode == "dir" and os.path.isdir(path):
                    return {"path": os.path.abspath(path)}
                if mode == "file" and os.path.isfile(path):
                    size = os.path.getsize(path)
                    return {
                        "path": os.path.abspath(path),
                        "name": os.path.basename(path),
                        "size_gb": round(size / (1024**3), 2),
                    }
            if result.returncode == 1:
                return {"path": None, "cancelled": True}
            err = (result.stderr or "").strip() or f"exit code {result.returncode}"
            return {"path": None, "error": err}
        except subprocess.TimeoutExpired:
            return {"path": None, "error": "Dialog timed out (no selection within 2 minutes)"}
        except Exception as e:
            return {"path": None, "error": str(e)}
    
    @app.get("/v1/browse")
    async def browse_model():
        """
        Open a native file dialog on the server to pick a .gguf model.
        Works because server and browser run on the same machine.
        Look for the dialog in the taskbar if it doesn't appear on top.
        """
        return await asyncio.get_running_loop().run_in_executor(
            None, lambda: _run_browse_dialog("file")
        )
    
    @app.get("/v1/browse-dir")
    async def browse_directory():
        """Open a native directory picker to select a folder to scan."""
        return await asyncio.get_running_loop().run_in_executor(
            None, lambda: _run_browse_dialog("dir")
        )
    
    @app.get("/v1/models/scan")
    async def scan_models(dir: str | None = None):
        """
        Scan directories for available GGUF model files.

        Scans the configured models directory (WS_MODELS_DIR env var,
        default: current directory + common model locations).
        Returns a list of found .gguf files with size info.

        The recursive glob + GGUF header parsing is blocking I/O that can
        take minutes on large model stores, so it runs in a worker thread
        (never on the event loop — a blocked loop freezes /health, stats,
        and every in-flight generation).
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _scan_gguf_models, dir)

    def _scan_gguf_models(dir: str | None = None) -> dict:
        import os, glob

        # Default search paths come from the shared helper so /v1/config and
        # the Hub download target_dir guard agree on legitimate model folders.
        search_dirs = [dir] if dir else get_model_search_dirs()

        found = []
        seen = set()
        for search_dir in search_dirs:
            if not os.path.isdir(search_dir):
                continue
            # Recursive scan: **/*.gguf to find models in subfolders
            # (e.g., Jan Desktop stores models in models/model-name/model.gguf)
            pattern = os.path.join(search_dir, "**", "*.gguf")
            for path in sorted(glob.glob(pattern, recursive=True)):
                abspath = os.path.abspath(path)
                if abspath in seen:
                    continue
                seen.add(abspath)
                try:
                    size = os.path.getsize(abspath)
                    arch = "unknown"
                    quant = None
                    try:
                        from gguf import GGUFReader
                        reader = GGUFReader(abspath)
                        field = reader.fields.get("general.architecture")
                        if field is not None:
                            data = field.parts[-1]
                            if isinstance(data, (bytes, bytearray)):
                                arch = bytes(data).decode("utf-8", errors="replace").strip("\x00")
                            elif hasattr(data, "tobytes"):
                                arch = data.tobytes().decode("utf-8", errors="replace").strip("\x00")
                            else:
                                arch = str(data)
                        # Effective quantization = dominant non-F32 tensor
                        # type (authoritative over general.file_type, whose
                        # label can be stale/custom-converter-wrong).
                        # Python ≥3.11 str(IntEnum) is the bare integer, so
                        # use the enum's .name ("Q2_K", "F16", …).
                        counts: dict = {}
                        for t in reader.tensors:
                            tt = t.tensor_type
                            key = getattr(tt, "name", None) or str(tt).split(".")[-1]
                            if key == "F32":
                                continue
                            counts[key] = counts.get(key, 0) + 1
                        if counts:
                            quant = max(counts.items(), key=lambda kv: kv[1])[0]
                    except Exception:
                        pass
                    # Architectures that needed newer llama-cpp in older
                    # installs. "qwen35" was verified working on the pinned
                    # llama-cpp-python 0.3.34 (live generation + user report,
                    # 2026-07-30) and removed. Remaining entries are kept
                    # conservatively until each arch is re-verified.
                    needs_upgrade = arch in (
                        "qwen35moe", "qwen3", "qwen3moe",
                        "deepseek2", "deepseek3",
                    )
                    found.append({
                        "path": abspath,
                        "name": os.path.basename(abspath),
                        "size_bytes": size,
                        "size_gb": round(size / (1024**3), 2),
                        "directory": os.path.dirname(abspath),
                        "architecture": arch,
                        "quant": quant,
                        "may_need_upgrade": needs_upgrade,
                    })
                except OSError:
                    pass
        
        return {"models": found, "total": len(found)}
    
    @app.post("/v1/models/load", response_model=ModelActionResponse)
    async def load_model(request: ModelLoadRequest):
        """
        Load a model into the server.
        
        The model becomes available for generation at its model_id.
        """
        try:
            if request.force and request.model_id in manager._models:
                await manager.unload(request.model_id)
            
            result = await manager.load(
                model_id=request.model_id,
                model_path=request.model_path,
                buffer_mb=request.buffer_mb,
                n_ctx=request.n_ctx,
                n_threads=request.n_threads,
                gpu_layers=request.gpu_layers,
                kv_cache_type=request.kv_cache_type,
                # llama-server extra args (e.g. MTP draft flags). The schema
                # field was missing until now — the endpoint silently
                # dropped it, which wasted a whole EXP-023 penalty matrix on
                # flags that never reached the subprocess.
                extra_args=request.extra_args,
            )
            return ModelActionResponse(
                status="loaded",
                model_id=request.model_id,
                message=f"Model loaded: {request.model_path}",
            )
        except ValueError as e:
            raise HTTPException(status_code=409, detail=str(e))
        except Exception as e:
            logger.exception("Model load failed")
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.post("/v1/models/unload", response_model=ModelActionResponse)
    async def unload_model(request: ModelUnloadRequest):
        """Unload a model from the server."""
        try:
            await manager.unload(request.model_id)
            return ModelActionResponse(
                status="unloaded",
                model_id=request.model_id,
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    # ── WebSocket Endpoint ──────────────────────────────────────────
    
    @app.websocket("/v1/stream")
    async def ws_generate(websocket: WebSocket):
        """
        Generate text over WebSocket with token-by-token streaming.
        
        Protocol:
            Client → Server: {"type": "generate", "model": "...", "prompt": "...", "max_tokens": 100}
            Server → Client: {"type": "token", "text": "...", "index": 0}
            Server → Client: {"type": "token", "text": "...", "index": 1}
            ...
            Server → Client: {"type": "done", "stats": {...}}
            
        Client disconnects to cancel in-progress generation.
        """
        await websocket.accept()
        cancelled = False
        
        try:
            data = await websocket.receive_json()
            
            if data.get("type") != "generate":
                await websocket.send_json({
                    "type": "error",
                    "message": "First message must be type=generate",
                    "code": "BAD_REQUEST",
                })
                return
            
            model_id = data.get("model", "default")
            prompt = data.get("prompt", "")
            max_tokens = data.get("max_tokens", 128)
            temperature = data.get("temperature", 0.7)
            top_p = data.get("top_p", 0.9)
            
            if not prompt:
                await websocket.send_json({
                    "type": "error",
                    "message": "Missing 'prompt' field",
                    "code": "BAD_REQUEST",
                })
                return
            
            gen = manager.generate_stream(
                model_id=model_id,
                prompt=prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=top_p,
            )
            
            async for event in gen:
                if cancelled:
                    break
                if event.get("done"):
                    await websocket.send_json({
                        "type": "done",
                        "stats": event.get("stats", {}),
                    })
                else:
                    await websocket.send_json({
                        "type": "token",
                        "text": event["token"],
                        "index": event["index"],
                    })
        
        except WebSocketDisconnect:
            cancelled = True
        except ValueError as e:
            try:
                await websocket.send_json({
                    "type": "error",
                    "message": str(e),
                    "code": "MODEL_NOT_FOUND",
                })
            except WebSocketDisconnect:
                pass
        except Exception as e:
            logger.exception("WebSocket generation failed")
            try:
                await websocket.send_json({
                    "type": "error",
                    "message": str(e),
                    "code": "GENERATION_ERROR",
                })
            except WebSocketDisconnect:
                pass
    
    # ── OpenAI-Compatible Endpoint ──────────────────────────────────
    
    @app.post("/v1/chat/completions")
    async def chat_completions(request: ChatCompletionRequest):
        """
        OpenAI-compatible chat completions endpoint.
        
        Compatible with any OpenAI SDK, VS Code Continue.dev, Cline, etc.
        
        Set `OPENAI_BASE_URL=http://localhost:8765/v1` and use
        any `model_id` as the model name.
        """
        try:
            return await handle_chat_completion(request, manager)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except Exception as e:
            logger.exception("Chat completion failed")
            raise HTTPException(status_code=500, detail=str(e))
    
    # ── Anthropic-Compatible Endpoint ──────────────────────────────
    
    @app.post("/v1/messages")
    async def anthropic_messages(request: Request):
        """
        Anthropic-compatible Messages API endpoint.
        
        Compatible with Claude Code, Anthropic SDK, and any Anthropic-compatible client.
        
        Set `ANTHROPIC_BASE_URL=http://localhost:8765/v1` and use
        any `model_id` as the model name.
        """
        try:
            return await handle_anthropic_messages(request, manager)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except Exception as e:
            logger.exception("Anthropic message failed")
            raise HTTPException(status_code=500, detail=str(e))    # ── Issue Tracking ──────────────────────────────────────────────

    def _tiering_debug_summary() -> Optional[dict]:
        """Compact auto-tiering snapshot for issue reports: enabled flag +
        route totals (aggregated per tier/reason — no per-event detail, so
        the report stays small and contains no prompts). Honest: None when
        anything fails (a report must never break because of telemetry)."""
        try:
            cfg = tiering.load_config()
            urec = getattr(app.state, "usage_recorder", None)
            events = urec.history(kind="tier_route") if urec is not None else []
            by_tier: dict[str, int] = {}
            by_reason: dict[str, int] = {}
            for e in events:
                k = str(e.get("tier", "?"))
                by_tier[k] = by_tier.get(k, 0) + 1
                r = str(e.get("reason", "?"))
                by_reason[r] = by_reason.get(r, 0) + 1
            return {
                "enabled": cfg.get("enabled", False),
                "total_routes": len(events),
                "by_tier": by_tier,
                "by_reason": by_reason,
            }
        except Exception:
            return None

    @app.get("/v1/debug/context")
    async def debug_context(
        model_path: str | None = None,
        last_error: str | None = None,
        last_endpoint: str | None = None,
    ):
        """Collect privacy-safe debug context for issue reports."""
        arch = None
        models = await manager.list_models()
        if models:
            model_path = model_path or models[0].path
            arch = models[0].arch
        return collect_debug_context(
            model_path=model_path,
            model_architecture=arch,
            last_error=last_error,
            last_endpoint=last_endpoint,
            log_tail=list(recent_errors[-50:]),
            tiering=_tiering_debug_summary(),
        )
    
    @app.post("/v1/issues")
    async def create_issue(body: IssueCreate):
        """Create a new issue report."""
        try:
            # Merge server debug context if client context incomplete
            if not body.context.get("app_version"):
                body.context = {
                    **collect_debug_context(
                        log_tail=list(recent_errors[-50:]),
                        tiering=_tiering_debug_summary(),
                    ),
                    **(body.context or {}),
                }
            issue = issue_service.create(body)
            return issue.model_dump()
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))
    
    @app.get("/v1/issues")
    async def list_issues(status: str | None = None, severity: str | None = None):
        """List issues, optionally filtered by status/severity."""
        try:
            issues = issue_service.list(status=status, severity=severity)
            return [i.model_dump() for i in issues]
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    
    @app.get("/v1/issues/export")
    async def export_issues(format: str = "md"):
        """Export issues summary (md or json)."""
        if format == "json":
            issues = issue_service.list()
            return [i.model_dump() for i in issues]
        md = issue_service.export_markdown()
        from fastapi.responses import PlainTextResponse
        return PlainTextResponse(md, media_type="text/markdown")
    
    @app.get("/v1/issues/{issue_id}")
    async def get_issue(issue_id: str):
        """Get a single issue by ID."""
        issue = issue_service.get(issue_id)
        if not issue:
            raise HTTPException(status_code=404, detail=f"Issue {issue_id} not found")
        return issue.model_dump()
    
    @app.patch("/v1/issues/{issue_id}")
    async def update_issue(issue_id: str, body: IssueUpdate):
        """Update issue fields/status (maintainer)."""
        try:
            issue = issue_service.update(issue_id, body)
            return issue.model_dump()
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    
    @app.post("/v1/issues/{issue_id}/verify")
    async def verify_issue(issue_id: str, body: IssueVerify):
        """User verification of a fix."""
        try:
            issue = issue_service.verify(issue_id, body)
            return issue.model_dump()
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    # ── Hub (P4): Hugging Face GGUF search + download ───────────────
    # Backend-only in P4; the Hub UI page consumes these in P5. Security:
    # the server has no auth + CORS "*", so downloads are confined to the
    # model dirs, written atomically, and size-guarded (see server/hub.py).

    @app.get("/v1/hub/search")
    async def hub_search(
        q: str = "",
        sort: str = "downloads",
        limit: int = 20,
        cursor: str | None = None,
        paginate: int = 0,
    ):
        """
        Search Hugging Face for GGUF models (filtered to GGUF only), with
        quant + parameter-size parsed from each file's name. Results are
        cached in-memory for 5 minutes. HF unreachable → 502 (never a fake
        list). `sort` ∈ downloads|likes|recent.

        Optional cursor pagination for the Hub "Latest" feed: pass
        `paginate=1` (and optionally `cursor` for a page after the first) to
        also receive `next_cursor` in the response, threaded through the real
        HF `Link: rel="next"` header. The plain single-page path is unchanged.
        """
        try:
            if paginate:
                page = hub_manager.search_with_cursor(q=q, sort=sort, limit=limit, cursor=cursor)
                results = page["results"]
                return {
                    "results": results,
                    "count": len(results),
                    "next_cursor": page["next_cursor"],
                }
            results = hub_manager.search(q=q, sort=sort, limit=limit)
            return {"results": results, "count": len(results), "next_cursor": None}
        except HubUpstreamError as e:
            raise HTTPException(status_code=502, detail=str(e))

    @app.get("/v1/hub/recommended")
    async def hub_recommended():
        """Curated models proven on this reference rig (server/recommended.py).

        Static data — no network call. Every entry is backed by a measured
        experiment (``research/experiments/``) with the Thai quality gate, and
        carries the EXACT download files that were measured so users fetch the
        right quant. See the module docstring for the honest caveat (numbers
        are from this machine; other hardware will differ).
        """
        return recommended_payload()

    @app.get("/v1/research/experiment/{exp_path:path}")
    async def research_experiment(exp_path: str):
        """Serve one experiment's markdown record for the in-app Evidence
        viewer (research/experiments/). Path validated by containment — no
        traversal, only ``*.md`` files ever read (server/research.py).
        """
        try:
            return read_experiment(exp_path)
        except ResearchValidationError as e:
            raise HTTPException(status_code=e.status, detail=str(e))

    @app.get("/v1/hub/model/{repo_id:path}")
    async def hub_model(repo_id: str):
        """
        On-demand model detail (P5.1): aggregate HF model metadata + per-file
        byte sizes + shard/quant grouping for one repo. Cached ~15 min. HF
        unreachable → 502 (never a fake/empty 200). Fields HF omits are null.
        """
        try:
            return hub_manager.model_detail(repo_id)
        except HubValidationError as e:
            raise HTTPException(status_code=e.status, detail=str(e))
        except HubUpstreamError as e:
            raise HTTPException(status_code=502, detail=str(e))

    @app.post("/v1/hub/download", status_code=202)
    async def hub_download(body: HubDownloadRequest):
        """
        Start a background GGUF download and return the task (poll
        `/v1/hub/progress/{id}` or `/v1/hub/downloads`).

        Security: `target_dir` must resolve inside an allowed model dir
        (traversal / absolute-outside / symlink-escape → 403); `filename`
        must be a plain `*.gguf` name (else 400). Writes are atomic
        (`.part` → rename) and size-guarded. No auth in v1 — isolate the
        server (see API Docs note, P5).
        """
        try:
            task = hub_manager.create_download(body.repo_id, body.filename, body.target_dir)
        except HubValidationError as e:
            raise HTTPException(status_code=e.status, detail=str(e))
        hub_manager.schedule_download(task)
        return task.to_dict()

    @app.get("/v1/hub/downloads")
    async def hub_downloads():
        """List all download tasks with their latest status/progress."""
        items = hub_manager.list_tasks()
        return {"downloads": items, "count": len(items)}

    @app.get("/v1/hub/progress/{task_id}")
    async def hub_progress(task_id: str):
        """
        SSE stream of a download's REAL progress (bytes/percent/speed_bps/
        eta_s/status) until it reaches a terminal state (done/failed/cancelled).
        """
        task = hub_manager.get_task(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail=f"download task {task_id} not found")

        async def event_generator():
            while True:
                yield f"data: {json.dumps(task.to_dict(), ensure_ascii=False)}\n\n"
                if task.status in ("done", "failed", "cancelled"):
                    break
                await asyncio.sleep(0.5)

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "X-Accel-Buffering": "no",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            },
        )

    @app.post("/v1/hub/download/{task_id}/cancel")
    async def hub_cancel(task_id: str):
        """
        Cancel a download. Sets the cancel flag; the worker stops within one
        chunk and the partial ``.part`` is KEPT so the task can be resumed.
        Idempotent for already-terminal tasks.
        """
        task = hub_manager.cancel(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail=f"download task {task_id} not found")
        return task.to_dict()

    @app.post("/v1/hub/download/{task_id}/resume")
    async def hub_resume(task_id: str):
        """
        Resume a cancelled/failed download (v1.1): re-queues the task; the
        worker appends the remaining bytes to the kept ``.part`` via HTTP
        ``Range`` instead of re-downloading from byte 0. 404 unknown task;
        409 when the task is not resumable (active or done).
        """
        try:
            task = hub_manager.resume(task_id)
        except ValueError as e:
            raise HTTPException(status_code=409, detail=str(e))
        if task is None:
            raise HTTPException(status_code=404, detail=f"download task {task_id} not found")
        hub_manager.schedule_download(task)
        return task.to_dict()

    @app.post("/v1/hub/download/{task_id}/delete")
    async def hub_delete(task_id: str, body: Optional[HubDeleteRequest] = None):
        """
        Delete a download task from the manager (v1.1): stops a running
        worker and removes the partial ``.part``. By default the final
        ``.gguf`` of a completed task is left on disk; pass
        ``{"delete_file": true}`` to ALSO delete the model file (only for
        ``done`` tasks whose file is inside an allowed model dir and whose
        model is not currently loaded). Returns ``file_deleted`` honestly.
        """
        delete_file = bool(body and body.delete_file)
        task = hub_manager.get_task(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail=f"download task {task_id} not found")
        if delete_file:
            if task.status != "done":
                raise HTTPException(
                    status_code=409,
                    detail="only a completed download has a model file to delete",
                )
            # never delete a model that a backend is holding open — removing
            # it would break the running session (checked BEFORE the delete).
            # Compare NORMALIZED paths (realpath + case-fold) so a model
            # loaded through a different spelling/symlink still matches.
            target_real = os.path.normcase(os.path.realpath(task.target_path))
            loaded = await manager.list_models()
            if any(
                os.path.normcase(os.path.realpath(getattr(m, "path", "") or "")) == target_real
                for m in loaded
            ):
                raise HTTPException(
                    status_code=409,
                    detail="this model is currently loaded — unload it before deleting the file",
                )
        hub_manager.delete(task_id, delete_file=delete_file)
        file_deleted = delete_file and not os.path.exists(task.target_path)
        # which features reference this model's suggested id (conversations
        # live client-side, so the server reports assistants only — the UI
        # counts conversations itself). Honest at delete time: a reference
        # created in another tab after the dialog opened is still reported.
        # Only scanned when a file is actually at risk (delete_file) — the
        # keep-file path never reads the assistant store.
        refs = _assistants_referencing(task.filename) if delete_file else []
        return {
            "status": "deleted",
            "id": task.id,
            "file_deleted": file_deleted,
            "referenced_by": {"assistants": refs},
        }

    @app.post("/v1/hub/downloads/clear")
    async def hub_clear(body: Optional[HubClearRequest] = None):
        """
        Remove every FINISHED download (done/failed/cancelled) at once
        (v1.1): the panel's "clear finished" action. Active downloads are
        kept. Pass ``{"delete_file": true}`` to ALSO delete the model files
        of completed downloads — except those of currently loaded models,
        which are skipped and reported in ``files_skipped`` (never removed
        under a running backend). Returns the honest summary.
        """
        delete_file = bool(body and body.delete_file)
        protected: set = set()
        if delete_file:
            # same normalized-path rule as the single-task delete endpoint
            loaded = await manager.list_models()
            protected = {
                os.path.normcase(os.path.realpath(getattr(m, "path", "") or ""))
                for m in loaded
            }
        # snapshot the DONE tasks' filenames BEFORE the clear so the response
        # can map task id → assistant references (the tasks are popped inside
        # clear(); their filenames would otherwise be gone).
        done_files = {
            t["id"]: t["filename"]
            for t in hub_manager.list_tasks()
            if t.get("status") == "done"
        }
        result = hub_manager.clear(delete_file=delete_file, protected_paths=protected)
        if delete_file and done_files:
            # ONE store read for the whole batch, then task_id → references
            # for every done task the clear removed (conversations live
            # client-side, so only assistants are reported). A task that
            # finished between the snapshot and the clear simply has no
            # entry — advisory only, never blocks.
            refs_by_file = _assistant_refs_batch(list(done_files.values()))
            result["referenced_by"] = {
                tid: {"assistants": refs_by_file.get(fname, [])}
                for tid, fname in done_files.items()
                if tid in result.get("removed", [])
            }
        return result

    @app.post("/v1/hub/download/{task_id}/reveal")
    async def hub_reveal(task_id: str):
        """
        Open the OS file manager showing a COMPLETED download's file (v1.1).

        The server and the browser run on the same machine, so this launches
        Explorer/Finder via a subprocess (Windows ``/select`` highlights the
        file; macOS ``open -R``; Linux opens the folder). Security: only
        tasks that finished with their file on disk, and the file must
        realpath-resolve inside an allowed model dir (same containment rule
        as delete) — revealing an arbitrary path is refused.
        """
        task = hub_manager.get_task(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail=f"download task {task_id} not found")
        if task.status != "done" or not os.path.isfile(task.target_path):
            raise HTTPException(
                status_code=409,
                detail="only a completed download whose file is still on disk can be revealed",
            )
        real = os.path.realpath(task.target_path)
        allowed = [os.path.realpath(d) for d in get_model_search_dirs()]
        if not any(real == ra or real.startswith(ra + os.sep) for ra in allowed):
            raise HTTPException(
                status_code=403,
                detail="refusing to reveal a file outside the allowed model directories",
            )
        res = _reveal_in_explorer(real)
        if res.get("error"):
            raise HTTPException(status_code=500, detail=res["error"])
        return {"status": "revealed", "path": real}

    # ── Assistants (P7.2): named chat personas (system prompt + model + params)
    from .assistants import get_assistant_store

    _astore = get_assistant_store()

    @app.get("/v1/assistants")
    async def list_assistants():
        """List all assistants."""
        return _astore.list()

    @app.get("/v1/assistants/{assistant_id}")
    async def get_assistant(assistant_id: str):
        """Get a single assistant."""
        a = _astore.get(assistant_id)
        if not a:
            raise HTTPException(status_code=404, detail=f"Assistant {assistant_id} not found")
        return a

    @app.post("/v1/assistants", status_code=201)
    async def create_assistant(body: AssistantCreate):
        """Create a new assistant."""
        return _astore.create(
            name=body.name,
            system_prompt=body.system_prompt,
            description=body.description,
            model_id=body.model_id,
            params=body.params,
        )

    @app.patch("/v1/assistants/{assistant_id}")
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

    @app.delete("/v1/assistants/{assistant_id}")
    async def delete_assistant(assistant_id: str):
        """Delete an assistant."""
        if not _astore.delete(assistant_id):
            raise HTTPException(status_code=404, detail=f"Assistant {assistant_id} not found")
        return {"status": "deleted", "id": assistant_id}

    # ── MCP (P7.4): manage MCP servers + list/call tools ───────────────
    from .mcp_host import get_mcp_store, get_mcp_host, validate_mcp_server
    from .schemas import MCPServerCreate

    _mcpstore = get_mcp_store()
    _mcp = get_mcp_host()

    @app.get("/v1/mcp/servers")
    async def list_mcp_servers():
        """List configured MCP servers."""
        return _mcpstore.list()

    @app.post("/v1/mcp/servers", status_code=201)
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

    @app.delete("/v1/mcp/servers/{server_id}")
    async def delete_mcp_server(server_id: str):
        """Delete an MCP server config."""
        if not _mcpstore.delete(server_id):
            raise HTTPException(status_code=404, detail=f"MCP server {server_id} not found")
        return {"status": "deleted", "id": server_id}

    @app.get("/v1/mcp/tools")
    async def list_mcp_tools(server_id: str | None = None):
        """List tools from enabled MCP servers (connects to servers)."""
        try:
            tools = await _mcp.list_tools(server_id)
            return tools
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    @app.post("/v1/mcp/tools/{server_id}/{tool_name}/call")
    async def call_mcp_tool(server_id: str, tool_name: str, body: Dict[str, Any]):
        """Call a tool on an MCP server."""
        try:
            result = await _mcp.call_tool(server_id, tool_name, body)
            return {"server_id": server_id, "tool": tool_name, "result": result}
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    # ── Auto-tiering (P8): fast/quality pair + pure router ─────────────
    # User-configurable model pair (default = the Gemma pair proven on this
    # rig, EXP-022/019). The router itself is model-agnostic — any two GGUFs
    # work; see server/tiering.py for the decision rule.
    from . import tiering

    app.state.tiering_manager = manager

    @app.get("/v1/tiering/config")
    async def get_tiering_config():
        """Current auto-tiering config + on-disk resolution per tier (so a
        broken pair is visible, not silent)."""
        cfg = tiering.resolve_state(tiering.load_config())
        problems = tiering.validate_config(cfg)
        return {"config": cfg, "problems": problems}

    @app.put("/v1/tiering/config")
    async def put_tiering_config(body: Dict[str, Any]):
        """Validate + persist a new tiering config (data/tiering.json).
        Returns the normalized config; 400 with readable problems when
        invalid (e.g. missing model file)."""
        try:
            saved = tiering.save_config(body)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        return {"status": "saved", "config": tiering.resolve_state(saved)}

    @app.post("/v1/tiering/route")
    async def route_tiering(body: Dict[str, Any]):
        """Route a request to fast or quality tier and load that model.

        Body: ``{"messages": [...], "options": {reasoning_mode/effort}}``.
        Returns ``{tier, model_id, model_path, reason}``. When the config is
        disabled the call is refused (409) — the caller should fall back to
        its own model choice instead of silently routing.

        Reuse-first: when the tier's file is ALREADY loaded (even under a
        different model_id — e.g. the user loaded it manually), the route
        reuses it instead of evicting + reloading the same file, and reports
        the EFFECTIVE loaded model_id (``reused: true``) so the caller can
        generate against it immediately. Each successful route is recorded
        into the usage history as a ``tier_route`` event (real telemetry;
        a recorder hiccup never breaks routing).
        """
        cfg = tiering.load_config()
        if not cfg.get("enabled", False):
            raise HTTPException(
                status_code=409,
                detail="auto-tiering is disabled — fall back to an explicit model",
            )
        messages = body.get("messages") or []
        options = body.get("options") or {}
        tier, reason = tiering.decide_tier(cfg, messages, options)
        entry = cfg[tier]
        tmanager = getattr(app.state, "tiering_manager", manager)
        find = getattr(tmanager, "find_loaded_path", None)
        reused_id: Optional[str] = None
        if callable(find):
            try:
                reused_id = find(entry["model_path"])
            except Exception:
                reused_id = None
        effective_id = reused_id or entry["model_id"]
        if reused_id is None:
            # n_ctx comes from the tier config (default 8192 — the
            # server-wide 2048 would cap output at ~1950 tokens and
            # truncate long answers mid-thought, EXP-023). Only pass it
            # when set: load() pops n_ctx without coalescing None.
            load_kwargs: dict = {
                "extra_args": entry.get("extra_args"),
                "n_threads": entry.get("n_threads"),
            }
            if entry.get("n_ctx"):
                load_kwargs["n_ctx"] = int(entry["n_ctx"])
            try:
                await tmanager.load_or_get(
                    model_id=entry["model_id"],
                    model_path=entry["model_path"],
                    **load_kwargs,
                )
            except Exception as e:
                raise HTTPException(
                    status_code=500,
                    detail=f"tier '{tier}' model failed to load: {e}",
                )
        urec = getattr(app.state, "usage_recorder", None)
        if urec is not None:
            try:
                urec.record_event(
                    "tier_route",
                    tier=tier,
                    reason=reason,
                    model_id=effective_id,
                    model_path=entry["model_path"],
                    prompt_chars=len(tiering.prompt_text(messages)),
                    reused=bool(reused_id),
                )
            except Exception:
                pass  # telemetry must never break routing
        return {
            "tier": tier,
            "model_id": effective_id,
            "model_path": entry["model_path"],
            "reason": reason,
            "reused": reused_id is not None,
            # Per-tier output budget (EXP-023): callers clamp their request's
            # max_tokens to this — the fast tier is for quick answers and
            # must not burn the full budget on a degenerate loop.
            "max_tokens": entry.get("max_tokens"),
        }

    @app.post("/v1/tiering/preview")
    async def preview_tiering(body: Dict[str, Any]):
        """Preview the routing decision WITHOUT loading any model — uses the
        LIVE config, so the answer is always real, never stale.

        Body (same shape as /v1/tiering/route): ``{"messages": [...],
        "options": {reasoning_mode/effort}}``. Returns ``{tier, reason,
        model_id, model_path}`` — what WOULD run, not what ran. 409 when
        the config is disabled (the caller can fall back to its own choice).
        """
        cfg = tiering.load_config()
        if not cfg.get("enabled", False):
            raise HTTPException(
                status_code=409,
                detail="auto-tiering is disabled — fall back to an explicit model",
            )
        messages = body.get("messages") or []
        options = body.get("options") or {}
        tier, reason = tiering.decide_tier(cfg, messages, options)
        entry = cfg[tier]
        return {
            "tier": tier,
            "reason": reason,
            "model_id": entry["model_id"],
            "model_path": entry["model_path"],
        }

    @app.post("/v1/tiering/unpin")
    async def unpin_tiering(body: Dict[str, Any]):
        """Restore one tier to the shipped default (undo a user pin).

        Body: ``{"tier": "fast"|"quality"}``. Only that tier changes — the
        other tier and the enabled/threshold settings are untouched. 400 for
        an invalid tier name.
        """
        try:
            saved = tiering.unpin_tier(str(body.get("tier", "")))
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        return {"status": "saved", "config": tiering.resolve_state(saved)}

    @app.get("/v1/tiering/stats")
    async def tiering_stats(limit: int = 100):
        """Auto-tiering routing statistics — real telemetry from the usage
        history ``tier_route`` events (never fabricated).

        Returns the enabled flag (from config), totals per tier/reason/model,
        and the newest events (capped by ``limit``, latest 10 in ``recent``).
        A fresh install has ``total_routes: 0`` — an honest empty, not a lie.
        """
        cfg = tiering.load_config()
        urec = getattr(app.state, "usage_recorder", None)
        events = (urec.history(kind="tier_route") if urec is not None else [])
        recent = events[-limit:] if limit and limit > 0 else events
        by_tier: dict[str, int] = {}
        by_reason: dict[str, int] = {}
        by_model: dict[str, int] = {}
        for e in events:
            k = str(e.get("tier", "?"))
            by_tier[k] = by_tier.get(k, 0) + 1
            k2 = str(e.get("reason", "?"))
            by_reason[k2] = by_reason.get(k2, 0) + 1
            k3 = str(e.get("model_id", "?"))
            by_model[k3] = by_model.get(k3, 0) + 1
        return {
            "enabled": cfg.get("enabled", False),
            "total_routes": len(events),
            "by_tier": by_tier,
            "by_reason": by_reason,
            "by_model": by_model,
            "recent": events[-10:],
            "count": len(recent),
        }

    @app.post("/v1/tiering/pin")
    async def pin_tiering(body: Dict[str, Any]):
        """Pin a tier from exact file names (Hub recommended list → disk).

        Body: ``{"tier": "fast"|"quality", "files": ["main.gguf", ...]}``.
        Resolves the files under the model search dirs (no full scan), wires
        MTP draft flags when a sibling draft file is present, saves, and
        returns the updated config. 400 with a readable message when a file
        is not on disk or the tier is invalid.
        """
        try:
            saved = tiering.pin_tier(
                str(body.get("tier", "")),
                [str(f) for f in (body.get("files") or [])],
                get_model_search_dirs(),
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        return {"status": "saved", "config": tiering.resolve_state(saved)}

    # ── Conversation summarization (context-management POC) ─────────────
    # New feature (research/12): running summary injected into the system
    # prompt keeps long chats working with a small context. No conflict
    # with Chat Agent Tools (workspace access) — separate routes.
    @app.post("/v1/conversation/summarize",
              response_model=ConversationSummarizeResponse)
    async def summarize_conversation(
        request: ConversationSummarizeRequest,
    ):
        """Summarize a conversation; returns a running summary the caller
        can inject into the system prompt."""
        from .conversation_summary import ConversationSummarizer, estimate_tokens

        messages = [{"role": m.role, "content": m.content}
                    for m in request.messages]
        svc = ConversationSummarizer(manager)
        summary = await svc.summarize(
            messages=messages,
            model_id=request.model,
            existing_summary=request.existing_summary,
        )
        return ConversationSummarizeResponse(
            summary=summary,
            input_tokens_estimate=estimate_tokens(messages),
            summary_tokens_estimate=estimate_tokens(
                [{"role": "user", "content": summary}]
            ),
            model=request.model,
        )

    return app, manager


# ── Default Application Instance ──────────────────────────────────
app, manager = create_app()


# ── Helpers ──────────────────────────────────────────────────────────


async def _stream_generate(
    request: GenerateRequest,
    manager: ModelManager,
) -> StreamingResponse:
    """Handle streaming generation via SSE."""
    async def event_generator():
        try:
            gen = manager.generate_stream(
                model_id=request.model,
                prompt=request.prompt,
                max_tokens=request.max_tokens,
                temperature=request.temperature,
                top_p=request.top_p,
            )
            async for event in gen:
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except ValueError as e:
            yield f"data: {json.dumps({'error': str(e), 'code': 'MODEL_NOT_FOUND'})}\n\n"
        except Exception as e:
            logger.exception("Stream generation failed")
            yield f"data: {json.dumps({'error': str(e), 'code': 'GENERATION_ERROR'})}\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "X-Accel-Buffering": "no",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )

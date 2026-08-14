"""System routes: health, config, usage history, logs, stats, hardware."""
from __future__ import annotations

import asyncio
import os
from typing import Any, Optional

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.responses import JSONResponse

from ..config import (
    get_model_search_dirs,
    describe_config,
    CONFIG_ENV_KEYS,
)
from ..logs import DEFAULT_TAIL_LINES
from .context import ServerContext


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


def build_router(app: FastAPI, ctx: ServerContext) -> APIRouter:
    """Register system routes. ``app`` is only used for version wiring."""
    from weight_stream import __version__  # lazy: avoid circular import

    router = APIRouter()

    # Health check
    @router.get("/health")
    async def health():
        return {"status": "ok", "version": __version__}

    # Root → Console (primary UI since P6 promote; legacy at /app-legacy)
    @router.get("/")
    async def root():
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url="/console/", status_code=302)

    # API info (for developers / health dashboards)
    @router.get("/api")
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

    @router.get("/v1/config")
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
            "config": describe_config(ctx.manager._cfg),
            "models_dirs": get_model_search_dirs(),
            "issues_dir": str(ctx.issue_service.store.base)
            if ctx.issue_service else None,
            "version": __version__,
        }

    @router.patch("/v1/config")
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

        overrides = set(getattr(ctx.manager._cfg, "_runtime_overrides", set()))
        applied: dict[str, dict] = {}
        notes: dict[str, str] = {}
        for key, val in coerced.items():
            setattr(ctx.manager._cfg, key, val)
            overrides.add(key)
            applied[key] = {"value": val, "source": "runtime"}
            if key in _CONFIG_GATED_KEYS:
                notes[key] = "applies to models loaded after this change"
        ctx.manager._cfg._runtime_overrides = overrides  # type: ignore[attr-defined]

        return {
            "status": "applied",
            "applied": applied,
            "notes": notes,
            "config": describe_config(ctx.manager._cfg),
        }

    @router.get("/v1/usage/history")
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
        records = ctx.manager.usage_history(limit=limit, since=since)
        return {
            "history": records,
            "count": len(records),
            "capacity": ctx.manager.usage_capacity(),
        }

    @router.get("/v1/logs/tail")
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

    @router.get("/v1/stats")
    async def stats(model: Optional[str] = None):
        """
        Get performance statistics.

        - No query param: returns stats for all loaded models + server status
        - `?model=default`: returns stats for a specific model
        """
        try:
            model_stats = await ctx.manager.get_stats(model)
            server_status = await ctx.manager.get_server_status()
            return {
                "models": model_stats if isinstance(model_stats, dict) else {model: model_stats},
                "server": server_status,
            }
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

    @router.get("/v1/hardware")
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

    return router

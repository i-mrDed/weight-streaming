"""Auto-tiering + conversation-summary routes."""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, FastAPI, HTTPException

from ..config import get_model_search_dirs
from ..schemas import (
    ConversationSummarizeRequest,
    ConversationSummarizeResponse,
)
from .. import tiering
from .context import ServerContext


def build_router(app: FastAPI, ctx: ServerContext) -> APIRouter:
    """Register auto-tiering + conversation routes."""
    router = APIRouter()

    app.state.tiering_manager = ctx.manager

    @router.get("/v1/tiering/config")
    async def get_tiering_config():
        """Current auto-tiering config + on-disk resolution per tier (so a
        broken pair is visible, not silent)."""
        cfg = tiering.resolve_state(tiering.load_config())
        problems = tiering.validate_config(cfg)
        return {"config": cfg, "problems": problems}

    @router.put("/v1/tiering/config")
    async def put_tiering_config(body: Dict[str, Any]):
        """Validate + persist a new tiering config (data/tiering.json).
        Returns the normalized config; 400 with readable problems when
        invalid (e.g. missing model file)."""
        try:
            saved = tiering.save_config(body)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        return {"status": "saved", "config": tiering.resolve_state(saved)}

    @router.post("/v1/tiering/route")
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
        tmanager = getattr(app.state, "tiering_manager", ctx.manager)
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

    @router.post("/v1/tiering/preview")
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

    @router.post("/v1/tiering/unpin")
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

    @router.get("/v1/tiering/stats")
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

    @router.post("/v1/tiering/pin")
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
    @router.post("/v1/conversation/summarize",
                 response_model=ConversationSummarizeResponse)
    async def summarize_conversation(
        request: ConversationSummarizeRequest,
    ):
        """Summarize a conversation; returns a running summary the caller
        can inject into the system prompt."""
        from ..conversation_summary import ConversationSummarizer, estimate_tokens

        messages = [{"role": m.role, "content": m.content}
                    for m in request.messages]
        svc = ConversationSummarizer(ctx.manager)
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

    return router

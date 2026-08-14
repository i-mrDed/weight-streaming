"""Issue routes: debug context, issue CRUD/export/verify."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.responses import PlainTextResponse

from ...issues import (
    IssueCreate,
    IssueService,
    IssueUpdate,
    IssueVerify,
    collect_debug_context,
)
from .context import ServerContext


def _tiering_debug_summary(app: FastAPI) -> Optional[dict]:
    """Compact auto-tiering snapshot for issue reports: enabled flag +
    route totals (aggregated per tier/reason — no per-event detail, so
    the report stays small and contains no prompts). Honest: None when
    anything fails (a report must never break because of telemetry)."""
    try:
        from .. import tiering
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


def build_router(app: FastAPI, ctx: ServerContext) -> APIRouter:
    """Register issue + debug routes."""
    router = APIRouter()
    issue_service: Optional[IssueService] = ctx.issue_service

    @router.get("/v1/debug/context")
    async def debug_context(
        model_path: str | None = None,
        last_error: str | None = None,
        last_endpoint: str | None = None,
    ):
        """Collect privacy-safe debug context for issue reports."""
        arch = None
        models = await ctx.manager.list_models()
        if models:
            model_path = model_path or models[0].path
            arch = models[0].arch
        return collect_debug_context(
            model_path=model_path,
            model_architecture=arch,
            last_error=last_error,
            last_endpoint=last_endpoint,
            log_tail=list(ctx.recent_errors[-50:]),
            tiering=_tiering_debug_summary(app),
        )

    @router.post("/v1/issues")
    async def create_issue(body: IssueCreate):
        """Create a new issue report."""
        try:
            if issue_service is None:
                raise HTTPException(status_code=500, detail="issue service not configured")
            # Merge server debug context if client context incomplete
            if not body.context.get("app_version"):
                body.context = {
                    **collect_debug_context(
                        log_tail=list(ctx.recent_errors[-50:]),
                        tiering=_tiering_debug_summary(app),
                    ),
                    **(body.context or {}),
                }
            issue = issue_service.create(body)
            return issue.model_dump()
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    @router.get("/v1/issues")
    async def list_issues(status: str | None = None, severity: str | None = None):
        """List issues, optionally filtered by status/severity."""
        try:
            if issue_service is None:
                raise HTTPException(status_code=500, detail="issue service not configured")
            issues = issue_service.list(status=status, severity=severity)
            return [i.model_dump() for i in issues]
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    @router.get("/v1/issues/export")
    async def export_issues(format: str = "md"):
        """Export issues summary (md or json)."""
        if issue_service is None:
            raise HTTPException(status_code=500, detail="issue service not configured")
        if format == "json":
            issues = issue_service.list()
            return [i.model_dump() for i in issues]
        md = issue_service.export_markdown()
        return PlainTextResponse(md, media_type="text/markdown")

    @router.get("/v1/issues/{issue_id}")
    async def get_issue(issue_id: str):
        """Get a single issue by ID."""
        if issue_service is None:
            raise HTTPException(status_code=500, detail="issue service not configured")
        issue = issue_service.get(issue_id)
        if not issue:
            raise HTTPException(status_code=404, detail=f"Issue {issue_id} not found")
        return issue.model_dump()

    @router.patch("/v1/issues/{issue_id}")
    async def update_issue(issue_id: str, body: IssueUpdate):
        """Update issue fields/status (maintainer)."""
        try:
            if issue_service is None:
                raise HTTPException(status_code=500, detail="issue service not configured")
            issue = issue_service.update(issue_id, body)
            return issue.model_dump()
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    @router.post("/v1/issues/{issue_id}/verify")
    async def verify_issue(issue_id: str, body: IssueVerify):
        """User verification of a fix."""
        try:
            if issue_service is None:
                raise HTTPException(status_code=500, detail="issue service not configured")
            issue = issue_service.verify(issue_id, body)
            return issue.model_dump()
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    return router

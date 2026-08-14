"""Hub routes: Hugging Face search/recommended, downloads, research."""
from __future__ import annotations

import asyncio
import json
import os
from typing import Optional

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.responses import StreamingResponse

from ..config import get_model_search_dirs
from ..hub import DownloadManager, HubUpstreamError, HubValidationError
from ..recommended import to_payload as recommended_payload
from ..research import ResearchValidationError, experiment as read_experiment
from ..schemas import (
    HubDownloadRequest,
    HubDeleteRequest,
    HubClearRequest,
)
from .context import ServerContext


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
        from ..assistants import get_assistant_store
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
    import subprocess
    import sys
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


def build_router(app: FastAPI, ctx: ServerContext) -> APIRouter:
    """Register hub + research routes."""
    router = APIRouter()
    hub_manager: Optional[DownloadManager] = ctx.hub_manager

    def _hub() -> DownloadManager:
        if hub_manager is None:
            raise HTTPException(status_code=500, detail="hub manager not configured")
        return hub_manager

    @router.get("/v1/hub/search")
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
        hm = _hub()
        try:
            if paginate:
                page = hm.search_with_cursor(q=q, sort=sort, limit=limit, cursor=cursor)
                results = page["results"]
                return {
                    "results": results,
                    "count": len(results),
                    "next_cursor": page["next_cursor"],
                }
            results = hm.search(q=q, sort=sort, limit=limit)
            return {"results": results, "count": len(results), "next_cursor": None}
        except HubUpstreamError as e:
            raise HTTPException(status_code=502, detail=str(e))

    @router.get("/v1/hub/recommended")
    async def hub_recommended():
        """Curated models proven on this reference rig (server/recommended.py).

        Static data — no network call. Every entry is backed by a measured
        experiment (``research/experiments/``) with the Thai quality gate, and
        carries the EXACT download files that were measured so users fetch the
        right quant. See the module docstring for the honest caveat (numbers
        are from this machine; other hardware will differ).
        """
        return recommended_payload()

    @router.get("/v1/research/experiment/{exp_path:path}")
    async def research_experiment(exp_path: str):
        """Serve one experiment's markdown record for the in-app Evidence
        viewer (research/experiments/). Path validated by containment — no
        traversal, only ``*.md`` files ever read (server/research.py).
        """
        try:
            return read_experiment(exp_path)
        except ResearchValidationError as e:
            raise HTTPException(status_code=e.status, detail=str(e))

    @router.get("/v1/hub/model/{repo_id:path}")
    async def hub_model(repo_id: str):
        """
        On-demand model detail (P5.1): aggregate HF model metadata + per-file
        byte sizes + shard/quant grouping for one repo. Cached ~15 min. HF
        unreachable → 502 (never a fake/empty 200). Fields HF omits are null.
        """
        try:
            return _hub().model_detail(repo_id)
        except HubValidationError as e:
            raise HTTPException(status_code=e.status, detail=str(e))
        except HubUpstreamError as e:
            raise HTTPException(status_code=502, detail=str(e))

    @router.post("/v1/hub/download", status_code=202)
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
        hm = _hub()
        try:
            task = hm.create_download(body.repo_id, body.filename, body.target_dir)
        except HubValidationError as e:
            raise HTTPException(status_code=e.status, detail=str(e))
        hm.schedule_download(task)
        return task.to_dict()

    @router.get("/v1/hub/downloads")
    async def hub_downloads():
        """List all download tasks with their latest status/progress."""
        items = _hub().list_tasks()
        return {"downloads": items, "count": len(items)}

    @router.get("/v1/hub/progress/{task_id}")
    async def hub_progress(task_id: str):
        """
        SSE stream of a download's REAL progress (bytes/percent/speed_bps/
        eta_s/status) until it reaches a terminal state (done/failed/cancelled).
        """
        task = _hub().get_task(task_id)
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

    @router.post("/v1/hub/download/{task_id}/cancel")
    async def hub_cancel(task_id: str):
        """
        Cancel a download. Sets the cancel flag; the worker stops within one
        chunk and the partial ``.part`` is KEPT so the task can be resumed.
        Idempotent for already-terminal tasks.
        """
        task = _hub().cancel(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail=f"download task {task_id} not found")
        return task.to_dict()

    @router.post("/v1/hub/download/{task_id}/resume")
    async def hub_resume(task_id: str):
        """
        Resume a cancelled/failed download (v1.1): re-queues the task; the
        worker appends the remaining bytes to the kept ``.part`` via HTTP
        ``Range`` instead of re-downloading from byte 0. 404 unknown task;
        409 when the task is not resumable (active or done).
        """
        hm = _hub()
        try:
            task = hm.resume(task_id)
        except ValueError as e:
            raise HTTPException(status_code=409, detail=str(e))
        if task is None:
            raise HTTPException(status_code=404, detail=f"download task {task_id} not found")
        hm.schedule_download(task)
        return task.to_dict()

    @router.post("/v1/hub/download/{task_id}/delete")
    async def hub_delete(task_id: str, body: Optional[HubDeleteRequest] = None):
        """
        Delete a download task from the manager (v1.1): stops a running
        worker and removes the partial ``.part``. By default the final
        ``.gguf`` of a completed task is left on disk; pass
        ``{"delete_file": true}`` to ALSO delete the model file (only for
        ``done`` tasks whose file is inside an allowed model dir and whose
        model is not currently loaded). Returns ``file_deleted`` honestly.
        """
        hm = _hub()
        delete_file = bool(body and body.delete_file)
        task = hm.get_task(task_id)
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
            loaded = await ctx.manager.list_models()
            if any(
                os.path.normcase(os.path.realpath(getattr(m, "path", "") or "")) == target_real
                for m in loaded
            ):
                raise HTTPException(
                    status_code=409,
                    detail="this model is currently loaded — unload it before deleting the file",
                )
        hm.delete(task_id, delete_file=delete_file)
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

    @router.post("/v1/hub/downloads/clear")
    async def hub_clear(body: Optional[HubClearRequest] = None):
        """
        Remove every FINISHED download (done/failed/cancelled) at once
        (v1.1): the panel's "clear finished" action. Active downloads are
        kept. Pass ``{"delete_file": true}`` to ALSO delete the model files
        of completed downloads — except those of currently loaded models,
        which are skipped and reported in ``files_skipped`` (never removed
        under a running backend). Returns the honest summary.
        """
        hm = _hub()
        delete_file = bool(body and body.delete_file)
        protected: set = set()
        if delete_file:
            # same normalized-path rule as the single-task delete endpoint
            loaded = await ctx.manager.list_models()
            protected = {
                os.path.normcase(os.path.realpath(getattr(m, "path", "") or ""))
                for m in loaded
            }
        # snapshot the DONE tasks' filenames BEFORE the clear so the response
        # can map task id → assistant references (the tasks are popped inside
        # clear(); their filenames would otherwise be gone).
        done_files = {
            t["id"]: t["filename"]
            for t in hm.list_tasks()
            if t.get("status") == "done"
        }
        result = hm.clear(delete_file=delete_file, protected_paths=protected)
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

    @router.post("/v1/hub/download/{task_id}/reveal")
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
        task = _hub().get_task(task_id)
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

    return router

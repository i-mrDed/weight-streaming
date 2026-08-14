"""Model routes: generate, stats, models list/scan/load/unload, browse."""
from __future__ import annotations

import asyncio
import os
import sys
from typing import Optional

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.responses import StreamingResponse

from ..config import get_model_search_dirs
from ..schemas import (
    GenerateRequest,
    GenerateResponse,
    ModelLoadRequest,
    ModelUnloadRequest,
    ModelActionResponse,
    ModelStatus,
)
from .context import ServerContext


def _scan_gguf_models(dir: str | None = None) -> dict:
    import glob

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


def _run_browse_dialog(mode: str = "file") -> dict:
    """Run native browse dialog via helper script (subprocess)."""
    helper = os.path.join(os.path.dirname(os.path.dirname(__file__)), "browse_dialog.py")
    try:
        # CREATE_NEW_CONSOLE helps dialog stay visible on Windows
        creationflags = 0
        if sys.platform == "win32":
            creationflags = getattr(__import__("subprocess"), "CREATE_NEW_PROCESS_GROUP", 0)
        result = __import__("subprocess").run(
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
    except __import__("subprocess").TimeoutExpired:
        return {"path": None, "error": "Dialog timed out (no selection within 2 minutes)"}
    except Exception as e:
        return {"path": None, "error": str(e)}


async def _stream_generate(request: GenerateRequest, manager) -> StreamingResponse:
    """Handle streaming generation via SSE."""
    import json
    import logging

    logger = logging.getLogger(__name__)

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


def build_router(app: FastAPI, ctx: ServerContext) -> APIRouter:
    """Register model routes."""
    import logging

    logger = logging.getLogger(__name__)
    router = APIRouter()

    @router.post("/v1/generate", response_model=GenerateResponse)
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
            return await _stream_generate(request, ctx.manager)

        try:
            result = await ctx.manager.generate(
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

    @router.get("/v1/models", response_model=list[ModelStatus])
    async def list_models():
        """List all loaded models."""
        return await ctx.manager.list_models()

    @router.get("/v1/browse")
    async def browse_model():
        """
        Open a native file dialog on the server to pick a .gguf model.
        Works because server and browser run on the same machine.
        Look for the dialog in the taskbar if it doesn't appear on top.
        """
        return await asyncio.get_running_loop().run_in_executor(
            None, lambda: _run_browse_dialog("file")
        )

    @router.get("/v1/browse-dir")
    async def browse_directory():
        """Open a native directory picker to select a folder to scan."""
        return await asyncio.get_running_loop().run_in_executor(
            None, lambda: _run_browse_dialog("dir")
        )

    @router.get("/v1/models/scan")
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

    @router.post("/v1/models/load", response_model=ModelActionResponse)
    async def load_model(request: ModelLoadRequest):
        """
        Load a model into the server.

        The model becomes available for generation at its model_id.
        """
        try:
            if request.force and request.model_id in ctx.manager._models:
                await ctx.manager.unload(request.model_id)

            result = await ctx.manager.load(
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

    @router.post("/v1/models/unload", response_model=ModelActionResponse)
    async def unload_model(request: ModelUnloadRequest):
        """Unload a model from the server."""
        try:
            await ctx.manager.unload(request.model_id)
            return ModelActionResponse(
                status="unloaded",
                model_id=request.model_id,
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    return router

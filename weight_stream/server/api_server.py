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

import json
import logging
import time
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from .config import get_config, ServerConfig
from .model_manager import ModelManager
from .openai_compat import handle_chat_completion
from .anthropic_compat import handle_anthropic_messages
from .schemas import (
    GenerateRequest,
    GenerateResponse,
    ModelLoadRequest,
    ModelUnloadRequest,
    ModelActionResponse,
    ModelStatus,
    ErrorResponse,
    ChatCompletionRequest,
)
from .streaming import sse_stream, ws_stream

logger = logging.getLogger(__name__)

# ── Application factory ─────────────────────────────────────────────


def create_app(config: ServerConfig = None) -> tuple[FastAPI, ModelManager]:
    """Create and configure the FastAPI application with ModelManager."""
    if config is None:
        config = get_config()
    
    manager = ModelManager()
    
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Startup and shutdown lifecycle."""
        logger.info(f"Server starting on {config.host}:{config.port}")
        yield
        logger.info("Server shutting down...")
        await manager.shutdown()
        logger.info("Server stopped")
    
    app = FastAPI(
        title="Weight Streaming API",
        description=(
            "Run LLMs larger than your RAM — speculative weight streaming from NVMe. "
            "OpenAI-compatible API for IDE/agent integration."
        ),
        version="0.11.0",
        lifespan=lifespan,
    )
    
    # CORS — allow all origins for local development
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Mount static files (SPA)
    import os
    static_dir = os.path.join(os.path.dirname(__file__), "static")
    if os.path.isdir(static_dir):
        app.mount("/app", StaticFiles(directory=static_dir, html=True), name="static")
    
    # Health check
    @app.get("/health")
    async def health():
        return {"status": "ok", "version": "0.11.0"}
    
    # Redirect root to SPA
    @app.get("/")
    async def root():
        return {"message": "Weight Streaming API v0.11.0", "docs": "/docs", "app": "/app"}
    
    # ── REST Endpoints ──────────────────────────────────────────────
    
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
    async def stats(model: str = None):
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
    
    @app.get("/v1/browse")
    async def browse_model():
        """
        Open a native file dialog on the server to let the user pick a model.
        Runs in a subprocess to avoid blocking the asyncio event loop.
        Returns the full path of the selected .gguf file.
        """
        import subprocess, sys, os
        
        try:
            # Run tkinter dialog in subprocess to avoid blocking asyncio
            result = await asyncio.get_running_loop().run_in_executor(
                None,
                lambda: subprocess.run(
                    [sys.executable, "-c",
                     "import tkinter as tk; from tkinter import filedialog; "
                     "r=tk.Tk(); r.withdraw(); r.attributes('-topmost',True); "
                     "p=filedialog.askopenfilename(title='Select GGUF Model', "
                     "filetypes=[('GGUF Models','*.gguf'),('All Files','*.*')]); "
                     "r.destroy(); print(p)"],
                    capture_output=True, text=True, timeout=60,
                )
            )
            path = result.stdout.strip()
            if path and os.path.isfile(path):
                size = os.path.getsize(path)
                return {
                    "path": os.path.abspath(path),
                    "name": os.path.basename(path),
                    "size_gb": round(size / (1024**3), 2),
                }
            return {"path": None, "cancelled": True}
        except subprocess.TimeoutExpired:
            return {"path": None, "error": "Dialog timed out"}
        except Exception as e:
            return {"path": None, "error": str(e)}
    
    @app.get("/v1/browse-dir")
    async def browse_directory():
        """Open a native directory picker in a subprocess."""
        import subprocess, sys, os
        
        try:
            result = await asyncio.get_running_loop().run_in_executor(
                None,
                lambda: subprocess.run(
                    [sys.executable, "-c",
                     "import tkinter as tk; from tkinter import filedialog; "
                     "r=tk.Tk(); r.withdraw(); r.attributes('-topmost',True); "
                     "p=filedialog.askdirectory(title='Select Model Directory'); "
                     "r.destroy(); print(p)"],
                    capture_output=True, text=True, timeout=60,
                )
            )
            path = result.stdout.strip()
            if path and os.path.isdir(path):
                return {"path": os.path.abspath(path)}
            return {"path": None, "cancelled": True}
        except subprocess.TimeoutExpired:
            return {"path": None, "error": "Dialog timed out"}
        except Exception as e:
            return {"path": None, "error": str(e)}
    
    @app.get("/v1/models/scan")
    async def scan_models(dir: str | None = None):
        """
        Scan directories for available GGUF model files.
        
        Scans the configured models directory (WS_MODELS_DIR env var,
        default: current directory + common model locations).
        Returns a list of found .gguf files with size info.
        """
        import os, glob
        
        search_dirs = []
        if dir:
            search_dirs.append(dir)
        else:
            # Default search paths
            ws_dir = os.environ.get("WS_MODELS_DIR", "")
            if ws_dir:
                search_dirs.append(ws_dir)
            # Also search current dir + common locations
            search_dirs.extend([
                os.getcwd(),
                os.path.join(os.getcwd(), "research", "models"),
                os.path.join(os.getcwd(), "models"),
                os.path.expanduser("~/models"),
            ])
        
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
                    found.append({
                        "path": abspath,
                        "name": os.path.basename(abspath),
                        "size_bytes": size,
                        "size_gb": round(size / (1024**3), 2),
                        "directory": os.path.dirname(abspath),
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
            raise HTTPException(status_code=500, detail=str(e))
    
    return app, manager


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

"""Streaming routes: WebSocket /v1/stream, OpenAI + Anthropic compat."""
from __future__ import annotations

import logging
import secrets
from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect

from ..schemas import ChatCompletionRequest
from ..anthropic_compat import handle_anthropic_messages
from ..openai_compat import handle_chat_completion
from .context import ServerContext

logger = logging.getLogger(__name__)


def build_router(app: FastAPI, ctx: ServerContext) -> APIRouter:
    """Register streaming routes."""
    router = APIRouter()

    @router.websocket("/v1/stream")
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

        Security (fix/ws-security):
        - Origin must be loopback (or in WS_CORS_ORIGINS) — blocks drive-by
          websocket from any web page (CORS middleware does NOT cover WS).
        - When WS_API_TOKEN is set, the client must send
          `Authorization: Bearer <token>` (same rule as HTTP /v1/*).
        Both checks run BEFORE accept(); failures close with 4408/4401.
        """
        # 1) Origin check (WS bypasses the HTTP CORS middleware)
        origin = websocket.headers.get("origin", "")
        allowed = ctx.ws_origin_allowed(origin) if ctx.ws_origin_allowed else True
        if not allowed:
            await websocket.close(code=4408, reason="origin not allowed")
            return
        # 2) API token check (same WS_API_TOKEN as HTTP /v1/*)
        if ctx.api_token:
            auth = websocket.headers.get("authorization", "")
            if not secrets.compare_digest(auth, f"Bearer {ctx.api_token}"):
                await websocket.close(code=4401, reason="unauthorized")
                return

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

            gen = ctx.manager.generate_stream(
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

    @router.post("/v1/chat/completions")
    async def chat_completions(request: ChatCompletionRequest):
        """
        OpenAI-compatible chat completions endpoint.

        Compatible with any OpenAI SDK, VS Code Continue.dev, Cline, etc.

        Set `OPENAI_BASE_URL=http://localhost:8765/v1` and use
        any `model_id` as the model name.
        """
        try:
            return await handle_chat_completion(request, ctx.manager)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except Exception as e:
            logger.exception("Chat completion failed")
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/v1/messages")
    async def anthropic_messages(request: Request):
        """
        Anthropic-compatible Messages API endpoint.

        Compatible with Claude Code, Anthropic SDK, and any Anthropic-compatible client.

        Set `ANTHROPIC_BASE_URL=http://localhost:8765/v1` and use
        any `model_id` as the model name.
        """
        try:
            return await handle_anthropic_messages(request, ctx.manager)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except Exception as e:
            logger.exception("Anthropic message failed")
            raise HTTPException(status_code=500, detail=str(e))

    return router

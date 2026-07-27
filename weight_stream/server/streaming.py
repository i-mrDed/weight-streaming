"""
Streaming helpers for SSE (Server-Sent Events) and WebSocket delivery.

Used by the API server to stream token-by-token output to clients.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncIterator

from starlette.websockets import WebSocket, WebSocketDisconnect


# ── SSE (Server-Sent Events) ────────────────────────────────────────


async def sse_stream(generator: AsyncIterator[dict]) -> AsyncIterator[str]:
    """
    Wrap an async token generator as SSE (text/event-stream).
    
    Usage:
        from fastapi.responses import StreamingResponse
        return StreamingResponse(sse_stream(gen), media_type="text/event-stream")
    """
    async for event in generator:
        yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


def sse_error_message(code: str, message: str) -> str:
    """Return a single SSE error event as a string."""
    return f"data: {json.dumps({'error': message, 'code': code})}\n\n"


# ── WebSocket ────────────────────────────────────────────────────────


async def ws_stream(
    websocket: WebSocket,
    generator: AsyncIterator[dict],
) -> None:
    """
    Stream token-by-token output over WebSocket.
    
    Protocol:
        Client sends: {"type": "generate", "model": "...", "prompt": "..."}
        Server sends: {"type": "token", "text": "...", "index": 0}
        Server sends: {"type": "done", "stats": {...}} at end
        Server sends: {"type": "error", "message": "...", "code": "..."} on error
        
    Client disconnects to cancel in-progress generation.
    """
    await websocket.accept()
    
    try:
        async for event in generator:
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
        pass  # Client intentionally disconnected
    except Exception as e:
        try:
            await websocket.send_json({
                "type": "error",
                "message": str(e),
                "code": "GENERATION_ERROR",
            })
        except WebSocketDisconnect:
            pass

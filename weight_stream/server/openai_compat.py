"""
OpenAI-compatible API adapter.

Converts OpenAI Chat Completion format to weight-streaming internal format,
enabling any OpenAI-compatible client (VS Code, Cursor, Continue.dev, etc.)
to connect to the weight-streaming API server.
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from typing import Any, AsyncIterator

from fastapi import HTTPException
from fastapi.responses import StreamingResponse

from .model_manager import ModelManager
from .schemas import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatCompletionChoice,
    ChatCompletionUsage,
    ChatMessage,
    GenerateRequest,
)
from .streaming import sse_stream


async def handle_chat_completion(
    request: ChatCompletionRequest,
    manager: ModelManager,
) -> ChatCompletionResponse | StreamingResponse:
    """
    Handle an OpenAI-compatible chat completion request.
    
    Uses llama-cpp-python's create_chat_completion() which automatically
    applies the model's built-in chat template (Qwen uses <|im_start|>,
    Llama uses [INST], etc.) — producing much better responses than
    manual prompt construction.
    """
    # Convert our ChatMessage objects to dicts for llama.cpp
    messages = [{"role": m.role, "content": m.content} for m in request.messages]
    
    # Token estimation (approximate)
    prompt_tokens = sum(len(m["content"].split()) for m in messages)
    
    if request.stream:
        return await _stream_response(request, messages, prompt_tokens, manager)
    else:
        return await _complete_response(request, messages, prompt_tokens, manager)


def _messages_to_prompt(messages: list[ChatMessage]) -> str:
    """Convert chat messages to a single prompt string."""
    parts = []
    for msg in messages:
        if msg.role == "system":
            parts.append(f"System: {msg.content}")
        elif msg.role == "user":
            parts.append(f"User: {msg.content}")
        elif msg.role == "assistant":
            parts.append(f"Assistant: {msg.content}")
    return "\n".join(parts)


async def _complete_response(
    request: ChatCompletionRequest,
    messages: list[dict],
    prompt_tokens: int,
    manager: ModelManager,
) -> ChatCompletionResponse:
    """Generate a complete (non-streaming) chat completion response."""
    result = await manager.chat_completion(
        model_id=request.model,
        messages=messages,
        max_tokens=request.max_tokens,
        temperature=request.temperature,
        top_p=request.top_p,
        reasoning_mode=request.reasoning_mode or "auto",
    )
    
    completion_tokens = result.get("tokens_generated", 0)
    
    return ChatCompletionResponse(
        id=f"chatcmpl-{uuid.uuid4().hex[:12]}",
        created=int(time.time()),
        model=request.model,
        choices=[
            ChatCompletionChoice(
                index=0,
                message=ChatMessage(
                    role="assistant",
                    content=result["output"],
                ),
                finish_reason="stop",
            )
        ],
        usage=ChatCompletionUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        ),
    )


async def _stream_response(
    request: ChatCompletionRequest,
    messages: list[dict],
    prompt_tokens: int,
    manager: ModelManager,
) -> StreamingResponse:
    """Generate a streaming chat completion response via SSE."""
    chat_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
    created = int(time.time())
    
    async def generate():
        gen = manager.chat_completion_stream(
            model_id=request.model,
            messages=messages,
            max_tokens=request.max_tokens,
            temperature=request.temperature,
            top_p=request.top_p,
            reasoning_mode=request.reasoning_mode or "auto",
        )
        
        async for event in gen:
            if event.get("done"):
                chunk = {
                    "id": chat_id,
                    "object": "chat.completion.chunk",
                    "created": created,
                    "model": request.model,
                    "choices": [{
                        "index": 0,
                        "delta": {},
                        "finish_reason": "stop",
                    }],
                }
                yield f"data: {json.dumps(chunk)}\n\n"
                yield "data: [DONE]\n\n"
            else:
                chunk = {
                    "id": chat_id,
                    "object": "chat.completion.chunk",
                    "created": created,
                    "model": request.model,
                    "choices": [{
                        "index": 0,
                        "delta": {"content": event["token"]},
                        "finish_reason": None,
                    }],
                }
                yield f"data: {json.dumps(chunk)}\n\n"
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "X-Accel-Buffering": "no",
            "Cache-Control": "no-cache",
        },
    )

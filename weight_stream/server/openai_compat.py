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
    
    Converts messages to a prompt string and delegates to ModelManager.
    Returns either a complete ChatCompletionResponse or a streaming
    SSE response depending on request.stream.
    """
    # Convert messages array to prompt string
    prompt = _messages_to_prompt(request.messages)
    
    # Token estimation (approximate — we don't have direct tokenizer access)
    prompt_tokens = len(prompt.split())
    
    if request.stream:
        return await _stream_response(request, prompt, prompt_tokens, manager)
    else:
        return await _complete_response(request, prompt, prompt_tokens, manager)


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
    prompt: str,
    prompt_tokens: int,
    manager: ModelManager,
) -> ChatCompletionResponse:
    """Generate a complete (non-streaming) chat completion response."""
    gen_request = GenerateRequest(
        model=request.model,
        prompt=prompt,
        max_tokens=request.max_tokens,
        temperature=request.temperature,
        top_p=request.top_p,
        stream=False,
    )
    
    result = await manager.generate(
        model_id=gen_request.model,
        prompt=gen_request.prompt,
        max_tokens=gen_request.max_tokens,
        temperature=gen_request.temperature,
        top_p=gen_request.top_p,
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
    prompt: str,
    prompt_tokens: int,
    manager: ModelManager,
) -> StreamingResponse:
    """Generate a streaming chat completion response via SSE."""
    chat_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
    created = int(time.time())
    
    async def generate():
        gen = manager.generate_stream(
            model_id=request.model,
            prompt=prompt,
            max_tokens=request.max_tokens,
            temperature=request.temperature,
            top_p=request.top_p,
        )
        
        async for event in gen:
            if event.get("done"):
                # Final chunk with finish_reason
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

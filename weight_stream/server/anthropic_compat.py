"""
Anthropic-compatible API adapter.

Converts Anthropic Messages API format to weight-streaming internal format,
enabling Claude Code, Anthropic SDK, and any Anthropic-compatible client
to connect to the weight-streaming API server.
"""

from __future__ import annotations

import json
import time
import uuid
from typing import Any

from fastapi import HTTPException, Request
from fastapi.responses import StreamingResponse

from .model_manager import ModelManager
from .schemas import (
    GenerateRequest,
)
from .streaming import sse_stream


async def handle_anthropic_messages(
    request: Request,
    manager: ModelManager,
):
    """
    Handle an Anthropic Messages API request.
    
    Reads the raw JSON body and converts to our internal format.
    Supports both streaming (SSE in Anthropic format) and non-streaming.
    """
    body = await request.json()
    
    model_id = body.get("model", "default")
    messages = body.get("messages", [])
    max_tokens = body.get("max_tokens", 128)
    temperature = body.get("temperature", 0.7)
    top_p = body.get("top_p", 1.0)
    stream = body.get("stream", False)
    
    # Convert messages to prompt string
    prompt = _messages_to_prompt(messages)
    
    if stream:
        return await _stream_response(model_id, prompt, max_tokens, temperature, top_p, manager)
    else:
        return await _complete_response(model_id, prompt, max_tokens, temperature, top_p, manager)


def _messages_to_prompt(messages: list[dict]) -> str:
    """Convert Anthropic messages to a single prompt string."""
    parts = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        # Handle both string and array content formats
        if isinstance(content, list):
            texts = [b.get("text", "") for b in content if b.get("type") == "text"]
            content = " ".join(texts)
        if role == "system":
            parts.append(f"System: {content}")
        elif role == "user":
            parts.append(f"Human: {content}")
        elif role == "assistant":
            parts.append(f"Assistant: {content}")
    return "\n\n".join(parts)


async def _complete_response(
    model_id: str,
    prompt: str,
    max_tokens: int,
    temperature: float,
    top_p: float,
    manager: ModelManager,
) -> dict:
    """Generate a complete (non-streaming) Anthropic response."""
    result = await manager.generate(
        model_id=model_id,
        prompt=prompt,
        max_tokens=max_tokens,
        temperature=temperature,
        top_p=top_p,
    )
    
    output = result.get("output", "")
    tokens_generated = result.get("tokens_generated", len(output.split()))
    prompt_tokens = len(prompt.split())
    
    return {
        "id": f"msg_{uuid.uuid4().hex[:12]}",
        "type": "message",
        "role": "assistant",
        "model": model_id,
        "content": [{"type": "text", "text": output}],
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {
            "input_tokens": prompt_tokens,
            "output_tokens": tokens_generated,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0,
        },
    }


async def _stream_response(
    model_id: str,
    prompt: str,
    max_tokens: int,
    temperature: float,
    top_p: float,
    manager: ModelManager,
) -> StreamingResponse:
    """Generate a streaming Anthropic response via SSE."""
    msg_id = f"msg_{uuid.uuid4().hex[:12]}"
    prompt_tokens = len(prompt.split())
    
    async def generate():
        # message_start
        yield f"event: message_start\n"
        yield f"data: {json.dumps({'type': 'message_start', 'message': {'id': msg_id, 'type': 'message', 'role': 'assistant', 'model': model_id, 'usage': {'input_tokens': prompt_tokens}}})}\n\n"
        
        # content_block_start
        yield f"event: content_block_start\n"
        yield f"data: {json.dumps({'type': 'content_block_start', 'index': 0, 'content_block': {'type': 'text', 'text': ''}})}\n\n"
        
        # Ping to keep connection alive
        yield f"event: ping\n"
        yield f"data: {json.dumps({'type': 'ping'})}\n\n"
        
        gen = manager.generate_stream(
            model_id=model_id,
            prompt=prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
        )
        
        token_count = 0
        async for event in gen:
            if event.get("done"):
                break
            token = event.get("token", "")
            token_count += 1
            # content_block_delta
            yield f"event: content_block_delta\n"
            yield f"data: {json.dumps({'type': 'content_block_delta', 'index': 0, 'delta': {'type': 'text_delta', 'text': token}})}\n\n"
        
        # content_block_stop
        yield f"event: content_block_stop\n"
        yield f"data: {json.dumps({'type': 'content_block_stop', 'index': 0})}\n\n"
        
        # message_delta
        yield f"event: message_delta\n"
        yield f"data: {json.dumps({'type': 'message_delta', 'delta': {'stop_reason': 'end_turn', 'stop_sequence': None}, 'usage': {'output_tokens': token_count}})}\n\n"
        
        # message_stop
        yield f"event: message_stop\n"
        yield f"data: {json.dumps({'type': 'message_stop'})}\n\n"
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "X-Accel-Buffering": "no",
            "Cache-Control": "no-cache",
        },
    )

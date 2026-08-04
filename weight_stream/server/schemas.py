"""
Pydantic request/response schemas for the weight-streaming API.

All API types are defined here for validation, documentation (OpenAPI),
and type safety across the server module.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ── Request Models ──────────────────────────────────────────────────


class GenerateRequest(BaseModel):
    """Request to generate text from a loaded model."""
    model: str = Field(default="default", description="Model ID or name")
    prompt: str = Field(..., min_length=1, description="Input text prompt")
    max_tokens: int = Field(default=128, ge=1, le=8192, description="Max tokens to generate")
    temperature: float = Field(default=0.7, ge=0.0, le=2.0, description="Sampling temperature")
    top_p: float = Field(default=0.9, ge=0.0, le=1.0, description="Nucleus sampling threshold")
    stream: bool = Field(default=False, description="Enable SSE token streaming")

    model_config = {"extra": "allow"}


class ModelLoadRequest(BaseModel):
    """Request to load a model into the server."""
    model_id: str = Field(..., min_length=1, description="Unique model identifier")
    model_path: str = Field(..., min_length=1, description="Path to GGUF model file")
    buffer_mb: int = Field(default=64, ge=1, description="Buffer size in MB")
    n_ctx: int = Field(default=512, ge=8, description="Context window size")
    n_threads: Optional[int] = Field(default=None, description="Number of CPU threads")
    force: bool = Field(default=False, description="Force reload if already loaded")


class ModelUnloadRequest(BaseModel):
    """Request to unload a model from the server."""
    model_id: str = Field(..., min_length=1, description="Model ID to unload")


class HubDownloadRequest(BaseModel):
    """Request to start a Hugging Face GGUF download (P4 Hub)."""
    repo_id: str = Field(..., min_length=1, description="HF repo id, e.g. 'org/model-gguf'")
    filename: str = Field(..., min_length=1, description="GGUF filename within the repo")
    target_dir: Optional[str] = Field(
        default=None,
        description="Destination dir; must resolve inside an allowed model dir",
    )


# ── Response Models ──────────────────────────────────────────────────


class BufferStats(BaseModel):
    """Buffer performance statistics."""
    capacity_shards: int = 0
    hot_shards: int = 0
    hits: int = 0
    misses: int = 0
    hit_rate: float = 0.0
    prefetches: int = 0
    evictions: int = 0
    total_accesses: int = 0
    capacity_mb: int = 0


class PrefetcherStats(BaseModel):
    """Prefetcher statistics."""
    prefetched: int = 0
    queued: int = 0


class PageCacheStats(BaseModel):
    """OS page cache residency statistics."""
    resident_ratio: float = 0.0
    resident_gb: float = 0.0
    total_gb: float = 0.0


class ModelInfo(BaseModel):
    """Model metadata."""
    path: Optional[str] = None
    arch: Optional[str] = None
    n_experts: int = 0


class ModelStatus(BaseModel):
    """Status of a loaded model."""
    id: str
    path: str
    loaded: bool
    arch: Optional[str] = None
    n_experts: int = 0
    buffer_mb: int = 64
    last_used: Optional[str] = None
    capabilities: Optional[Dict[str, Any]] = None


class AssistantCreate(BaseModel):
    """Create an assistant (P7.2)."""
    name: str = Field(..., min_length=1, max_length=100)
    system_prompt: str = ""
    description: str = ""
    model_id: Optional[str] = None
    params: Optional[Dict[str, Any]] = None


class AssistantUpdate(BaseModel):
    """Update an assistant (P7.2)."""
    name: Optional[str] = None
    system_prompt: Optional[str] = None
    description: Optional[str] = None
    model_id: Optional[str] = None
    params: Optional[Dict[str, Any]] = None


class GenerationResult(BaseModel):
    """Result from a generation request (non-streaming)."""
    model: str = "default"
    prompt: str = ""
    output: str = ""
    tokens_generated: int = 0
    elapsed_seconds: float = 0.0
    tokens_per_second: float = 0.0
    stats: Optional[Dict[str, Any]] = None


class GenerateResponse(BaseModel):
    """Full response from a generation request."""
    model: str = "default"
    prompt: str = ""
    output: str = ""
    tokens_generated: int = 0
    elapsed_seconds: float = 0.0
    tokens_per_second: float = 0.0
    stats: Optional[Dict[str, Any]] = None


class ModelActionResponse(BaseModel):
    """Response for model load/unload actions."""
    status: str
    model_id: str
    message: Optional[str] = None


class ErrorResponse(BaseModel):
    """Standard error response."""
    error: str
    code: str = "UNKNOWN"
    details: Optional[Dict[str, Any]] = None


# ── Streaming Models ─────────────────────────────────────────────────


class StreamToken(BaseModel):
    """A single token in a streaming response."""
    token: str = ""
    index: int = 0
    done: bool = False
    stats: Optional[Dict[str, Any]] = None


# ── OpenAI-Compatible Models ─────────────────────────────────────────


class ChatMessage(BaseModel):
    """OpenAI-compatible chat message."""
    role: str = Field(..., pattern="^(system|user|assistant|tool)$")
    content: str = Field(default="", min_length=0)
    tool_calls: Optional[List[Dict[str, Any]]] = Field(default=None, description="Tool calls requested by the model (P7.3)")


class ChatCompletionRequest(BaseModel):
    """OpenAI-compatible chat completion request."""
    model: str = Field(default="default")
    messages: List[ChatMessage] = Field(..., min_length=1)
    max_tokens: int = Field(default=128, ge=1, le=8192)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    top_p: float = Field(default=1.0, ge=0.0, le=1.0)
    stream: bool = Field(default=False)
    reasoning_effort: Optional[str] = Field(default="medium", description="Reasoning effort level: low, medium, high (legacy)")
    reasoning_mode: Optional[str] = Field(default=None, description="Reasoning mode: auto, on, off (P7 — controls thinking)")
    tools: Optional[List[Dict[str, Any]]] = Field(default=None, description="Available agent tools")

    model_config = {"extra": "allow"}


class ChatCompletionChoice(BaseModel):
    """A single choice in a chat completion response."""
    index: int = 0
    message: ChatMessage
    finish_reason: str = "stop"


class ChatCompletionUsage(BaseModel):
    """Token usage statistics."""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ChatCompletionResponse(BaseModel):
    """OpenAI-compatible chat completion response."""
    id: str = ""
    object: str = "chat.completion"
    created: int = 0
    model: str = "default"
    choices: List[ChatCompletionChoice] = []
    usage: ChatCompletionUsage = ChatCompletionUsage()

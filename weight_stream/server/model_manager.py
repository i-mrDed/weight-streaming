"""
Model lifecycle manager for the weight-streaming API server.

Manages multiple WeightStreamModel instances:
- Load / unload / reload models by ID
- Track idle time for automatic cleanup
- Thread-safe generation delegation
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, AsyncIterator, Dict, Optional

from ..backends.llama_cpp import WeightStreamModel
from ..core.exceptions import WeightStreamError, ModelError, GenerationError
from .config import get_config
from .schemas import ModelStatus

logger = logging.getLogger(__name__)


class ModelManager:
    """
    Manages multiple WeightStreamModel instances.
    
    Thread safety: asyncio.Lock per model_id for generate()
    Access to _models dict is protected by _dict_lock.
    """
    
    def __init__(self):
        self._models: Dict[str, WeightStreamModel] = {}
        self._configs: Dict[str, dict] = {}  # saved configs for reload
        self._locks: Dict[str, asyncio.Lock] = {}
        self._last_used: Dict[str, float] = {}
        self._generating: Dict[str, bool] = {}
        
        self._dict_lock = asyncio.Lock()
        self._cleanup_task: Optional[asyncio.Task] = None
        
        self._cfg = get_config()
    
    # ── Model lifecycle ─────────────────────────────────────────────
    
    async def load(self, model_id: str, model_path: str, **kwargs) -> dict:
        """
        Load a model into the manager.
        
        Args:
            model_id: Unique identifier for this model instance
            model_path: Path to GGUF model file
            **kwargs: Forwarded to WeightStreamModel constructor
                       (buffer_mb, n_ctx, n_threads, verbose)
            
        Returns:
            {"status": "loaded", "model_id": model_id}
            
        Raises:
            ModelError: If model file not found or load fails
            ValueError: If model already loaded and force=False
        """
        async with self._dict_lock:
            if model_id in self._models:
                raise ValueError(
                    f"Model '{model_id}' is already loaded. "
                    f"Use force=True to reload."
                )
            
            # Build kwargs with defaults
            buffer_mb = kwargs.pop("buffer_mb", self._cfg.default_buffer_mb)
            n_ctx = kwargs.pop("n_ctx", self._cfg.default_n_ctx)
            n_threads = kwargs.pop("n_threads", self._cfg.default_n_threads)
            verbose = kwargs.pop("verbose", False)
            
            # Enforce max models
            if len(self._models) >= self._cfg.max_loaded_models:
                # Unload oldest idle model
                oldest_id, oldest_time = None, float("inf")
                now = time.time()
                for mid, lu in self._last_used.items():
                    if not self._generating.get(mid, False) and lu < oldest_time:
                        oldest_time = lu
                        oldest_id = mid
                if oldest_id:
                    await self.unload(oldest_id)
                else:
                    raise RuntimeError(
                        f"Max models ({self._cfg.max_loaded_models}) loaded "
                        f"and all are busy generating."
                    )
            
            # Load model (CPU-bound, run in thread)
            loop = asyncio.get_running_loop()
            model = await loop.run_in_executor(
                None,
                lambda: WeightStreamModel(
                    model_path=model_path,
                    buffer_mb=buffer_mb,
                    n_ctx=n_ctx,
                    n_threads=n_threads,
                    verbose=verbose,
                    **kwargs,
                )
            )
            
            self._models[model_id] = model
            self._configs[model_id] = {
                "model_path": model_path,
                "buffer_mb": buffer_mb,
                "n_ctx": n_ctx,
                "n_threads": n_threads,
            }
            self._locks[model_id] = asyncio.Lock()
            self._last_used[model_id] = time.time()
            self._generating[model_id] = False
        
        logger.info(f"Model loaded: {model_id} ({model_path})")
        
        # Start idle cleanup if not already running
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._auto_cleanup())
        
        return {"status": "loaded", "model_id": model_id}
    
    async def unload(self, model_id: str) -> dict:
        """
        Unload a model from the manager.
        
        Idempotent: does not error if model is not loaded.
        """
        async with self._dict_lock:
            model = self._models.pop(model_id, None)
            self._configs.pop(model_id, None)
            self._locks.pop(model_id, None)
            self._last_used.pop(model_id, None)
            self._generating.pop(model_id, None)
        
        if model:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, model.close)
            logger.info(f"Model unloaded: {model_id}")
        
        return {"status": "unloaded", "model_id": model_id}
    
    async def reload(self, model_id: str) -> dict:
        """Unload then reload a model with its saved config."""
        config = self._configs.get(model_id)
        if not config:
            raise ValueError(f"No saved config for model '{model_id}'")
        
        await self.unload(model_id)
        return await self.load(model_id, **config)
    
    async def load_or_get(self, model_id: str, model_path: str, **kwargs) -> None:
        """Load a model only if not already loaded."""
        async with self._dict_lock:
            if model_id not in self._models:
                # Release lock during load to avoid deadlock
                pass
        if model_id not in self._models:
            await self.load(model_id, model_path, **kwargs)
    
    # ── Generation ──────────────────────────────────────────────────
    
    async def generate(
        self,
        model_id: str,
        prompt: str,
        max_tokens: int = 128,
        temperature: float = 0.7,
        top_p: float = 0.9,
        **kwargs,
    ) -> dict:
        """Generate text (non-streaming)."""
        model = self._get_model(model_id)
        
        async with self._locks[model_id]:
            self._generating[model_id] = True
            self._last_used[model_id] = time.time()
            try:
                loop = asyncio.get_running_loop()
                start = time.time()
                
                output = await loop.run_in_executor(
                    None,
                    lambda: model.generate(
                        prompt=prompt,
                        max_tokens=max_tokens,
                        temperature=temperature,
                        top_p=top_p,
                        **kwargs,
                    )
                )
                
                elapsed = time.time() - start
                stats = await loop.run_in_executor(None, model.get_stats)
                
                # Count tokens from stats
                gen = stats.get("generation", {})
                token_count = gen.get("token_count", 0)
                
                return {
                    "model": model_id,
                    "prompt": prompt,
                    "output": output,
                    "tokens_generated": token_count,
                    "elapsed_seconds": round(elapsed, 3),
                    "tokens_per_second": round(token_count / elapsed, 2) if elapsed > 0 else 0,
                    "stats": stats,
                }
            finally:
                self._generating[model_id] = False
    
    async def generate_stream(
        self,
        model_id: str,
        prompt: str,
        max_tokens: int = 128,
        temperature: float = 0.7,
        top_p: float = 0.9,
        **kwargs,
    ) -> AsyncIterator[dict]:
        """
        Generate text with token-by-token streaming.
        
        Yields:
            {"token": "...", "index": 0, "done": False}
            ...
            {"token": "", "index": N, "done": True, "stats": {...}}
        """
        model = self._get_model(model_id)
        
        async with self._locks[model_id]:
            self._generating[model_id] = True
            self._last_used[model_id] = time.time()
            try:
                loop = asyncio.get_running_loop()
                start = time.time()
                
                stream = model._llm(
                    prompt,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    top_p=top_p,
                    stream=True,
                    **kwargs,
                )
                
                token_count = 0
                for chunk in stream:
                    if "choices" in chunk and len(chunk["choices"]) > 0:
                        text = chunk["choices"][0].get("text", "")
                        yield {
                            "token": text,
                            "index": token_count,
                            "done": False,
                        }
                        token_count += 1
                
                elapsed = time.time() - start
                stats = await loop.run_in_executor(None, model.get_stats)
                
                yield {
                    "token": "",
                    "index": token_count,
                    "done": True,
                    "stats": stats,
                }
            finally:
                self._generating[model_id] = False
    
    @staticmethod
    def _format_chat_prompt(messages: list[dict]) -> str:
        """
        Format messages in a robust Q&A style that works across models,
        including heavily quantized ones where ChatML fails.
        
        Empirically verified: Q&A / Instruct style produces correct answers
        on Qwen Q2_K, while ChatML (<|im_start|>) causes echo/garbage.
        """
        system = "You are a helpful assistant."
        parts = []
        for msg in messages:
            role = msg.get("role", "user")
            content = (msg.get("content") or "").strip()
            if role == "system" and content:
                system = content
            elif role == "user":
                parts.append(f"User: {content}")
            elif role == "assistant":
                parts.append(f"Assistant: {content}")
        
        prompt = f"System: {system}\n\n"
        prompt += "\n".join(parts)
        prompt += "\nAssistant:"
        return prompt
    
    @staticmethod
    def _clean_chat_output(text: str) -> str:
        """Strip trailing garbage from model output."""
        text = text.strip()
        # Stop at role markers if model continues the dialogue
        for marker in ("\nUser:", "\nSystem:", "\nAssistant:", "\n\nUser", "\n\nSystem"):
            idx = text.find(marker)
            if idx > 0:
                text = text[:idx]
        return text.strip()
    
    async def chat_completion(
        self,
        model_id: str,
        messages: list[dict],
        max_tokens: int = 128,
        temperature: float = 0.7,
        top_p: float = 0.9,
        **kwargs,
    ) -> dict:
        """Chat completion using robust Q&A prompt format."""
        model = self._get_model(model_id)
        
        async with self._locks[model_id]:
            self._generating[model_id] = True
            self._last_used[model_id] = time.time()
            try:
                loop = asyncio.get_running_loop()
                start = time.time()
                prompt = self._format_chat_prompt(messages)
                
                result = await loop.run_in_executor(
                    None,
                    lambda: model._llm(
                        prompt,
                        max_tokens=max_tokens,
                        temperature=temperature,
                        top_p=top_p,
                        repeat_penalty=1.15,
                        stop=["\nUser:", "\nSystem:", "\n\nUser", "\n\nSystem", "<|im_end|>", "<|im_start|>"],
                        stream=False,
                        **kwargs,
                    )
                )
                
                elapsed = time.time() - start
                raw = result["choices"][0]["text"]
                content = self._clean_chat_output(raw)
                token_count = result.get("usage", {}).get("completion_tokens", 0) or len(content.split())
                
                return {
                    "model": model_id,
                    "output": content,
                    "tokens_generated": token_count,
                    "elapsed_seconds": round(elapsed, 3),
                    "tokens_per_second": round(token_count / elapsed, 2) if elapsed > 0 else 0,
                }
            finally:
                self._generating[model_id] = False
    
    async def chat_completion_stream(
        self,
        model_id: str,
        messages: list[dict],
        max_tokens: int = 128,
        temperature: float = 0.7,
        top_p: float = 0.9,
        **kwargs,
    ) -> AsyncIterator[dict]:
        """Chat completion with streaming (robust Q&A format)."""
        model = self._get_model(model_id)
        
        async with self._locks[model_id]:
            self._generating[model_id] = True
            self._last_used[model_id] = time.time()
            try:
                prompt = self._format_chat_prompt(messages)
                stream = model._llm(
                    prompt,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    top_p=top_p,
                    repeat_penalty=1.15,
                    stop=["\nUser:", "\nSystem:", "\n\nUser", "\n\nSystem", "<|im_end|>", "<|im_start|>"],
                    stream=True,
                    **kwargs,
                )
                
                token_count = 0
                for chunk in stream:
                    if "choices" in chunk and len(chunk["choices"]) > 0:
                        text = chunk["choices"][0].get("text", "")
                        if text:
                            yield {
                                "token": text,
                                "index": token_count,
                                "done": False,
                            }
                            token_count += 1
                
                yield {
                    "token": "",
                    "index": token_count,
                    "done": True,
                }
            finally:
                self._generating[model_id] = False
    
    # ── Stats ────────────────────────────────────────────────────────
    
    async def get_stats(self, model_id: Optional[str] = None) -> dict:
        """Get stats for a specific model or all models."""
        if model_id:
            model = self._get_model(model_id)
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(None, model.get_stats)
        
        result = {}
        async with self._dict_lock:
            for mid, model in self._models.items():
                loop = asyncio.get_running_loop()
                result[mid] = await loop.run_in_executor(None, model.get_stats)
        return result
    
    async def list_models(self) -> list[ModelStatus]:
        """List all loaded and saved models."""
        models = []
        async with self._dict_lock:
            for mid in self._models:
                config = self._configs.get(mid, {})
                model = self._models[mid]
                models.append(ModelStatus(
                    id=mid,
                    path=config.get("model_path", ""),
                    loaded=True,
                    arch=getattr(model, "_get_arch", lambda: "unknown")(),
                    n_experts=getattr(model, "n_experts", 0),
                    buffer_mb=config.get("buffer_mb", 64),
                    last_used=(
                        time.strftime(
                            "%Y-%m-%dT%H:%M:%SZ",
                            time.gmtime(self._last_used[mid])
                        )
                        if mid in self._last_used else None
                    ),
                ))
        return models
    
    async def get_server_status(self) -> dict:
        """Get overall server status."""
        async with self._dict_lock:
            return {
                "models_loaded": len(self._models),
                "max_models": self._cfg.max_loaded_models,
                "queue_depth": self._cfg.request_queue_depth,
                "host": self._cfg.host,
                "port": self._cfg.port,
            }
    
    # ── Internal ─────────────────────────────────────────────────────
    
    def _get_model(self, model_id: str) -> WeightStreamModel:
        """Get a loaded model, raising if not found."""
        if model_id not in self._models:
            raise ValueError(f"Model '{model_id}' is not loaded. Use POST /v1/models/load first.")
        return self._models[model_id]
    
    async def _auto_cleanup(self):
        """Background task that unloads idle models."""
        while True:
            await asyncio.sleep(60)  # Check every 60 seconds
            timeout = self._cfg.idle_unload_timeout
            if timeout <= 0:
                continue
            
            now = time.time()
            to_unload = []
            
            async with self._dict_lock:
                for mid, last in self._last_used.items():
                    if (
                        not self._generating.get(mid, False)
                        and (now - last) > timeout
                    ):
                        to_unload.append(mid)
            
            for mid in to_unload:
                logger.info(f"Auto-unloading idle model: {mid}")
                await self.unload(mid)
            
            if not self._models:
                self._cleanup_task = None
                break
    
    async def shutdown(self):
        """Shutdown the manager: unload all models."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        
        ids = list(self._models.keys())
        for mid in ids:
            await self.unload(mid)
        
        logger.info("ModelManager shutdown complete")

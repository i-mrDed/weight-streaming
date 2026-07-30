"""
Model lifecycle manager for the weight-streaming API server.

Manages multiple WeightStreamModel instances:
- Load / unload / reload models by ID
- Track idle time for automatic cleanup
- Thread-safe generation delegation

Streaming design note (item 4):
llama-cpp-python iterators block the calling thread for the full per-token
compute. All streaming paths in this manager therefore consume them through
``_iter_blocking`` (worker thread + bounded queue), so the event loop stays
free for health checks, stats, and cancellation while a response generates.

Chat design note (item 5):
All streaming paths consume the model's public wrappers — ``stream_chat``
(chat) and ``stream_prompt`` (plain-prompt completions) — instead of
touching ``_llm`` directly, so generation stats, OS paging telemetry, and
page-cache sampling are recorded on every path.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import threading
import time
from typing import Any, AsyncIterator, Callable, Dict, Iterator, Optional

from ..backends.llama_cpp import WeightStreamModel
from ..core.exceptions import WeightStreamError, ModelError, GenerationError
from .config import get_config, ServerConfig
from .schemas import ModelStatus

logger = logging.getLogger(__name__)


class ModelManager:
    """
    Manages multiple WeightStreamModel instances.

    Thread safety: asyncio.Lock per model_id for generate()
    Access to _models dict is protected by _dict_lock.
    """

    def __init__(self, config: Optional[ServerConfig] = None):
        self._models: Dict[str, WeightStreamModel] = {}
        self._configs: Dict[str, dict] = {}  # saved configs for reload
        self._locks: Dict[str, asyncio.Lock] = {}
        self._last_used: Dict[str, float] = {}
        self._generating: Dict[str, bool] = {}

        self._dict_lock = asyncio.Lock()
        self._cleanup_task: Optional[asyncio.Task] = None

        # Keep the exact configuration supplied by the application factory.
        # This makes --n-threads and lifecycle settings apply to models loaded
        # later from the SPA as well as auto-loaded models.
        self._cfg = config or get_config()

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

    @staticmethod
    async def _iter_blocking(
        make_iterator: Callable[[], Iterator[Any]],
        queue_size: int = 16,
    ) -> AsyncIterator[Any]:
        """
        Adapt a blocking (synchronous) iterator to an async iterator that
        never blocks the asyncio event loop.

        llama-cpp-python returns plain generators whose ``next()`` does the
        full per-token compute on the calling thread. Iterating them from an
        event-loop coroutine freezes every other request (``/health``,
        ``/v1/stats``, cancellation) for the whole generation. This bridge
        runs the blocking iterator in a worker thread instead.

        - Bounded queue with backpressure: the worker waits (in 0.25 s
          slices) for room in the queue before producing more tokens.
        - Cooperative cancellation: when the consumer stops (client
          disconnect / task cancellation), the ``finally`` below sets the
          stop flag; the worker notices within ~0.25 s and stops iterating.
          llama.cpp streams are lazy, so stopping iteration also stops
          further token computation.
        - Errors raised inside the worker are re-raised in the consumer.
        """
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue(maxsize=queue_size)
        sentinel = object()
        stop = threading.Event()

        def send(item: Any) -> bool:
            """Thread-safe put with backpressure and cancellation slices."""
            try:
                fut = asyncio.run_coroutine_threadsafe(queue.put(item), loop)
            except RuntimeError:
                return False  # loop already closed
            while True:
                try:
                    fut.result(timeout=0.25)
                    return True
                except concurrent.futures.TimeoutError:
                    if stop.is_set():
                        fut.cancel()
                        return False
                except Exception:
                    return False  # consumer gone / loop shutting down

        def worker() -> None:
            try:
                for item in make_iterator():
                    if stop.is_set():
                        break
                    if not send(item):
                        break
            except Exception as ex:  # re-raised on the consumer side
                if not stop.is_set():
                    send(ex)
            finally:
                send(sentinel)

        loop.run_in_executor(None, worker)
        try:
            while True:
                item = await queue.get()
                if item is sentinel:
                    break
                if isinstance(item, BaseException):
                    raise item
                yield item
        finally:
            stop.set()

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

        The blocking llama.cpp iterator runs in a worker thread
        (see ``_iter_blocking``), keeping the event loop responsive.

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

                def make_stream() -> Iterator[str]:
                    # Runs in the worker thread. The plain-prompt path goes
                    # through the public WeightStreamModel wrapper, so
                    # generation stats and paging telemetry are recorded
                    # exactly like on the chat path.
                    return model.stream_prompt(
                        prompt,
                        max_tokens=max_tokens,
                        temperature=temperature,
                        top_p=top_p,
                        **kwargs,
                    )

                token_count = 0
                async for text in self._iter_blocking(make_stream):
                    yield {
                        "token": text,
                        "index": token_count,
                        "done": False,
                    }
                    token_count += 1

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
    def _estimate_tokens(text: str) -> int:
        """Estimate token count (approx 1 token ≈ 3-4 chars or word boundary)."""
        if not text:
            return 0
        return max(1, len(text) // 3)

    @classmethod
    def _fit_messages_to_context(
        cls,
        messages: list[dict],
        max_tokens: int,
        n_ctx: int,
    ) -> list[dict]:
        """
        Dynamically trim history to fit strict token budget:
        Budget = n_ctx - max_tokens - safety_margin (64)
        Always preserves system prompt and latest user message.
        """
        if not messages:
            return []

        safety_margin = 64
        budget = max(128, n_ctx - max_tokens - safety_margin)

        system_msg = None
        history_msgs = []
        latest_msg = messages[-1]

        for msg in messages[:-1]:
            if msg.get("role") == "system" and system_msg is None:
                system_msg = msg
            else:
                history_msgs.append(msg)

        system_tokens = cls._estimate_tokens(system_msg.get("content", "")) if system_msg else 0
        latest_tokens = cls._estimate_tokens(latest_msg.get("content", ""))
        used_tokens = system_tokens + latest_tokens

        packed_history = []
        for msg in reversed(history_msgs):
            cost = cls._estimate_tokens(msg.get("content", ""))
            if used_tokens + cost <= budget:
                packed_history.insert(0, msg)
                used_tokens += cost
            else:
                break

        result = []
        if system_msg:
            result.append(system_msg)
        result.extend(packed_history)
        result.append(latest_msg)
        return result

    async def chat_completion(
        self,
        model_id: str,
        messages: list[dict],
        max_tokens: int = 128,
        temperature: float = 0.7,
        top_p: float = 0.9,
        **kwargs,
    ) -> dict:
        """Chat completion (non-streaming) via the model's public wrapper."""
        model = self._get_model(model_id)

        async with self._locks[model_id]:
            self._generating[model_id] = True
            self._last_used[model_id] = time.time()
            try:
                loop = asyncio.get_running_loop()
                start = time.time()
                n_ctx = getattr(model, "n_ctx", 2048)
                fitted = self._fit_messages_to_context(messages, max_tokens, n_ctx)

                def produce() -> str:
                    # Runs in a worker thread: consume the wrapper's
                    # blocking chat stream and join the chunks. Native
                    # template + fallback handling live in the wrapper.
                    return "".join(
                        model.stream_chat(
                            messages=fitted,
                            max_tokens=max_tokens,
                            temperature=temperature,
                            top_p=top_p,
                            **kwargs,
                        )
                    ).strip()

                content = await loop.run_in_executor(None, produce)

                elapsed = time.time() - start
                stats = await loop.run_in_executor(None, model.get_stats)
                token_count = (
                    stats.get("generation", {}).get("token_count")
                    or self._estimate_tokens(content)
                )

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
        """
        Chat completion streaming via the model's public wrapper.

        The blocking wrapper iterator runs in a worker thread
        (see ``_iter_blocking``): health checks, stats, and cancellation
        stay responsive during a long response. On client disconnect the
        async generator is closed, the stop flag halts the worker, and the
        ``finally`` below always releases ``_generating`` and the lock.
        """
        model = self._get_model(model_id)

        async with self._locks[model_id]:
            self._generating[model_id] = True
            self._last_used[model_id] = time.time()
            try:
                n_ctx = getattr(model, "n_ctx", 2048)
                fitted = self._fit_messages_to_context(messages, max_tokens, n_ctx)

                def make_stream() -> Iterator[str]:
                    # Runs in the worker thread: native template first,
                    # prompt-formatter fallback — both inside the wrapper.
                    return model.stream_chat(
                        messages=fitted,
                        max_tokens=max_tokens,
                        temperature=temperature,
                        top_p=top_p,
                        **kwargs,
                    )

                token_count = 0
                async for text in self._iter_blocking(make_stream):
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

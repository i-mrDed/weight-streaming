"""Focused regression tests for local-server configuration and chat streaming.

Covers the item 4-5 reliability contract:
- local server defaults keep CPU headroom and keep models loaded
- the application factory passes its config to the ModelManager
- chat goes through the model's public stream_chat wrapper (never _llm)
- blocking iterators run off the event loop (worker-thread bridge)
- cancellation and mid-stream errors always release _generating and the lock
- WeightStreamModel.stream_chat native/fallback behavior and telemetry
"""

import asyncio
import contextlib
import os
import time

import pytest

from weight_stream.backends.llama_cpp import WeightStreamModel
from weight_stream.server.api_server import create_app
from weight_stream.server.config import ServerConfig
from weight_stream.server.model_manager import ModelManager


# -- Fakes -----------------------------------------------------------------


class _FakeLlamaEngine:
    """Mimics the llama_cpp.Llama surface used by WeightStreamModel.stream_chat."""

    def __init__(self, native_chunks=("Native ", "stream"), fail_native=False):
        self.native_chunks = list(native_chunks)
        self.fail_native = fail_native
        self.chat_requests = []
        self.prompt_requests = []

    def create_chat_completion(self, **kwargs):
        self.chat_requests.append(kwargs)
        if self.fail_native:
            raise RuntimeError("chat template not found")
        return iter(
            {"choices": [{"delta": {"content": c}}]} for c in self.native_chunks
        )

    def __call__(self, prompt, **kwargs):
        self.prompt_requests.append({"prompt": prompt, **kwargs})
        return iter({"choices": [{"text": c}]} for c in ("Fallback ", "reply"))


class _FakePageMonitor:
    def __init__(self):
        self.samples = 0

    def sample_resident_pages(self):
        self.samples += 1

    def get_resident_bytes(self):
        # Grows with each sample so residency-delta estimates are testable.
        return self.samples * 1024 * 1024

    def get_resident_ratio(self):
        return 0.0


def _bare_weight_stream_model(engine, arch="qwen2", page_monitor=None):
    """Build a WeightStreamModel without running the heavy __init__."""
    model = object.__new__(WeightStreamModel)
    model._llm = engine
    model._model_path = "fake.gguf"
    model._metadata = {"general.architecture": arch}
    model._page_monitor = page_monitor
    return model


class _FakeStreamModel:
    """Mimics the public WeightStreamModel contract used by ModelManager."""

    n_ctx = 2048

    def __init__(
        self,
        chunks=("Native ", "stream"),
        setup_error=None,
        iter_error_after=None,
        chunk_delay=0.0,
    ):
        self._chunks = list(chunks)
        self._setup_error = setup_error
        self._iter_error_after = iter_error_after
        self._chunk_delay = chunk_delay
        self.stream_requests = []
        self.prompt_requests = []

    def _get_arch(self):
        return "unknown"

    def get_stats(self):
        return {
            "generation": {
                "token_count": len(self._chunks),
                "tokens_per_sec": 42.0,
            }
        }

    def stream_chat(self, messages, max_tokens=128, temperature=0.7, top_p=0.9, **kwargs):
        self.stream_requests.append(
            {
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "top_p": top_p,
                "extra": kwargs,
            }
        )
        if self._setup_error is not None:
            raise self._setup_error
        for i, chunk in enumerate(self._chunks):
            if self._iter_error_after is not None and i == self._iter_error_after:
                raise RuntimeError("boom mid-stream")
            if self._chunk_delay:
                time.sleep(self._chunk_delay)  # simulate blocking compute
            yield chunk

    def stream_prompt(self, prompt, max_tokens=128, temperature=0.7, top_p=0.9, **kwargs):
        self.prompt_requests.append(
            {
                "prompt": prompt,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "top_p": top_p,
                "extra": kwargs,
            }
        )
        if self._setup_error is not None:
            raise self._setup_error
        for i, chunk in enumerate(self._chunks):
            if self._iter_error_after is not None and i == self._iter_error_after:
                raise RuntimeError("boom mid-stream")
            if self._chunk_delay:
                time.sleep(self._chunk_delay)
            yield chunk


def _register(manager, model_id, model):
    manager._models[model_id] = model
    manager._locks[model_id] = asyncio.Lock()
    manager._last_used[model_id] = 0
    manager._generating[model_id] = False


# -- Server configuration ---------------------------------------------------


def test_local_server_defaults_keep_cpu_headroom_and_model_loaded(monkeypatch):
    monkeypatch.delenv("WS_N_THREADS", raising=False)
    monkeypatch.delenv("WS_IDLE_TIMEOUT", raising=False)

    config = ServerConfig()

    assert config.default_n_threads == max(1, (os.cpu_count() or 4) // 2)
    assert config.idle_unload_timeout == 0


def test_application_factory_passes_its_config_to_model_manager():
    config = ServerConfig(default_n_threads=3, idle_unload_timeout=0)
    _, manager = create_app(config)

    assert manager._cfg is config
    assert manager._cfg.default_n_threads == 3


# -- Manager consumes the public wrapper, never _llm ------------------------


def test_chat_completion_uses_the_model_public_wrapper():
    manager = ModelManager(ServerConfig())
    model = _FakeStreamModel()
    _register(manager, "test", model)

    result = asyncio.run(
        manager.chat_completion(
            "test",
            [
                {"role": "system", "content": "Respond precisely."},
                {"role": "user", "content": "What is 2 + 2?"},
            ],
            max_tokens=32,
            temperature=0.2,
            top_p=0.8,
        )
    )

    assert result["output"] == "Native stream"
    request = model.stream_requests[0]
    assert request["messages"][-1] == {"role": "user", "content": "What is 2 + 2?"}
    assert request["top_p"] == 0.8
    assert request["temperature"] == 0.2
    assert result["tokens_generated"] == 2  # from the wrapper's real stats


def test_streaming_chat_reads_wrapper_chunks_and_marks_done():
    manager = ModelManager(ServerConfig())
    model = _FakeStreamModel()
    _register(manager, "test", model)

    async def collect():
        return [
            event
            async for event in manager.chat_completion_stream(
                "test", [{"role": "user", "content": "Hello"}], max_tokens=32
            )
        ]

    events = asyncio.run(collect())

    assert [event["token"] for event in events[:-1]] == ["Native ", "stream"]
    assert events[-1]["done"] is True
    assert model.stream_requests[0]["max_tokens"] == 32


def test_generate_stream_uses_public_prompt_wrapper():
    """Plain-prompt streaming must go through WeightStreamModel.stream_prompt
    (public wrapper), never model._llm, so stats/paging are recorded too."""
    manager = ModelManager(ServerConfig())
    model = _FakeStreamModel(chunks=("plain ", "prompt"))
    _register(manager, "test", model)

    async def collect():
        return [
            event
            async for event in manager.generate_stream(
                "test", "Once upon a time", max_tokens=24
            )
        ]

    events = asyncio.run(collect())

    assert [event["token"] for event in events[:-1]] == ["plain ", "prompt"]
    assert events[-1]["done"] is True
    assert model.prompt_requests, "stream_prompt wrapper was not used"
    assert model.prompt_requests[0]["prompt"] == "Once upon a time"
    assert model.prompt_requests[0]["max_tokens"] == 24
    assert not model.stream_requests, "chat wrapper must not be used here"


# -- Item 4: event loop stays responsive, cleanup is guaranteed -------------


def test_streaming_chat_offloads_blocking_iterator_from_event_loop():
    """While a slow blocking stream generates, the event loop must stay
    free to run other coroutines (health checks, stats, cancellation)."""
    manager = ModelManager(ServerConfig())
    # 8 chunks x 30ms of blocking "compute" inside the iterator
    model = _FakeStreamModel(chunks=[f"tok{i} " for i in range(8)], chunk_delay=0.03)
    _register(manager, "test", model)

    async def scenario():
        heartbeats = 0
        stop = asyncio.Event()

        async def heartbeat():
            nonlocal heartbeats
            while not stop.is_set():
                heartbeats += 1
                await asyncio.sleep(0.01)

        async def consume():
            return [
                event["token"]
                async for event in manager.chat_completion_stream(
                    "test", [{"role": "user", "content": "hi"}], max_tokens=32
                )
                if not event.get("done")
            ]

        hb_task = asyncio.create_task(heartbeat())
        tokens = await consume()
        stop.set()
        await hb_task
        return tokens, heartbeats

    tokens, heartbeats = asyncio.run(scenario())

    assert len(tokens) == 8
    # ~240ms of blocking generation with a 10ms heartbeat: if the iterator
    # ran on the event loop, heartbeats would be ~0. Demand a clear margin.
    assert heartbeats >= 10, f"event loop was blocked (heartbeats={heartbeats})"


def test_streaming_chat_cancellation_releases_generation_state():
    manager = ModelManager(ServerConfig())
    model = _FakeStreamModel(chunks=[f"tok{i} " for i in range(20)], chunk_delay=0.02)
    _register(manager, "test", model)

    async def scenario():
        gen = manager.chat_completion_stream(
            "test", [{"role": "user", "content": "hi"}], max_tokens=64
        )
        first = await gen.__anext__()
        assert first["token"] == "tok0 "
        # Client disconnect: the response generator is closed/cancelled.
        await gen.aclose()

    asyncio.run(scenario())

    assert manager._generating["test"] is False
    # The per-model lock must be free again (not held busy).
    assert not manager._locks["test"].locked()


def test_streaming_chat_midstream_error_releases_generation_state():
    manager = ModelManager(ServerConfig())
    model = _FakeStreamModel(chunks=["a", "b", "c"], iter_error_after=1)
    _register(manager, "test", model)

    async def collect():
        return [
            event
            async for event in manager.chat_completion_stream(
                "test", [{"role": "user", "content": "hi"}], max_tokens=32
            )
        ]

    try:
        asyncio.run(collect())
        raised = False
    except Exception as ex:
        raised = True
        assert "boom mid-stream" in str(ex)

    assert raised
    assert manager._generating["test"] is False
    assert not manager._locks["test"].locked()


# -- Item 5: WeightStreamModel.stream_chat contract -------------------------


def test_stream_chat_native_template_yields_deltas_and_records_stats():
    engine = _FakeLlamaEngine(native_chunks=["Hello", " world"])
    model = _bare_weight_stream_model(engine)

    chunks = list(
        model.stream_chat(
            [{"role": "user", "content": "Hi"}],
            max_tokens=16,
            temperature=0.3,
            top_p=0.85,
        )
    )

    assert chunks == ["Hello", " world"]
    request = engine.chat_requests[0]
    assert request["stream"] is True
    assert request["messages"] == [{"role": "user", "content": "Hi"}]
    assert request["top_p"] == 0.85
    stats = model._last_gen_stats
    assert stats["token_count"] == 2
    assert stats["tokens_per_sec"] > 0
    assert "Hi" in stats["prompt"]


def test_stream_chat_records_os_paging_demand():
    """stream_chat must attach real OS paging-demand telemetry (ADR-003 gap)."""
    from weight_stream.io.page_faults import page_fault_count

    if page_fault_count() is None:
        pytest.skip("no page-fault counter on this platform")

    engine = _FakeLlamaEngine(native_chunks=["a", "b", "c"])
    model = _bare_weight_stream_model(engine)

    assert list(model.stream_chat([{"role": "user", "content": "Hi"}])) == ["a", "b", "c"]

    paging = model._last_gen_stats["paging"]
    assert paging["faults"] >= 0
    assert paging["faults_per_token"] >= 0
    assert paging["fault_mb_per_token"] >= 0
    assert "note" in paging
    # Disk demand: present on POSIX (major faults) or when a page monitor
    # provides residency samples; absent on Windows without a monitor.
    if "disk_demand_mb" in paging:
        assert paging["disk_demand_mb"] >= 0
        assert paging["disk_demand_source"] in (
            "major_faults", "residency_growth_estimate")
        assert paging["disk_mb_per_token"] >= 0


def test_stream_chat_falls_back_to_prompt_formatter_when_native_fails():
    engine = _FakeLlamaEngine(fail_native=True)
    model = _bare_weight_stream_model(engine, arch="qwen2")

    chunks = list(
        model.stream_chat([{"role": "user", "content": "Hi there"}], max_tokens=16)
    )

    assert chunks == ["Fallback ", "reply"]
    assert engine.chat_requests, "native path must be attempted first"
    prompt = engine.prompt_requests[0]["prompt"]
    assert "system" in prompt and "user" in prompt
    stop = engine.prompt_requests[0]["stop"]
    assert len(stop) == 7
    assert stop[-1] == "<|eot_id|>"
    assert stop[-2] == "<|" + "im_start|>"
    assert stop[-3] == "<|" + "im_end|>"
    stats = model._last_gen_stats
    assert stats["token_count"] == 2


def test_stream_chat_samples_page_monitor_periodically():
    monitor = _FakePageMonitor()
    engine = _FakeLlamaEngine(native_chunks=[f"t{i}" for i in range(12)])
    model = _bare_weight_stream_model(engine, page_monitor=monitor)

    chunks = list(model.stream_chat([{"role": "user", "content": "Hi"}]))

    assert len(chunks) == 12
    # Samples at token 5 and 10, plus one final sample after the stream.
    assert monitor.samples == 3


def test_stream_chat_records_partial_stats_on_early_close():
    engine = _FakeLlamaEngine(native_chunks=["a", "b", "c", "d"])
    model = _bare_weight_stream_model(engine)

    stream = model.stream_chat([{"role": "user", "content": "Hi"}])
    assert next(stream) == "a"
    stream.close()  # simulate client cancellation mid-generation

    stats = model._last_gen_stats
    assert stats["token_count"] == 1
    assert stats["elapsed"] >= 0


"""Offline tests for Report-ISSUE-003: loading a 2nd llama-server model.

The llama-server backend owns ONE fixed backend port, so only one such
model can actually serve. Loading a second one used to register both as
loaded and fail at generate time with a port-collision error. Now the
manager evicts the idle first model (or fails fast when it is generating).

No subprocess is spawned: ``LlamaServerBackend.start()`` is lazy and the
tests only construct the backend (metadata parsing failure on a bogus path
degrades gracefully) — the pure helper and the manager's eviction plan are
what's under test.
"""

import asyncio
import pytest

from weight_stream.backends.llama_server import LlamaServerBackend
from weight_stream.core.exceptions import ModelError
from weight_stream.server.config import ServerConfig
from weight_stream.server.model_manager import ModelManager, _find_llama_server_conflict

FAKE_A = "C:/nonexistent/model-a.gguf"
FAKE_B = "C:/nonexistent/model-b.gguf"


def _server_backend(path=FAKE_A):
    return LlamaServerBackend(model_path=path)


class _CpuBackend:
    """Stand-in for the WeightStreamModel (CPU binding) — no server port."""

    def close(self):
        pass


# ── pure helper ───────────────────────────────────────────────────────


def test_conflict_returns_idle_server_model_for_eviction():
    models = {"a": _server_backend(), "b": _CpuBackend()}
    evict_id, blocked_id = _find_llama_server_conflict(models, {})
    assert evict_id == "a"
    assert blocked_id is None


def test_conflict_blocks_generating_server_model():
    models = {"a": _server_backend()}
    evict_id, blocked_id = _find_llama_server_conflict(models, {"a": True})
    assert evict_id is None
    assert blocked_id == "a"


def test_conflict_none_without_server_model():
    models = {"b": _CpuBackend()}
    assert _find_llama_server_conflict(models, {}) == (None, None)
    assert _find_llama_server_conflict({}, {}) == (None, None)


# ── manager end-to-end (asyncio.run, no spawn) ────────────────────────


def _manager() -> ModelManager:
    cfg = ServerConfig(
        lower_process_priority=False,
        idle_unload_timeout=0,
        max_loaded_models=4,
    )
    return ModelManager(cfg)


def _stub_create_backend(monkeypatch):
    """Deterministic backend factory — no file reads, no subprocess.

    The real _create_backend would construct WeightStreamModel for the CPU
    path (which validates the GGUF exists) or read metadata; stubbing it
    keeps the manager's conflict-planning logic the only thing under test.
    """

    def fake_create(self, model_path, **kwargs):
        if kwargs.get("use_llama_server", True):
            return LlamaServerBackend(model_path=model_path)
        return _CpuBackend()

    monkeypatch.setattr(ModelManager, "_create_backend", fake_create)


@pytest.fixture
def server_available(monkeypatch):
    monkeypatch.setattr(LlamaServerBackend, "is_available",
                        staticmethod(lambda: True))


def test_load_second_server_model_evicts_first(server_available, monkeypatch):
    _stub_create_backend(monkeypatch)

    async def go():
        mgr = _manager()
        await mgr.load("a", FAKE_A)
        assert "a" in mgr._models
        res = await mgr.load("b", FAKE_B)
        # The single-port model A was silently replaced by B.
        assert res["status"] == "loaded"
        assert res.get("evicted") == ["a"]
        assert "a" not in mgr._models
        assert "b" in mgr._models
        assert isinstance(mgr._models["b"], LlamaServerBackend)

    asyncio.run(go())


def test_load_fails_fast_when_server_model_generating(server_available,
                                                       monkeypatch):
    _stub_create_backend(monkeypatch)

    async def go():
        mgr = _manager()
        await mgr.load("a", FAKE_A)
        mgr._generating["a"] = True  # simulate an in-flight request
        with pytest.raises(ModelError, match="single-port.*generating"):
            await mgr.load("b", FAKE_B)
        # The generating model is untouched.
        assert "a" in mgr._models
        assert "b" not in mgr._models

    asyncio.run(go())


def test_cpu_backend_models_do_not_conflict(server_available, monkeypatch):
    # A CPU-binding model occupies no backend port — loading a server model
    # alongside it must NOT evict it.
    _stub_create_backend(monkeypatch)

    async def go():
        mgr = _manager()
        await mgr.load("cpu", FAKE_A, use_llama_server=False)
        await mgr.load("server", FAKE_B)
        assert "cpu" in mgr._models
        assert "server" in mgr._models

    asyncio.run(go())

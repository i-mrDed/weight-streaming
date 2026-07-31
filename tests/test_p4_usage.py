"""P4 tests: UsageRecorder (ring buffer + JSONL) and the ModelManager usage
hooks across all four generation paths, plus GET /v1/usage/history.

Offline-only; the fake model's get_stats() stands in for the backend so no
real GGUF is loaded.
"""

import asyncio
import json

from fastapi.testclient import TestClient

from weight_stream.server.api_server import create_app
from weight_stream.server.config import ServerConfig
from weight_stream.server.model_manager import ModelManager
from weight_stream.server.usage import UsageRecorder


# ── Fakes ─────────────────────────────────────────────────────────────


class _FakeModel:
    """Mimics the WeightStreamModel surface used by ModelManager."""

    n_ctx = 2048

    def __init__(self, chunks=("a", "b", "c"), gen_stats=None):
        self._chunks = list(chunks)
        # default: real-looking backend generation stats
        self._gen = gen_stats if gen_stats is not None else {
            "token_count": len(self._chunks),
            "tokens_per_sec": 42.0,
            "elapsed": 0.5,
            "paging": {"faults": 10, "faults_per_token": 1.0, "note": "verbose text"},
        }

    def _get_arch(self):
        return "qwen2"

    def close(self):
        pass

    def get_stats(self):
        return {"generation": dict(self._gen)}

    def stream_chat(self, messages, **k):
        yield from self._chunks

    def stream_prompt(self, prompt, **k):
        yield from self._chunks

    def generate(self, prompt, **k):
        return "".join(self._chunks)


def _register(mgr, model_id, model):
    mgr._models[model_id] = model  # noqa: SLF001
    mgr._locks[model_id] = asyncio.Lock()  # noqa: SLF001
    mgr._last_used[model_id] = 0  # noqa: SLF001
    mgr._generating[model_id] = False  # noqa: SLF001


def _run_all_four(mgr, mid="m"):
    async def go():
        await mgr.chat_completion(mid, [{"role": "user", "content": "hi"}])
        async for _ in mgr.chat_completion_stream(mid, [{"role": "user", "content": "hi"}]):
            pass
        await mgr.generate(mid, "hello")
        async for _ in mgr.generate_stream(mid, "hello"):
            pass
    asyncio.run(go())


# ── UsageRecorder unit ────────────────────────────────────────────────


def test_recorder_records_and_persists(tmp_path):
    path = tmp_path / "u.jsonl"
    rec = UsageRecorder(path)
    rec.record(model="m", tokens=5, tok_s=10.0, elapsed_s=0.5)
    assert len(rec) == 1
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["tokens"] == 5


def test_recorder_ring_caps_at_capacity(tmp_path):
    rec = UsageRecorder(tmp_path / "u.jsonl", capacity=3)
    for i in range(5):
        rec.record(model="m", tokens=i, tok_s=1.0, elapsed_s=0.1, ts=1000 + i)
    tokens = [r["tokens"] for r in rec.history()]
    assert tokens == [2, 3, 4]  # newest 3 kept, oldest dropped


def test_recorder_reload_tails_to_capacity(tmp_path):
    path = tmp_path / "u.jsonl"
    rec = UsageRecorder(path, capacity=10)
    for i in range(6):
        rec.record(model="m", tokens=i, tok_s=1.0, elapsed_s=0.1, ts=i)
    reloaded = UsageRecorder(path, capacity=4)
    assert len(reloaded) == 4
    assert [r["tokens"] for r in reloaded.history()] == [2, 3, 4, 5]


def test_recorder_limit_and_since(tmp_path):
    rec = UsageRecorder(tmp_path / "u.jsonl")
    for i in range(5):
        rec.record(model="m", tokens=i, tok_s=1.0, elapsed_s=0.1, ts=100 + i)
    assert [r["tokens"] for r in rec.history(limit=2)] == [3, 4]
    assert rec.history(limit=0) == []
    assert rec.history(limit=-1) == []
    assert [r["tokens"] for r in rec.history(since=103)] == [3, 4]


def test_recorder_summarizes_paging_and_keeps_tok_s_null(tmp_path):
    rec = UsageRecorder(tmp_path / "u.jsonl")
    rec.record(model="m", tokens=3, tok_s=None, elapsed_s=None,
               paging={"faults": 7, "faults_per_token": 2.0, "note": "drop me"})
    rec.record(model="m", tokens=4, tok_s=20.0, elapsed_s=0.2, paging=None)
    h = rec.history()
    assert h[0]["tok_s"] is None  # honest null, never fabricated
    assert h[0]["paging"] == {"faults": 7, "faults_per_token": 2.0}  # note dropped
    assert "paging" not in h[1]  # absent when no paging
    assert h[1]["tok_s"] == 20.0
    assert isinstance(h[0]["ts"], int)  # epoch ms


# ── ModelManager hooks ────────────────────────────────────────────────


def test_all_four_generation_paths_record_usage(tmp_path):
    rec = UsageRecorder(tmp_path / "u.jsonl")
    mgr = ModelManager(ServerConfig(), usage_recorder=rec)
    _register(mgr, "m", _FakeModel())
    _run_all_four(mgr)
    h = rec.history()
    assert len(h) == 4
    # the chat-streaming path must carry REAL tok_s (the P4 get_stats fix)
    assert all(r["tok_s"] == 42.0 for r in h)
    assert all(r["tokens"] == 3 for r in h)
    assert all(r["paging"]["faults"] == 10 for r in h)


def test_stream_without_backend_stats_records_null_tok_s(tmp_path):
    """Honest telemetry: a path with no real tokens/sec stores null, not a number."""
    rec = UsageRecorder(tmp_path / "u.jsonl")
    mgr = ModelManager(ServerConfig(), usage_recorder=rec)
    _register(mgr, "m", _FakeModel(gen_stats={}))  # no token_count / tokens_per_sec
    asyncio.run(mgr.chat_completion("m", [{"role": "user", "content": "hi"}]))
    r = rec.history()[-1]
    assert r["tok_s"] is None


def test_manager_without_recorder_reports_empty_history():
    mgr = ModelManager(ServerConfig())
    assert mgr.usage_history() == []
    assert mgr.usage_capacity() == 0


# ── GET /v1/usage/history endpoint ────────────────────────────────────


def test_usage_history_endpoint_returns_records(monkeypatch, tmp_path):
    monkeypatch.setenv("WS_USAGE_HISTORY_FILE", str(tmp_path / "usage.jsonl"))
    monkeypatch.setenv("WS_LOG_FILE", str(tmp_path / "server.log"))
    app, mgr = create_app(ServerConfig())
    _register(mgr, "m", _FakeModel())
    _run_all_four(mgr)
    with TestClient(app) as c:
        d = c.get("/v1/usage/history").json()
        assert d["count"] == 4
        assert d["capacity"] == 500
        assert d["history"][-1]["tok_s"] == 42.0
        limited = c.get("/v1/usage/history", params={"limit": 2}).json()
        assert limited["count"] == 2


def test_usage_history_endpoint_since_filter(monkeypatch, tmp_path):
    monkeypatch.setenv("WS_USAGE_HISTORY_FILE", str(tmp_path / "usage.jsonl"))
    monkeypatch.setenv("WS_LOG_FILE", str(tmp_path / "server.log"))
    app, mgr = create_app(ServerConfig())
    rec = mgr._usage  # noqa: SLF001
    for i in range(5):
        rec.record(model="m", tokens=i, tok_s=1.0, elapsed_s=0.1, ts=1000 + i)
    with TestClient(app) as c:
        d = c.get("/v1/usage/history", params={"since": 1003}).json()
        assert [r["tokens"] for r in d["history"]] == [3, 4]

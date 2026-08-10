"""Regression tests for the security/robustness findings from the OpenCode
review (2026-08-10). Every test FAILS against the pre-fix code and passes
after hardening:

- W1: ModelManager.load() eviction deadlocks (re-entrant asyncio.Lock)
- W2: CORS wildcard + credentials lets any website drive the local API
- W3: MCP server `command` accepted without an allowlist (RCE vector)
- W4: GGUF parse failure leaks the model mmap + file handle
- W5: assistant_id / issue_id path traversal (Windows %5C included)

Run:  python -m pytest tests/test_p4_security_hardening.py -v
"""

import asyncio
import mmap

import pytest
from fastapi.testclient import TestClient

from weight_stream.server.api_server import create_app
from weight_stream.server.config import ServerConfig
from weight_stream.server.model_manager import ModelManager


def _app(monkeypatch, tmp_path, **cfg):
    """App whose usage/log stores point at tmp (no repo pollution)."""
    monkeypatch.setenv("WS_USAGE_HISTORY_FILE", str(tmp_path / "usage.jsonl"))
    monkeypatch.setenv("WS_LOG_FILE", str(tmp_path / "server.log"))
    return create_app(ServerConfig(**cfg))


# ── W1: load() eviction deadlock ─────────────────────────────────────


def test_load_eviction_unloads_oldest_without_deadlock(monkeypatch):
    """Loading model #2 when max_loaded_models=1 must evict model #1.

    Pre-fix this HANGS forever (load() holds _dict_lock then calls
    unload(), which re-acquires the same asyncio.Lock — not reentrant).
    The wait_for timeout turns the hang into a test failure.
    """
    closed = []

    class _FakeModel:
        def __init__(self, **kwargs):
            pass

        def close(self):
            closed.append(True)

    monkeypatch.setattr(
        "weight_stream.server.model_manager.WeightStreamModel", _FakeModel
    )
    monkeypatch.setattr(
        "weight_stream.server.model_manager.lower_process_priority",
        lambda: True,
    )
    monkeypatch.setattr(
        "weight_stream.server.model_manager.restore_process_priority",
        lambda: True,
    )
    manager = ModelManager(ServerConfig(max_loaded_models=1))

    async def scenario():
        await manager.load("a", "fake.gguf", n_threads=2, use_llama_server=False)
        await manager.load("b", "fake.gguf", n_threads=2, use_llama_server=False)

    asyncio.run(asyncio.wait_for(scenario(), timeout=10))

    assert "b" in manager._models  # noqa: SLF001
    assert "a" not in manager._models  # noqa: SLF001
    assert closed, "evicted model was not closed"


def test_load_eviction_picks_oldest_idle_model(monkeypatch):
    """Eviction must unload the oldest NON-generating model and keep a busy
    one (the pre-existing selection rule, exercised without deadlock)."""
    monkeypatch.setattr(
        "weight_stream.server.model_manager.WeightStreamModel", _FakeModel
    )
    monkeypatch.setattr(
        "weight_stream.server.model_manager.lower_process_priority", lambda: True
    )
    monkeypatch.setattr(
        "weight_stream.server.model_manager.restore_process_priority", lambda: True
    )
    manager = ModelManager(ServerConfig(max_loaded_models=2))

    async def scenario():
        await manager.load("a", "fake.gguf", n_threads=2, use_llama_server=False)
        await manager.load("b", "fake.gguf", n_threads=2, use_llama_server=False)
        # Simulate "a" as most-recently-used, "b" idle; load "c" evicts "b".
        manager._last_used["a"] = 999.0  # noqa: SLF001
        manager._last_used["b"] = 1.0  # noqa: SLF001
        await manager.load("c", "fake.gguf", n_threads=2, use_llama_server=False)

    asyncio.run(asyncio.wait_for(scenario(), timeout=10))

    assert {"a", "c"} <= set(manager._models)  # noqa: SLF001
    assert "b" not in manager._models  # noqa: SLF001


class _FakeModel:
    def __init__(self, **kwargs):
        pass

    def close(self):
        pass


# ── W2: CORS hardening ───────────────────────────────────────────────


def test_cors_blocks_non_loopback_origin(monkeypatch, tmp_path):
    app, _ = _app(monkeypatch, tmp_path)
    with TestClient(app) as c:
        # Simple request from an evil origin: no CORS grant.
        r = c.get("/health", headers={"Origin": "http://evil.example"})
        assert r.status_code == 200
        assert "access-control-allow-origin" not in r.headers
        # Preflight from an evil origin: refused.
        r = c.options(
            "/v1/models",
            headers={
                "Origin": "http://evil.example",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert "access-control-allow-origin" not in r.headers


def test_cors_allows_loopback_origin(monkeypatch, tmp_path):
    app, _ = _app(monkeypatch, tmp_path)
    with TestClient(app) as c:
        r = c.get("/health", headers={"Origin": "http://localhost:8765"})
        assert (
            r.headers.get("access-control-allow-origin") == "http://localhost:8765"
        )


def test_cors_env_extra_origins(monkeypatch, tmp_path):
    monkeypatch.setenv("WS_CORS_ORIGINS", "http://192.168.1.50:8080")
    app, _ = _app(monkeypatch, tmp_path)
    with TestClient(app) as c:
        r = c.get("/health", headers={"Origin": "http://192.168.1.50:8080"})
        assert (
            r.headers.get("access-control-allow-origin")
            == "http://192.168.1.50:8080"
        )


# ── W3: MCP command allowlist ────────────────────────────────────────


def test_mcp_api_rejects_arbitrary_command(monkeypatch, tmp_path):
    app, _ = _app(monkeypatch, tmp_path)
    with TestClient(app) as c:
        r = c.post(
            "/v1/mcp/servers",
            json={
                "name": "evil",
                "transport": "stdio",
                "command": "cmd.exe",
                "args": ["/c", "calc"],
            },
        )
        assert r.status_code == 400
        # An absolute path to an arbitrary exe is refused too.
        r = c.post(
            "/v1/mcp/servers",
            json={
                "name": "evil2",
                "transport": "stdio",
                "command": "C:/Windows/System32/WindowsPowerShell/v1.0/powershell.exe",
            },
        )
        assert r.status_code == 400


def test_mcp_api_rejects_non_http_sse_url(monkeypatch, tmp_path):
    app, _ = _app(monkeypatch, tmp_path)
    with TestClient(app) as c:
        r = c.post(
            "/v1/mcp/servers",
            json={"name": "fileurl", "transport": "sse", "url": "file:///etc/passwd"},
        )
        assert r.status_code == 400


def test_mcp_validator_allowlist(tmp_path):
    from weight_stream.server.mcp_host import MCPHost, MCPServerStore, validate_mcp_server

    store = MCPServerStore(file_path=str(tmp_path / "mcp.json"))
    host = MCPHost(store=store)

    # Legitimate runners are allowed.
    validate_mcp_server({"id": "ok", "transport": "stdio", "command": "npx"})
    validate_mcp_server({"id": "ok2", "transport": "sse", "url": "https://mcp.example.com/sse"})

    # Arbitrary / path / traversal commands are refused.
    for bad in (
        {"id": "a", "command": "cmd.exe"},
        {"id": "b", "command": "C:/Windows/System32/cmd.exe"},
        {"id": "c", "command": "../evil"},
        {"id": "d", "command": "npx; calc"},
        {"id": "e", "command": "powershell.exe"},
    ):
        with pytest.raises(ValueError):
            validate_mcp_server({"id": bad["id"], "transport": "stdio", "command": bad["command"]})

    assert host  # (host construction is fine; call-tool path is tested elsewhere)


# ── W4: GGUF parse failure must release mmap + fd ────────────────────


def test_gguf_parse_failure_closes_mmap_and_file(monkeypatch, tmp_path):
    """A GGUF parse error in Step 3 must close the mmap + file opened in
    Step 1. Pre-fix the mapping is leaked (a >100 GB mapping per failed
    load) — the spy records that close() was never called."""
    model_path = tmp_path / "broken.gguf"
    model_path.write_bytes(b"not a real gguf file at all")

    mmap_instances = []
    real_mmap = mmap.mmap

    class _SpyMMap:
        def __init__(self, fileno, size, access=mmap.ACCESS_READ):
            self._inner = real_mmap(fileno, size, access=access)
            self.closed = False
            mmap_instances.append(self)

        def close(self):
            self.closed = True
            self._inner.close()

        def __getattr__(self, name):
            return getattr(self._inner, name)

    monkeypatch.setattr(mmap, "mmap", _SpyMMap)

    def boom(self, path):
        raise RuntimeError("parse boom")

    monkeypatch.setattr(
        "weight_stream.backends.llama_cpp.GGUFParser", boom
    )

    from weight_stream.backends.llama_cpp import WeightStreamModel
    from weight_stream.core.exceptions import ModelError

    with pytest.raises(ModelError):
        WeightStreamModel(model_path=str(model_path), buffer_mb=1, n_ctx=64, n_threads=2)

    assert mmap_instances, "Step 1 mmap was never created"
    assert mmap_instances[0].closed, "mmap leaked on GGUF parse failure (W4)"


# ── W5: path traversal via assistant_id / issue_id ───────────────────


def test_assistant_store_refuses_traversal_ids(tmp_path):
    from weight_stream.server.assistants import AssistantStore

    store = AssistantStore(directory=str(tmp_path))
    # A decoy OUTSIDE the store dir that a traversal would read/delete.
    outside = tmp_path.parent / "outside.json"
    outside.write_text('{"id": "pwned", "name": "PWNED"}', encoding="utf-8")

    for evil in (
        "../outside",
        "..\\outside",
        "..%5Coutside",
        "%2e%2e%5Coutside",
        "a/b",
        "a\\b",
        "",
    ):
        assert store.get(evil) is None, f"traversal read via {evil!r}"
        assert store.delete(evil) is False, f"traversal delete via {evil!r}"
        assert store.update(evil, name="x") is None, f"traversal update via {evil!r}"

    # A valid id still works end-to-end.
    a = store.create(name="ok")
    assert store.get(a["id"])["name"] == "ok"


def test_issue_store_refuses_traversal_ids(tmp_path):
    from weight_stream.issues.store import IssueStore

    store = IssueStore(base_dir=tmp_path)
    outside = tmp_path.parent / "outside.json"
    outside.write_text("{}", encoding="utf-8")

    for evil in ("../outside", "..\\outside", "..%5Coutside", "a/b", "a\\b"):
        assert store.get(evil) is None, f"traversal read via {evil!r}"
        # create() with a foreign id must refuse rather than write outside.
        from weight_stream.issues.models import Issue

        bad = Issue(
            id=evil, title="t", description="d",
            created_at="2026-01-01T00:00:00Z",
            updated_at="2026-01-01T00:00:00Z",
        )
        with pytest.raises(ValueError):
            store.create(bad)

    # Normal ids (Report-ISSUE-001 style) still work.
    issue = store.create(
        Issue(
            id="Report-ISSUE-001", title="t", description="d",
            created_at="2026-01-01T00:00:00Z",
            updated_at="2026-01-01T00:00:00Z",
        )
    )
    assert store.get("Report-ISSUE-001") is not None
    assert issue.id == "Report-ISSUE-001"

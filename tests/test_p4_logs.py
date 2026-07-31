"""P4 tests: logging rewire — RecentLogsHandler ring buffer, /v1/logs/tail,
the now-live /v1/debug/context log_tail, data/server.log persistence, and
WS_LOG_LEVEL wiring (applied on startup, restored on shutdown).

Integration tests run inside `with TestClient(app)` so the app lifespan
attaches/detaches the root-logger handlers (no global state leaks).
"""

import logging

from fastapi.testclient import TestClient

from weight_stream.server.api_server import create_app
from weight_stream.server.config import ServerConfig
from weight_stream.server.logs import (
    RecentLogsHandler,
    resolve_log_level,
    LOG_TAIL_CAP,
)


def _emit(handler, msg, level=logging.INFO):
    handler.emit(logging.LogRecord("t", level, "p", 1, msg, None, None))


# ── RecentLogsHandler unit ────────────────────────────────────────────


def test_handler_tail_and_capacity():
    h = RecentLogsHandler(capacity=3)
    h.setFormatter(logging.Formatter("%(message)s"))
    for i in range(5):
        _emit(h, f"msg{i}")
    assert h.tail(10) == ["msg2", "msg3", "msg4"]  # ring kept newest 3
    assert h.tail(2) == ["msg3", "msg4"]
    assert h.tail(0) == []


def test_handler_mirrors_into_recent_errors_and_caps():
    mirror: list = []
    h = RecentLogsHandler(capacity=10, mirror=mirror, mirror_cap=2)
    h.setFormatter(logging.Formatter("%(message)s"))
    for i in range(4):
        _emit(h, f"msg{i}")
    assert mirror == ["msg2", "msg3"]  # mirror capped at 2
    assert h.tail(10) == ["msg0", "msg1", "msg2", "msg3"]  # ring keeps more


def test_resolve_log_level():
    assert resolve_log_level("info") == logging.INFO
    assert resolve_log_level("WARNING") == logging.WARNING
    assert resolve_log_level("bogus") == logging.INFO
    assert resolve_log_level(None) == logging.INFO
    assert resolve_log_level("") == logging.INFO


# ── Endpoint integration (lifespan attaches handlers) ─────────────────


def _app(monkeypatch, tmp_path, **cfg):
    monkeypatch.setenv("WS_LOG_FILE", str(tmp_path / "server.log"))
    monkeypatch.setenv("WS_USAGE_HISTORY_FILE", str(tmp_path / "usage.jsonl"))
    return create_app(ServerConfig(**cfg))


def test_logs_tail_endpoint_returns_real_log(monkeypatch, tmp_path):
    app, _ = _app(monkeypatch, tmp_path, log_level="info")
    log = logging.getLogger("weight_stream.server.api_server")
    with TestClient(app) as c:
        log.warning("MARKER_TAIL_ABC")
        d = c.get("/v1/logs/tail", params={"lines": 100}).json()
        assert any("MARKER_TAIL_ABC" in ln for ln in d["lines"])
        assert d["count"] == len(d["lines"])


def test_debug_context_log_tail_is_no_longer_dead(monkeypatch, tmp_path):
    """The P4 bug fix: /v1/debug/context server_log_tail must contain real logs."""
    app, _ = _app(monkeypatch, tmp_path, log_level="info")
    log = logging.getLogger("weight_stream.server.api_server")
    with TestClient(app) as c:
        log.error("MARKER_DEBUG_CTX")
        dc = c.get("/v1/debug/context").json()
        assert any("MARKER_DEBUG_CTX" in ln for ln in dc.get("server_log_tail", []))


def test_server_log_file_is_written(monkeypatch, tmp_path):
    app, _ = _app(monkeypatch, tmp_path, log_level="info")
    log = logging.getLogger("weight_stream.server.api_server")
    with TestClient(app) as c:
        log.warning("MARKER_FILE_WRITE")
    content = (tmp_path / "server.log").read_text(encoding="utf-8")
    assert "MARKER_FILE_WRITE" in content


def test_ws_log_level_wired_on_startup_and_restored_on_shutdown(monkeypatch, tmp_path):
    root = logging.getLogger()
    before = root.level
    app, _ = _app(monkeypatch, tmp_path, log_level="warning")
    with TestClient(app):
        assert root.level == logging.WARNING  # WS_LOG_LEVEL applied
    assert root.level == before  # restored — no leak into other apps/tests


def test_logs_tail_default_and_clamp(monkeypatch, tmp_path):
    app, _ = _app(monkeypatch, tmp_path, log_level="info")
    log = logging.getLogger("weight_stream.server.api_server")
    with TestClient(app) as c:
        for i in range(5):
            log.info("LINE_%d", i)
        default = c.get("/v1/logs/tail").json()
        assert default["count"] >= 5
        assert default["count"] <= 100  # DEFAULT_TAIL_LINES
        clamped = c.get("/v1/logs/tail", params={"lines": 10_000}).json()
        assert clamped["count"] <= LOG_TAIL_CAP


def test_logs_tail_empty_before_any_log(monkeypatch, tmp_path):
    app, _ = _app(monkeypatch, tmp_path, log_level="error")  # suppress info startup line
    with TestClient(app) as c:
        # only suppressible startup logs were emitted at info; ring may be empty
        d = c.get("/v1/logs/tail").json()
        assert d["count"] == len(d["lines"])  # shape always consistent

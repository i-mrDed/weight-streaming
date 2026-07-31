"""P4 tests: Hugging Face Hub — filename parsing, the download target_dir
security guard, GGUF-only search (cached), atomic downloads with REAL
progress, cancel, size guards, and the /v1/hub/* endpoint contracts (incl. SSE).

Fully offline: DownloadManager's HTTP callables are injected (manager tests)
or monkeypatched at module level (endpoint tests). No real network is touched.
"""

import io
import json
import os
import threading

import pytest
from fastapi.testclient import TestClient

import weight_stream.server.hub as hubmod
from weight_stream.server.api_server import create_app
from weight_stream.server.config import ServerConfig
from weight_stream.server.hub import (
    DownloadManager,
    HubUpstreamError,
    HubValidationError,
    parse_quant,
    parse_size_label,
    _sanitize_filename,
    _resolve_target_dir,
)


# ── Fakes / fixtures ──────────────────────────────────────────────────

FAKE_SEARCH = [{
    "id": "org/qwen-gguf",
    "downloads": 100,
    "likes": 5,
    "lastModified": "2024-01-01",
    "siblings": [
        {"rfilename": "qwen-7b-q4_k_m.gguf"},
        {"rfilename": "qwen-7b-f16.gguf"},
        {"rfilename": "README.md"},          # must be filtered out
        {"rfilename": "qwen-7b-q8_0.gguf"},
    ],
}]


class FakeStream:
    def __init__(self, data: bytes, content_length=None):
        self._buf = io.BytesIO(data)
        self.content_length = content_length if content_length is not None else len(data)

    def read(self, n):
        return self._buf.read(n)

    def close(self):
        pass


class FailAfterStream(FakeStream):
    def __init__(self, data, fail_at):
        super().__init__(data)
        self._fail_at = fail_at

    def read(self, n):
        if self._buf.tell() >= self._fail_at:
            raise RuntimeError("net died")
        return self._buf.read(n)


@pytest.fixture
def models_dir(tmp_path, monkeypatch):
    d = tmp_path / "models"
    d.mkdir()
    monkeypatch.setenv("WS_MODELS_DIR", str(d))
    return d


def _mgr(fetch=None, stream=None):
    return DownloadManager(
        fetch_json=fetch or (lambda url, t: FAKE_SEARCH),
        open_stream=stream or (lambda url, t: FakeStream(b"G" * 3000)),
    )


def _app(monkeypatch, tmp_path, fetch=None, stream=None):
    monkeypatch.setenv("WS_USAGE_HISTORY_FILE", str(tmp_path / "u.jsonl"))
    monkeypatch.setenv("WS_LOG_FILE", str(tmp_path / "s.log"))
    monkeypatch.setattr(hubmod, "_default_fetch_json", fetch or (lambda u, t: FAKE_SEARCH))
    monkeypatch.setattr(hubmod, "_default_open_stream", stream or (lambda u, t: FakeStream(b"Z" * 500)))
    return create_app(ServerConfig())


# ── Filename parsing ──────────────────────────────────────────────────


@pytest.mark.parametrize("name,quant", [
    ("qwen2-7b-instruct-q4_k_m.gguf", "Q4_K_M"),
    ("model-q4_0.gguf", "Q4_0"),
    ("llama-8x7b-q8_0.gguf", "Q8_0"),
    ("model-F16.gguf", "F16"),
    ("mistral-bf16.gguf", "BF16"),
    ("phi.iq2_s.gguf", "IQ2_S"),
    ("no-quant-here.gguf", None),
])
def test_parse_quant(name, quant):
    assert parse_quant(name) == quant


@pytest.mark.parametrize("text,size", [
    ("qwen2-7b-gguf", "7B"),
    ("mixtral-8x7b", "8X7B"),
    ("tiny-1.5b-model", "1.5B"),
    ("no size here", None),
])
def test_parse_size_label(text, size):
    assert parse_size_label(text) == size


# ── Guard unit tests ──────────────────────────────────────────────────


def test_sanitize_filename_rules():
    assert _sanitize_filename("model.gguf") == "model.gguf"
    for bad in ["a/b.gguf", "a\\b.gguf", "..gguf", "../x.gguf", "model.bin", "", "a\x00b.gguf"]:
        with pytest.raises(HubValidationError) as ei:
            _sanitize_filename(bad)
        assert ei.value.status == 400


def test_resolve_target_dir_accepts_allowed_and_subdir(models_dir):
    allowed = [str(models_dir)]
    assert _resolve_target_dir(str(models_dir), allowed) == os.path.realpath(str(models_dir))
    sub = models_dir / "sub"
    sub.mkdir()
    assert _resolve_target_dir(str(sub), allowed) == os.path.realpath(str(sub))


def test_resolve_target_dir_rejects_outside(models_dir):
    allowed = [str(models_dir)]
    for bad in ["../../../etc", "/tmp", str(models_dir.parent.parent)]:
        with pytest.raises(HubValidationError) as ei:
            _resolve_target_dir(bad, allowed)
        assert ei.value.status == 403


def test_resolve_target_dir_symlink_escape_rejected(models_dir, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    link = models_dir / "link"
    try:
        os.symlink(outside, link, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable on this platform")
    with pytest.raises(HubValidationError) as ei:
        _resolve_target_dir(str(link), [str(models_dir)])
    assert ei.value.status == 403


# ── Search ────────────────────────────────────────────────────────────


def test_search_filters_to_gguf_and_parses_files():
    res = _mgr().search("qwen")
    assert res[0]["repo_id"] == "org/qwen-gguf"
    names = [f["filename"] for f in res[0]["files"]]
    assert "README.md" not in names  # GGUF-only filter
    assert names == ["qwen-7b-q4_k_m.gguf", "qwen-7b-f16.gguf", "qwen-7b-q8_0.gguf"]
    by_name = {f["filename"]: f for f in res[0]["files"]}
    assert by_name["qwen-7b-q4_k_m.gguf"]["quant"] == "Q4_K_M"
    assert by_name["qwen-7b-q4_k_m.gguf"]["size_label"] == "7B"


def test_search_is_cached_for_five_minutes():
    calls = {"n": 0}

    def counting(url, t):
        calls["n"] += 1
        return FAKE_SEARCH

    mgr = DownloadManager(fetch_json=counting, open_stream=lambda u, t: FakeStream(b""))
    mgr.search("q")
    mgr.search("q")
    mgr.search("q", sort="likes")  # different key → new fetch
    assert calls["n"] == 2


def test_search_upstream_failure_raises_honest_error():
    def boom(url, t):
        raise RuntimeError("dns failure")

    mgr = DownloadManager(fetch_json=boom, open_stream=lambda u, t: FakeStream(b""))
    with pytest.raises(HubUpstreamError) as ei:
        mgr.search("x")
    assert "dns failure" in str(ei.value)


# ── Downloads (manager-level, deterministic) ──────────────────────────


def test_download_is_atomic_with_real_progress(models_dir):
    mgr = _mgr(stream=lambda u, t: FakeStream(b"G" * 3000, content_length=3000))
    task = mgr.create_download("org/qwen-gguf", "qwen-7b-q4_k_m.gguf", str(models_dir))
    mgr.run_download(task)
    final = models_dir / "qwen-7b-q4_k_m.gguf"
    assert task.status == "done"
    assert final.read_bytes() == b"G" * 3000
    assert not (models_dir / "qwen-7b-q4_k_m.gguf.part").exists()  # atomic: no leftover
    d = task.to_dict()
    assert d["percent"] == 100.0
    assert d["bytes_downloaded"] == 3000
    assert d["total_bytes"] == 3000
    assert d["speed_bps"] and d["speed_bps"] > 0  # real, not fabricated


def test_download_failure_cleans_up_part(models_dir):
    mgr = _mgr(stream=lambda u, t: FailAfterStream(b"X" * 3000, fail_at=1000))
    task = mgr.create_download("org/m", "fail.gguf", str(models_dir))
    mgr.run_download(task)
    assert task.status == "failed"
    assert "net died" in task.error
    assert not (models_dir / "fail.gguf").exists()       # no corrupt final
    assert not (models_dir / "fail.gguf.part").exists()  # part removed


def test_download_cancel_while_queued(models_dir):
    mgr = _mgr()
    task = mgr.create_download("org/m", "c.gguf", str(models_dir))
    mgr.cancel(task.id)
    assert task.status == "cancelled"
    # running a cancelled task is a no-op that writes nothing
    mgr.run_download(task)
    assert task.status == "cancelled"
    assert not (models_dir / "c.gguf").exists()


def test_download_rejected_target_writes_nothing(models_dir):
    mgr = _mgr()
    with pytest.raises(HubValidationError):
        mgr.create_download("org/m", "x.gguf", "../../../etc")
    assert list(models_dir.iterdir()) == []  # nothing created


def test_size_guard_max_bytes(monkeypatch, models_dir):
    monkeypatch.setenv("WS_HUB_MAX_BYTES", "100")
    mgr = _mgr(stream=lambda u, t: FakeStream(b"X" * 3000, content_length=3000))
    task = mgr.create_download("org/m", "big.gguf", str(models_dir))
    mgr.run_download(task)
    assert task.status == "failed"
    assert "WS_HUB_MAX_BYTES" in task.error
    assert not (models_dir / "big.gguf").exists()
    assert not (models_dir / "big.gguf.part").exists()


def test_size_guard_insufficient_disk(monkeypatch, models_dir):
    class _Usage:
        free = 10  # bytes

    monkeypatch.setattr(hubmod.shutil, "disk_usage", lambda p: _Usage())
    mgr = _mgr(stream=lambda u, t: FakeStream(b"X" * 3000, content_length=3000))
    task = mgr.create_download("org/m", "big.gguf", str(models_dir))
    mgr.run_download(task)
    assert task.status == "failed"
    assert "disk space" in task.error
    assert not (models_dir / "big.gguf").exists()


# ── Endpoint contracts ────────────────────────────────────────────────


def test_hub_search_endpoint_filters_and_parses(models_dir, monkeypatch, tmp_path):
    app, _ = _app(monkeypatch, tmp_path)
    with TestClient(app) as c:
        r = c.get("/v1/hub/search", params={"q": "qwen"})
        assert r.status_code == 200
        body = r.json()
        assert body["count"] == 1
        assert body["results"][0]["files"][0]["quant"] == "Q4_K_M"


def test_hub_search_endpoint_502_when_upstream_down(models_dir, monkeypatch, tmp_path):
    def boom(u, t):
        raise RuntimeError("down")

    app, _ = _app(monkeypatch, tmp_path, fetch=boom)
    with TestClient(app) as c:
        assert c.get("/v1/hub/search", params={"q": "x"}).status_code == 502


def test_hub_download_endpoint_guard(models_dir, monkeypatch, tmp_path):
    app, _ = _app(monkeypatch, tmp_path)
    with TestClient(app) as c:
        r = c.post("/v1/hub/download", json={
            "repo_id": "org/m", "filename": "m-q4_0.gguf", "target_dir": "../../../etc"})
        assert r.status_code == 403
        r = c.post("/v1/hub/download", json={"repo_id": "org/m", "filename": "bad.txt"})
        assert r.status_code == 400


def test_hub_download_endpoint_202_and_listed(models_dir, monkeypatch, tmp_path):
    app, _ = _app(monkeypatch, tmp_path)
    with TestClient(app) as c:
        r = c.post("/v1/hub/download", json={
            "repo_id": "org/m", "filename": "m-q4_0.gguf", "target_dir": str(models_dir)})
        assert r.status_code == 202
        task = r.json()
        assert task["id"].startswith("dl-")
        listed = c.get("/v1/hub/downloads").json()
        assert any(d["id"] == task["id"] for d in listed["downloads"])


def test_hub_progress_and_cancel_404_for_unknown(models_dir, monkeypatch, tmp_path):
    app, _ = _app(monkeypatch, tmp_path)
    with TestClient(app) as c:
        assert c.get("/v1/hub/progress/nope").status_code == 404
        assert c.post("/v1/hub/download/nope/cancel").status_code == 404


def test_hub_cancel_endpoint_cancels_task(models_dir, monkeypatch, tmp_path):
    app, _ = _app(monkeypatch, tmp_path)
    with TestClient(app) as c:
        hub_mgr = app.state.hub_manager
        task = hub_mgr.create_download("org/m", "m-q4_0.gguf", str(models_dir))  # stays queued
        r = c.post(f"/v1/hub/download/{task.id}/cancel")
        assert r.status_code == 200
        assert r.json()["status"] == "cancelled"


def test_hub_progress_sse_streams_real_progress(models_dir, monkeypatch, tmp_path):
    app, _ = _app(monkeypatch, tmp_path)  # open_stream → 500-byte FakeStream
    with TestClient(app) as c:
        hub_mgr = app.state.hub_manager
        task = hub_mgr.create_download("org/m", "m-q4_0.gguf", str(models_dir))
        th = threading.Thread(target=hub_mgr.run_download, args=(task,))
        th.start()
        r = c.get(f"/v1/hub/progress/{task.id}")  # polls until terminal
        th.join(timeout=5)
        assert r.status_code == 200
        frames = [
            json.loads(line[len("data:"):].strip())
            for line in r.text.splitlines() if line.startswith("data:")
        ]
        assert frames, "SSE stream produced no frames"
        assert frames[-1]["status"] == "done"
        assert frames[-1]["percent"] == 100.0
        assert frames[-1]["bytes_downloaded"] == 500
        assert (models_dir / "m-q4_0.gguf").read_bytes() == b"Z" * 500

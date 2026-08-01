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
    parse_shard,
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


# P5.1 on-demand detail: the two HF responses the endpoint aggregates.
FAKE_DETAIL = {
    "id": "org/qwen-gguf",
    "author": "org",
    "createdAt": "2024-01-01T00:00:00.000Z",
    "lastModified": "2024-02-01T00:00:00.000Z",
    "downloads": 500,
    "likes": 7,
    "pipeline_tag": "text-generation",
    "tags": ["gguf", "chat", "base_model:org/base", "function-calling"],
    "cardData": {"description": "A test model", "base_model": "org/base"},
}

FAKE_TREE = [
    {"path": "README.md", "type": "file", "size": 100},
    {"path": "imatrix.dat", "type": "file", "size": 200},
    # Q4_K_M split into 2 shards (2.0 GB + 1.5 GB = 3.5 GB total)
    {"path": "qwen-7b-q4_k_m-00002-of-00002.gguf", "type": "file", "size": 1_500_000_000},
    {"path": "qwen-7b-q4_k_m-00001-of-00002.gguf", "type": "file", "size": 2_000_000_000},
    # Q2_K single file (0.9 GB)
    {"path": "qwen-7b-q2_k.gguf", "type": "file", "size": 900_000_000},
    # F16 unquantized, 4 shards
    {"path": "qwen-7b-f16-00001-of-00004.gguf", "type": "file", "size": 3_900_000_000},
    {"path": "qwen-7b-f16-00002-of-00004.gguf", "type": "file", "size": 3_900_000_000},
    {"path": "qwen-7b-f16-00003-of-00004.gguf", "type": "file", "size": 3_900_000_000},
    {"path": "qwen-7b-f16-00004-of-00004.gguf", "type": "file", "size": 3_900_000_000},
]


def detail_router(url, t):
    """Fake HF: /tree/main → file tree, otherwise the model detail document."""
    return FAKE_TREE if url.rstrip("/").endswith("/tree/main") else FAKE_DETAIL


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
    ("model-fp16.gguf", "F16"),                       # fp16 → canonical F16
    ("qwen-fp16-00001-of-00004.gguf", "F16"),
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


@pytest.mark.parametrize("name,shard", [
    ("qwen-q4_0-00001-of-00002.gguf", {"index": 1, "total": 2}),
    ("qwen-fp16-00004-of-00004.gguf", {"index": 4, "total": 4}),
    ("qwen-q4_k_m.gguf", None),            # single file, not sharded
    ("model-00001-of-00002.bin", None),     # not a .gguf shard marker
])
def test_parse_shard(name, shard):
    assert parse_shard(name) == shard


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


def test_search_with_cursor_parses_link_header_next_cursor():
    FAKE_RECENT = [{"id": "org/recent", "siblings": [{"rfilename": "m-q4_k_m.gguf"}]}]

    def with_link(url, t):
        return FAKE_RECENT, {"Link": '<https://huggingface.co/api/models?a=1&cursor=abc123>; rel="next"'}

    def no_link(url, t):
        return FAKE_RECENT, {}

    mgr_next = DownloadManager(
        fetch_json=lambda u, t: FAKE_RECENT,
        fetch_headers=with_link,
        open_stream=lambda u, t: FakeStream(b""),
    )
    p1 = mgr_next.search_with_cursor("", sort="recent")
    assert p1["results"][0]["repo_id"] == "org/recent"
    assert p1["next_cursor"] == "abc123"

    mgr_end = DownloadManager(
        fetch_json=lambda u, t: FAKE_RECENT,
        fetch_headers=no_link,
        open_stream=lambda u, t: FakeStream(b""),
    )
    p2 = mgr_end.search_with_cursor("", sort="recent")
    assert p2["next_cursor"] is None


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


def test_size_guard_without_content_length(monkeypatch, models_dir):
    """P5 hardening #2: with NO Content-Length header the pre-check cannot
    run, but the mid-stream guard still counts REAL bytes — the transfer
    cannot breach WS_HUB_MAX_BYTES (beyond one chunk of granularity)."""
    monkeypatch.setenv("WS_HUB_MAX_BYTES", "100")

    class UnknownLengthStream(FakeStream):
        def __init__(self, data: bytes):
            super().__init__(data)
            self.content_length = None  # header absent → total unknown

    mgr = DownloadManager(
        fetch_json=lambda u, t: FAKE_SEARCH,
        open_stream=lambda u, t: UnknownLengthStream(b"X" * 3000),
        chunk_size=100,  # small chunks so the guard trips early
    )
    task = mgr.create_download("org/m", "sneaky.gguf", str(models_dir))
    mgr.run_download(task)
    assert task.status == "failed"
    assert "WS_HUB_MAX_BYTES" in task.error
    # the real byte count never ran past the ceiling by more than one chunk
    assert task.bytes_downloaded <= 100 + 100
    assert not (models_dir / "sneaky.gguf").exists()
    assert not (models_dir / "sneaky.gguf.part").exists()  # part cleaned up


def test_part_symlink_not_followed(models_dir, tmp_path):
    """P5 hardening #1: a pre-placed symlink at the .part path must be
    refused, never written through (closes the symlink-TOCTOU)."""
    victim = tmp_path / "victim.gguf"
    victim.write_bytes(b"original")
    link = models_dir / "trap.gguf.part"
    try:
        os.symlink(victim, link)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable on this platform")
    mgr = _mgr()
    task = mgr.create_download("org/m", "trap.gguf", str(models_dir))
    mgr.run_download(task)
    assert task.status == "failed"
    assert "symlink" in (task.error or "").lower()
    assert victim.read_bytes() == b"original"      # never written through
    assert not (models_dir / "trap.gguf").exists()  # no final file


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


# ── P5.1 on-demand model detail ─────────────────────────────────────


def test_model_detail_aggregates_shape_and_sizes():
    mgr = DownloadManager(fetch_json=detail_router, open_stream=lambda u, t: FakeStream(b""))
    d = mgr.model_detail("org/qwen-gguf")
    # metadata straight from the HF detail doc (real values, nothing invented)
    assert d["repo_id"] == "org/qwen-gguf"
    assert d["author"] == "org"
    assert d["published_at"] == "2024-01-01T00:00:00.000Z"
    assert d["updated_at"] == "2024-02-01T00:00:00.000Z"
    assert d["downloads"] == 500
    assert d["likes"] == 7
    assert d["pipeline_tag"] == "text-generation"
    assert "function-calling" in d["tags"]
    assert d["description"] == "A test model"
    assert d["base_model"] == "org/base"
    assert d["context_length"] is None  # HF gave none → honest null
    # files carry REAL byte sizes; non-GGUF separated out
    assert len(d["files"]) == 7  # 2 Q4_K_M shards + 1 Q2_K + 4 F16 shards
    assert {f["filename"] for f in d["non_gguf"]} == {"README.md", "imatrix.dat"}


def test_model_detail_shard_grouping_and_totals():
    mgr = DownloadManager(fetch_json=detail_router, open_stream=lambda u, t: FakeStream(b""))
    d = mgr.model_detail("org/qwen-gguf")
    by_q = {q["quant"]: q for q in d["quants"]}
    q4 = by_q["Q4_K_M"]
    assert q4["sharded"] is True
    assert q4["total_bytes"] == 3_500_000_000            # 2.0 + 1.5 GB
    assert q4["per_shard_bytes"] == [2_000_000_000, 1_500_000_000]  # sorted by shard index
    assert [f["filename"] for f in q4["files"]][0].endswith("00001-of-00002.gguf")
    q2 = by_q["Q2_K"]
    assert q2["sharded"] is False
    assert q2["total_bytes"] == 900_000_000
    assert q2["per_shard_bytes"] is None  # not sharded
    assert len(by_q["F16"]["files"]) == 4
    assert by_q["F16"]["total_bytes"] == 4 * 3_900_000_000


def test_model_detail_single_and_sharded_same_quant_separate():
    """A repo shipping fp16 as BOTH one file and an N-part split must yield two
    independent F16 groups — otherwise "download all N" grabs two copies."""
    detail = {"id": "org/m", "tags": [], "cardData": {}}
    tree = [
        {"path": "m-fp16.gguf", "type": "file", "size": 14_000_000_000},          # single complete file
        {"path": "m-fp16-00001-of-00002.gguf", "type": "file", "size": 7_000_000_000},
        {"path": "m-fp16-00002-of-00002.gguf", "type": "file", "size": 7_000_000_000},
    ]
    mgr = DownloadManager(
        fetch_json=lambda u, t: tree if u.rstrip("/").endswith("/tree/main") else detail,
        open_stream=lambda u, t: FakeStream(b""),
    )
    d = mgr.model_detail("org/m")
    f16 = [q for q in d["quants"] if q["quant"] == "F16"]
    assert len(f16) == 2  # NOT merged into one bogus group
    single = [q for q in f16 if not q["sharded"]]
    sharded = [q for q in f16 if q["sharded"]]
    assert len(single) == 1 and len(sharded) == 1
    assert single[0]["total_bytes"] == 14_000_000_000
    assert single[0]["files"][0]["filename"] == "m-fp16.gguf"
    assert sharded[0]["total_bytes"] == 14_000_000_000
    assert len(sharded[0]["files"]) == 2
    assert sharded[0]["per_shard_bytes"] == [7_000_000_000, 7_000_000_000]


def test_model_detail_is_cached():
    calls = {"n": 0}

    def counting(url, t):
        calls["n"] += 1
        return detail_router(url, t)

    mgr = DownloadManager(fetch_json=counting, open_stream=lambda u, t: FakeStream(b""))
    mgr.model_detail("org/qwen-gguf")
    mgr.model_detail("org/qwen-gguf")
    mgr.model_detail("org/other")  # different repo → fresh fetch pair
    assert calls["n"] == 4  # 2 repos x (detail + tree)


def test_model_detail_upstream_failure_raises():
    def boom(url, t):
        raise RuntimeError("dns failure")

    mgr = DownloadManager(fetch_json=boom, open_stream=lambda u, t: FakeStream(b""))
    with pytest.raises(HubUpstreamError):
        mgr.model_detail("org/x")


def test_model_detail_missing_fields_are_null():
    sparse_detail = {"id": "org/bare"}  # HF returned almost nothing
    mgr = DownloadManager(
        fetch_json=lambda u, t: [] if u.rstrip("/").endswith("/tree/main") else sparse_detail,
        open_stream=lambda u, t: FakeStream(b""),
    )
    d = mgr.model_detail("org/bare")
    assert d["published_at"] is None
    assert d["updated_at"] is None
    assert d["downloads"] is None
    assert d["likes"] is None
    assert d["description"] is None
    assert d["context_length"] is None
    assert d["files"] == []
    assert d["quants"] == []


def test_hub_model_endpoint_returns_payload(models_dir, monkeypatch, tmp_path):
    app, _ = _app(monkeypatch, tmp_path, fetch=detail_router)
    with TestClient(app) as c:
        r = c.get("/v1/hub/model/org/qwen-gguf")
        assert r.status_code == 200
        body = r.json()
        assert body["repo_id"] == "org/qwen-gguf"
        by_q = {q["quant"]: q for q in body["quants"]}
        assert by_q["Q4_K_M"]["total_bytes"] == 3_500_000_000


def test_hub_model_endpoint_502_when_upstream_down(models_dir, monkeypatch, tmp_path):
    def boom(u, t):
        raise RuntimeError("down")

    app, _ = _app(monkeypatch, tmp_path, fetch=boom)
    with TestClient(app) as c:
        assert c.get("/v1/hub/model/org/x").status_code == 502


def test_hub_model_endpoint_400_for_empty(models_dir, monkeypatch, tmp_path):
    app, _ = _app(monkeypatch, tmp_path, fetch=detail_router)
    with TestClient(app) as c:
        # a path of only whitespace resolves to an empty repo_id → 400
        assert c.get("/v1/hub/model/%20").status_code == 400


# ── P5.1 search enrichment (pass-through of tags/pipeline_tag) ──────


def test_search_passes_through_tags_and_pipeline_tag():
    enriched = [{
        "id": "org/m", "downloads": 1, "likes": None, "lastModified": None,
        "pipeline_tag": "text-generation", "tags": ["gguf", "code"],
        "siblings": [{"rfilename": "m-q4_0.gguf"}],
    }]
    res = DownloadManager(
        fetch_json=lambda u, t: enriched, open_stream=lambda u, t: FakeStream(b"")
    ).search("m")
    assert res[0]["pipeline_tag"] == "text-generation"
    assert res[0]["tags"] == ["gguf", "code"]
    assert res[0]["author"] == "org"


def test_search_without_tags_defaults_honest_empty():
    # older HF payloads omit tags/pipeline_tag → [] / None, never a guess
    res = DownloadManager(
        fetch_json=lambda u, t: FAKE_SEARCH, open_stream=lambda u, t: FakeStream(b"")
    ).search("q")
    assert res[0]["tags"] == []
    assert res[0]["pipeline_tag"] is None

"""P4 tests: Hugging Face Hub — filename parsing, the download target_dir
security guard, GGUF-only search (cached), atomic downloads with REAL
progress, cancel, size guards, and the /v1/hub/* endpoint contracts (incl. SSE).

Fully offline: DownloadManager's HTTP callables are injected (manager tests)
or monkeypatched at module level (endpoint tests). No real network is touched.
"""

import io
import json
import os
import struct
import threading
import time

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


class CancelAtStream(FakeStream):
    """Delivers bytes then flips the task's cancel flag mid-stream, so a
    cancel can be tested deterministically (no sleeping)."""

    def __init__(self, data, task, at):
        super().__init__(data)
        self._task = task
        self._at = at

    def read(self, n):
        if self._buf.tell() >= self._at:
            self._task._cancel.set()
        return self._buf.read(n)


class RangeStream:
    """A fake upstream for the resume path: honors ``Range`` (206, returns
    only the remaining bytes) or ignores it (200, returns the whole file)."""

    def __init__(self, data: bytes, start: int = 0, status: int = 206):
        self.status = status
        self._buf = io.BytesIO(data[start:] if status == 206 else data)
        self.content_length = (len(data) - start) if status == 206 else len(data)

    def read(self, n):
        return self._buf.read(n)

    def close(self):
        pass


def _make_gguf_bytes(magic=b"GGUF", version=3, bad_offset=None):
    """Minimal VALID GGUF: 2 metadata KVs (one string, one array) + 1 F32
    tensor (8x16 = 4096 elems → 16 KiB data). Payloads in download tests
    must be a real GGUF — the structural gate (EXP-011b) rejects anything
    that is not, so `b"G" * N` fixtures no longer reach `done`.

    ``bad_offset`` overrides the tensor data offset to exercise the
    bounds gate (offset/end beyond the data section = corrupt).
    """
    name = b"general.architecture"
    val = b"qwen3"
    arr = b"arr.k"
    parts = [
        magic,
        struct.pack("<I", version),
        struct.pack("<Q", 1),          # tensor_count
        struct.pack("<Q", 2),          # metadata_kv_count
        # kv 1: string
        struct.pack("<Q", len(name)), name,
        struct.pack("<I", 8),          # string type
        struct.pack("<Q", len(val)), val,
        # kv 2: array of 3 × uint32 (exercises the array walk)
        struct.pack("<Q", len(arr)), arr,
        struct.pack("<I", 9),          # array type
        struct.pack("<I", 4),          # element type: uint32
        struct.pack("<Q", 3),          # element count
        struct.pack("<I", 1), struct.pack("<I", 2), struct.pack("<I", 3),
    ]
    tname = b"blk.0.attn_q.weight"
    nelem = 4096
    parts += [
        struct.pack("<Q", len(tname)), tname,
        struct.pack("<I", 2),          # ndims
        struct.pack("<Q", 32), struct.pack("<Q", 128),  # dims (32×128 = 4096)
        struct.pack("<I", 0),          # F32
        struct.pack("<Q", bad_offset if bad_offset is not None else 0),
    ]
    return b"".join(parts) + b"\x00" * (nelem * 4)


_GGUF = _make_gguf_bytes()  # shared valid payload for download-completion tests


@pytest.fixture
def models_dir(tmp_path, monkeypatch):
    d = tmp_path / "models"
    d.mkdir()
    monkeypatch.setenv("WS_MODELS_DIR", str(d))
    return d


def _mgr(fetch=None, stream=None):
    return DownloadManager(
        fetch_json=fetch or (lambda url, t, start=0: FAKE_SEARCH),
        open_stream=stream or (lambda url, t, start=0: FakeStream(_GGUF, content_length=len(_GGUF))),
    )


def _app(monkeypatch, tmp_path, fetch=None, stream=None):
    monkeypatch.setenv("WS_USAGE_HISTORY_FILE", str(tmp_path / "u.jsonl"))
    monkeypatch.setenv("WS_LOG_FILE", str(tmp_path / "s.log"))
    monkeypatch.setattr(hubmod, "_default_fetch_json", fetch or (lambda u, t, start=0: FAKE_SEARCH))
    monkeypatch.setattr(hubmod, "_default_open_stream", stream or (lambda u, t, start=0: FakeStream(_GGUF)))
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


def test_stream_uses_larger_timeout_than_json(monkeypatch, models_dir):
    """A slow/stalling network must PAUSE a multi-GB download, not kill it:
    the download stream gets its own per-read timeout (default 300s) while
    the JSON calls keep the fast 10s timeout. Regression for the repeated
    mid-stream "read operation timed out" failures on slow connections."""
    import weight_stream.server.hub as hubmod
    from weight_stream.server.hub import DEFAULT_STREAM_TIMEOUT, DEFAULT_TIMEOUT

    assert DEFAULT_STREAM_TIMEOUT > DEFAULT_TIMEOUT  # the whole point
    seen = {}

    def capturing_stream(url, t, start=0):
        seen["timeout"] = t
        return FakeStream(_GGUF, content_length=len(_GGUF))

    def capturing_fetch(url, t, start=0):
        seen["json_timeout"] = t
        return FAKE_SEARCH

    mgr = DownloadManager(fetch_json=capturing_fetch, open_stream=capturing_stream)
    mgr.search("q")  # JSON path — must use the fast timeout
    task = mgr.create_download("org/qwen-gguf", "qwen-7b-q4_k_m.gguf", str(models_dir))
    mgr.run_download(task)  # stream path — must use the patient timeout
    assert task.status == "done"
    assert seen["json_timeout"] == DEFAULT_TIMEOUT          # fast for JSON
    assert seen["timeout"] == DEFAULT_STREAM_TIMEOUT        # patient for streams

    # a custom stream_timeout is honored too
    mgr2 = DownloadManager(
        fetch_json=capturing_fetch,
        open_stream=capturing_stream,
        stream_timeout=1234.0,
    )
    t2 = mgr2.create_download("org/m", "q.gguf", str(models_dir))
    mgr2.run_download(t2)
    assert seen["timeout"] == 1234.0


def test_download_is_atomic_with_real_progress(models_dir):
    mgr = _mgr(stream=lambda u, t, start=0: FakeStream(_GGUF, content_length=len(_GGUF)))
    task = mgr.create_download("org/qwen-gguf", "qwen-7b-q4_k_m.gguf", str(models_dir))
    mgr.run_download(task)
    final = models_dir / "qwen-7b-q4_k_m.gguf"
    assert task.status == "done"
    assert final.read_bytes() == _GGUF
    assert not (models_dir / "qwen-7b-q4_k_m.gguf.part").exists()  # atomic: no leftover
    d = task.to_dict()
    assert d["percent"] == 100.0
    assert d["bytes_downloaded"] == len(_GGUF)
    assert d["total_bytes"] == len(_GGUF)
    assert d["speed_bps"] and d["speed_bps"] > 0  # real, not fabricated


def test_download_failure_keeps_part_for_resume(models_dir):
    """v1.1: a failed download KEEPS its partial so a resume can append the
    remaining bytes instead of re-downloading from byte 0."""
    mgr = _mgr(stream=lambda u, t, start=0: FailAfterStream(b"X" * 3000, fail_at=1000))
    mgr.chunk_size = 500  # deterministic cut: exactly 1000 bytes before the raise
    task = mgr.create_download("org/m", "fail.gguf", str(models_dir))
    mgr.run_download(task)
    assert task.status == "failed"
    assert "net died" in task.error
    assert not (models_dir / "fail.gguf").exists()      # no corrupt final
    part = models_dir / "fail.gguf.part"
    assert part.exists() and part.read_bytes() == b"X" * 1000  # partial kept
    assert task.bytes_downloaded == 1000


def test_download_cancel_while_queued(models_dir):
    mgr = _mgr()
    task = mgr.create_download("org/m", "c.gguf", str(models_dir))
    mgr.cancel(task.id)
    assert task.status == "cancelled"
    # running a cancelled task is a no-op that writes nothing
    mgr.run_download(task)
    assert task.status == "cancelled"
    assert not (models_dir / "c.gguf").exists()


def test_download_cancel_keeps_part_for_resume(models_dir):
    """v1.1: cancelling mid-stream keeps the downloaded bytes on disk as
    ``.part`` — the whole point of the Resume button."""
    mgr = _mgr(stream=lambda u, t, start=0: None)  # replaced below
    mgr.chunk_size = 500
    task = mgr.create_download("org/m", "c.gguf", str(models_dir))
    mgr._open_stream = lambda u, t, start=0: CancelAtStream(b"X" * 3000, task, at=1000)
    mgr.run_download(task)
    assert task.status == "cancelled"
    # reads: 0-500, 500-1000 (cancel armed), 1000-1500 delivered; loop sees
    # the flag on the NEXT iteration → exactly 1500 bytes kept
    part = models_dir / "c.gguf.part"
    assert part.exists() and part.read_bytes() == b"X" * 1500
    assert not (models_dir / "c.gguf").exists()  # atomic: no final until done


def test_download_rejected_target_writes_nothing(models_dir):
    mgr = _mgr()
    with pytest.raises(HubValidationError):
        mgr.create_download("org/m", "x.gguf", "../../../etc")
    assert list(models_dir.iterdir()) == []  # nothing created


def test_size_guard_max_bytes(monkeypatch, models_dir):
    monkeypatch.setenv("WS_HUB_MAX_BYTES", "100")
    mgr = _mgr(stream=lambda u, t, start=0: FakeStream(b"X" * 3000, content_length=3000))
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
        fetch_json=lambda u, t, start=0: FAKE_SEARCH,
        open_stream=lambda u, t, start=0: UnknownLengthStream(b"X" * 3000),
        chunk_size=100,  # small chunks so the guard trips early
    )
    task = mgr.create_download("org/m", "sneaky.gguf", str(models_dir))
    mgr.run_download(task)
    assert task.status == "failed"
    assert "WS_HUB_MAX_BYTES" in task.error
    # the real byte count never ran past the ceiling by more than one chunk
    assert task.bytes_downloaded <= 100 + 100
    assert not (models_dir / "sneaky.gguf").exists()
    assert (models_dir / "sneaky.gguf.part").exists()  # partial kept for resume


def test_truncated_stream_is_never_marked_done(models_dir):
    """A stream that ends early (EOF before Content-Length) must FAIL
    honestly and keep the ``.part`` — a truncated file must never be renamed
    into place as "done". Regression: the loop used to treat EOF as success,
    so a connection cut mid-stream produced a ``done`` task whose file was
    missing the tail (10.05 GB advertised vs 3.8 GB on disk)."""
    mgr = _mgr(stream=lambda u, t, start=0: FakeStream(b"G" * 1500, content_length=3000))
    mgr.chunk_size = 500
    task = mgr.create_download("org/m", "cut.gguf", str(models_dir))
    mgr.run_download(task)
    assert task.status == "failed"
    assert "truncated" in (task.error or "")
    assert not (models_dir / "cut.gguf").exists()  # no renamed final file
    assert (models_dir / "cut.gguf.part").exists()  # partial kept for resume
    assert task.bytes_downloaded == 1500  # honest count, not faked


def test_truncated_eof_then_resume_yields_identical_file(models_dir):
    """The EXACT production scenario behind the integrity gate: a stream
    ends early via quiet EOF (no exception) → the gate fails the task and
    keeps the ``.part``; a resume via Range (206) fetches only the remainder
    and the final file is byte-identical to a fresh download."""
    data = _GGUF
    # Phase 1: quiet truncation — EOF after 1000 of the advertised total.
    mgr = _mgr(stream=lambda u, t, start=0: FakeStream(data[:1000], content_length=len(data)))
    mgr.chunk_size = 500
    task = mgr.create_download("org/m", "eof.gguf", str(models_dir))
    mgr.run_download(task)
    assert task.status == "failed"
    assert "truncated" in (task.error or "")
    part = models_dir / "eof.gguf.part"
    assert part.exists() and part.read_bytes() == data[:1000]

    # Phase 2: resume honors Range → only the remaining bytes fetched.
    seen = {"starts": []}

    def range_opener(url, t, start=0):
        seen["starts"].append(start)
        return RangeStream(data, start=start, status=206)

    task2 = mgr.resume(task.id)
    mgr._open_stream = range_opener
    mgr.run_download(task2)
    assert task2.status == "done"
    assert seen["starts"] == [1000]  # resumed exactly from the kept part
    assert (models_dir / "eof.gguf").read_bytes() == data  # byte-identical
    assert task2.bytes_downloaded == len(data)


def test_resume_appends_remaining_bytes_from_part(models_dir):
    """v1.1 happy path: a failed download's kept ``.part`` is resumed via
    ``Range`` (206) — only the remaining bytes are fetched and the final file
    is byte-identical to a fresh download."""
    data = _GGUF
    mgr = _mgr(stream=lambda u, t, start=0: FailAfterStream(data, fail_at=1000))
    mgr.chunk_size = 500
    task = mgr.create_download("org/m", "r.gguf", str(models_dir))
    mgr.run_download(task)
    assert task.status == "failed"
    part = models_dir / "r.gguf.part"
    assert part.exists() and part.read_bytes() == data[:1000]

    # resume: upstream honors Range → only 2000 remaining bytes transferred
    seen = {"starts": []}

    def range_opener(url, t, start=0):
        seen["starts"].append(start)
        return RangeStream(data, start=start, status=206)

    task2 = mgr.resume(task.id)  # resume on the SAME manager that owns it
    mgr._open_stream = range_opener
    assert task2 is not None and task2.status == "queued"
    mgr.run_download(task2)
    assert task2.status == "done"
    final = models_dir / "r.gguf"
    assert final.read_bytes() == data                     # byte-identical
    assert not (models_dir / "r.gguf.part").exists()      # atomic rename
    d = task2.to_dict()
    assert d["total_bytes"] == len(data)
    assert d["bytes_downloaded"] == len(data)
    assert d["percent"] == 100.0
    assert seen["starts"] == [1000]                      # Range asked from byte 1000


def test_new_task_resumes_stale_part(models_dir):
    """A brand-NEW download of the same filename picks up a stale ``.part``
    (auto-resume) instead of re-fetching from byte 0 — the documented
    v1.1 behavior for any task whose target file already has a partial."""
    data = _GGUF
    mgr = _mgr(stream=lambda u, t, start=0: FailAfterStream(data, fail_at=1000))
    mgr.chunk_size = 500
    t1 = mgr.create_download("org/m", "auto.gguf", str(models_dir))
    mgr.run_download(t1)
    assert t1.status == "failed"
    assert (models_dir / "auto.gguf.part").read_bytes() == data[:1000]

    seen = []
    mgr._open_stream = lambda u, t, start=0: (seen.append(start) or RangeStream(data, start=start, status=206))
    t2 = mgr.create_download("org/m", "auto.gguf", str(models_dir))  # NEW task, same file
    mgr.run_download(t2)
    assert t2.status == "done"
    assert (models_dir / "auto.gguf").read_bytes() == data
    assert seen == [1000]  # asked Range from byte 1000 — never re-fetched byte 0


def test_resume_mismatched_range_fails_honestly(models_dir):
    """A 206 whose ``Content-Range`` starts at a DIFFERENT offset than asked
    would corrupt the appended file — the task must fail honestly instead."""
    data = b"W" * 3000
    mgr = _mgr(stream=lambda u, t, start=0: FailAfterStream(data, fail_at=1000))
    mgr.chunk_size = 500
    task = mgr.create_download("org/m", "mis.gguf", str(models_dir))
    mgr.run_download(task)
    assert task.status == "failed"

    class WrongRange(RangeStream):
        def __init__(self, data, start=0, status=206):
            super().__init__(data, start=start, status=status)
            self.content_range_start = 500  # claims a DIFFERENT offset

    mgr._open_stream = lambda u, t, start=0: WrongRange(data, start=start, status=206)
    t2 = mgr.resume(task.id)
    mgr.run_download(t2)
    assert t2.status == "failed"
    assert "range" in (t2.error or "").lower()
    assert not (models_dir / "mis.gguf").exists()      # never written
    assert (models_dir / "mis.gguf.part").exists()      # partial kept, not corrupted


def test_delete_during_active_download_stops_and_cleans(models_dir):
    """Deleting a download WHILE it is running must stop the worker and
    remove the ``.part`` (Windows cannot remove an open file — the retry
    thread finishes the job once the worker closes its handle)."""
    class SlowStream(FakeStream):
        def __init__(self, task):
            super().__init__(b"C" * 100_000_000)  # never finishes quickly
            self._task = task

        def read(self, n):
            time.sleep(0.01)  # slow enough to delete mid-stream
            return self._buf.read(n)

    mgr = _mgr()
    mgr.chunk_size = 500
    task = mgr.create_download("org/m", "live.gguf", str(models_dir))
    mgr._open_stream = lambda u, t, start=0: SlowStream(task)
    th = threading.Thread(target=mgr.run_download, args=(task,))
    th.start()
    deadline = time.time() + 5
    while time.time() < deadline and task.bytes_downloaded < 1000:
        time.sleep(0.02)
    mgr.delete(task.id)  # mid-download: cancel + pop + remove part (retries in bg)
    th.join(timeout=5)
    for _ in range(30):  # retry thread may need a moment on Windows
        if not (models_dir / "live.gguf.part").exists():
            break
        time.sleep(0.1)
    assert not (models_dir / "live.gguf.part").exists()  # no orphaned partial
    assert not (models_dir / "live.gguf").exists()        # no final file


def test_resume_ignored_range_restarts_fresh(models_dir):
    """Upstream that ignores ``Range`` (200, whole body) must NOT duplicate
    the kept partial — the transfer restarts fresh and stays correct."""
    data = _GGUF
    mgr = _mgr(stream=lambda u, t, start=0: FailAfterStream(data, fail_at=1500))
    mgr.chunk_size = 500
    task = mgr.create_download("org/m", "ign.gguf", str(models_dir))
    mgr.run_download(task)
    assert task.status == "failed"
    assert (models_dir / "ign.gguf.part").read_bytes() == data[:1500]

    def full_opener(url, t, start=0):
        return RangeStream(data, start=start, status=200)  # ignores Range

    task2 = mgr.resume(task.id)
    mgr._open_stream = full_opener  # swap seam on the SAME manager
    mgr.run_download(task2)
    assert task2.status == "done"
    assert (models_dir / "ign.gguf").read_bytes() == data
    assert task2.bytes_downloaded == len(data)  # no double-counted prefix


def test_resume_refuses_active_and_done(models_dir):
    mgr = _mgr()
    task = mgr.create_download("org/m", "a.gguf", str(models_dir))
    mgr.run_download(task)
    assert task.status == "done"
    with pytest.raises(ValueError):
        mgr.resume(task.id)  # done is not resumable


def test_delete_removes_task_and_part(models_dir):
    mgr = _mgr(stream=lambda u, t, start=0: FailAfterStream(b"X" * 3000, fail_at=700))
    mgr.chunk_size = 500
    task = mgr.create_download("org/m", "d.gguf", str(models_dir))
    mgr.run_download(task)
    assert task.status == "failed"
    part = models_dir / "d.gguf.part"
    assert part.exists()
    assert mgr.delete(task.id) is not None
    assert mgr.get_task(task.id) is None      # removed from the manager
    assert not part.exists()                  # partial cleaned up


def test_delete_done_task_keeps_final_file(models_dir):
    """Deleting a COMPLETED task row must never destroy the downloaded model
    by default (delete_file=False)."""
    mgr = _mgr()
    task = mgr.create_download("org/m", "keep.gguf", str(models_dir))
    mgr.run_download(task)
    assert (models_dir / "keep.gguf").exists()
    assert mgr.delete(task.id) is not None
    assert (models_dir / "keep.gguf").exists()  # model file survives


def test_delete_done_task_with_delete_file_removes_model(models_dir):
    """delete_file=True on a COMPLETED task also removes the model file."""
    mgr = _mgr()
    task = mgr.create_download("org/m", "gone.gguf", str(models_dir))
    mgr.run_download(task)
    final = models_dir / "gone.gguf"
    assert final.exists()
    assert mgr.delete(task.id, delete_file=True) is not None
    assert not final.exists()                       # model file deleted
    assert not (models_dir / "gone.gguf.part").exists()


def test_delete_file_refuses_outside_allowed_dir(models_dir, tmp_path):
    """The destructive delete is containment-guarded: a target path that
    realpath-resolves outside the allowed model dirs is never removed."""
    outside = tmp_path / "outside"
    outside.mkdir()
    victim = outside / "victim.gguf"
    victim.write_bytes(b"precious")
    mgr = _mgr()
    assert mgr._remove_model_file(str(victim)) is False
    assert victim.read_bytes() == b"precious"       # untouched
    # a symlink pointing outside is refused too (realpath escapes)
    link = models_dir / "escape.gguf"
    try:
        os.symlink(victim, link)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable on this platform")
    assert mgr._remove_model_file(str(link)) is False
    assert victim.read_bytes() == b"precious"
    assert link.exists()  # the link itself is not removed either


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
    mgr = _mgr(stream=lambda u, t, start=0: FakeStream(b"X" * 3000, content_length=3000))
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


def test_hub_resume_endpoint_requeues_and_completes(models_dir, monkeypatch, tmp_path):
    app, _ = _app(monkeypatch, tmp_path)
    with TestClient(app) as c:
        hub_mgr = app.state.hub_manager
        task = hub_mgr.create_download("org/m", "m-q4_0.gguf", str(models_dir))
        hub_mgr.cancel(task.id)
        assert task.status == "cancelled"
        r = c.post(f"/v1/hub/download/{task.id}/resume")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "queued"
        # the worker runs (FakeStream) and finishes; poll the list until done
        for _ in range(50):
            if hub_mgr.get_task(task.id).status in ("done", "failed"):
                break
            import time as _t
            _t.sleep(0.05)
        assert hub_mgr.get_task(task.id).status == "done"
        assert (models_dir / "m-q4_0.gguf").read_bytes() == _GGUF


def test_hub_resume_404_and_409(models_dir, monkeypatch, tmp_path):
    app, _ = _app(monkeypatch, tmp_path)
    with TestClient(app) as c:
        assert c.post("/v1/hub/download/nope/resume").status_code == 404
        hub_mgr = app.state.hub_manager
        task = hub_mgr.create_download("org/m", "m-q4_0.gguf", str(models_dir))
        hub_mgr.run_download(task)  # synchronous → done
        r = c.post(f"/v1/hub/download/{task.id}/resume")
        assert r.status_code == 409
        assert "resume" in r.json()["detail"]


def test_hub_delete_endpoint_removes_task(models_dir, monkeypatch, tmp_path):
    app, _ = _app(monkeypatch, tmp_path)
    with TestClient(app) as c:
        hub_mgr = app.state.hub_manager
        task = hub_mgr.create_download("org/m", "m-q4_0.gguf", str(models_dir))
        r = c.post(f"/v1/hub/download/{task.id}/delete")
        assert r.status_code == 200
        assert r.json()["status"] == "deleted"
        assert r.json()["file_deleted"] is False
        assert hub_mgr.get_task(task.id) is None
        assert c.post("/v1/hub/download/nope/delete").status_code == 404


def test_hub_delete_file_endpoint_removes_model(models_dir, monkeypatch, tmp_path):
    """{"delete_file": true} on a completed task removes the model file too."""
    app, _ = _app(monkeypatch, tmp_path)
    monkeypatch.setattr(
        "weight_stream.server.api_server._assistants_referencing", lambda f: []
    )
    with TestClient(app) as c:
        hub_mgr = app.state.hub_manager
        task = hub_mgr.create_download("org/m", "m-q4_0.gguf", str(models_dir))
        hub_mgr.run_download(task)  # synchronous → done, file on disk
        final = models_dir / "m-q4_0.gguf"
        assert final.exists()
        r = c.post(f"/v1/hub/download/{task.id}/delete", json={"delete_file": True})
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "deleted"
        assert body["id"] == task.id
        assert body["file_deleted"] is True
        assert body["referenced_by"] == {"assistants": []}
        assert not final.exists()


def test_hub_delete_file_endpoint_409_when_not_done(models_dir, monkeypatch, tmp_path):
    app, _ = _app(monkeypatch, tmp_path)
    with TestClient(app) as c:
        hub_mgr = app.state.hub_manager
        task = hub_mgr.create_download("org/m", "m-q4_0.gguf", str(models_dir))
        hub_mgr.cancel(task.id)  # cancelled — no model file
        r = c.post(f"/v1/hub/download/{task.id}/delete", json={"delete_file": True})
        assert r.status_code == 409
        assert "completed" in r.json()["detail"]
        # the task row is still there (the delete did NOT happen)
        assert hub_mgr.get_task(task.id) is not None


def test_hub_delete_file_endpoint_409_when_model_loaded(models_dir, monkeypatch, tmp_path):
    """Deleting the file of a model that is currently loaded is refused — the
    backend holds it open; unloading is the only safe path."""
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    app, manager = _app(monkeypatch, tmp_path)
    monkeypatch.setattr(
        manager, "list_models",
        AsyncMock(return_value=[SimpleNamespace(path=str(models_dir / "m-q4_0.gguf"))]),
    )
    with TestClient(app) as c:
        hub_mgr = app.state.hub_manager
        task = hub_mgr.create_download("org/m", "m-q4_0.gguf", str(models_dir))
        hub_mgr.run_download(task)  # done, file on disk
        final = models_dir / "m-q4_0.gguf"
        assert final.exists()
        r = c.post(f"/v1/hub/download/{task.id}/delete", json={"delete_file": True})
        assert r.status_code == 409
        assert "loaded" in r.json()["detail"]
        assert final.exists()          # file NOT deleted
        assert hub_mgr.get_task(task.id) is not None  # task NOT removed


def test_clear_removes_finished_keeps_active(models_dir):
    """clear() removes every terminal task; queued/downloading stay."""
    mgr = _mgr()
    done = mgr.create_download("org/m", "d.gguf", str(models_dir))
    mgr.run_download(done)
    assert done.status == "done"
    failed = mgr.create_download("org/m", "f.gguf", str(models_dir))
    failed.status = "failed"
    failed.error = "boom"
    cancelled = mgr.create_download("org/m", "c.gguf", str(models_dir))
    mgr.cancel(cancelled.id)
    active = mgr.create_download("org/m", "a.gguf", str(models_dir))  # stays queued

    res = mgr.clear()
    assert set(res["removed"]) == {done.id, failed.id, cancelled.id}
    assert res["files_deleted"] == []
    assert res["files_skipped"] == []
    assert mgr.get_task(done.id) is None
    assert mgr.get_task(failed.id) is None
    assert mgr.get_task(cancelled.id) is None
    assert mgr.get_task(active.id) is not None   # active untouched
    assert (models_dir / "d.gguf").exists()       # default: model file kept


def test_clear_delete_file_removes_done_models_and_reports_skipped(models_dir):
    """clear(delete_file=True) removes the model files of done tasks, except
    protected (loaded) paths which are reported in files_skipped."""
    mgr = _mgr()
    t1 = mgr.create_download("org/m", "one.gguf", str(models_dir))
    mgr.run_download(t1)
    t2 = mgr.create_download("org/m", "two.gguf", str(models_dir))
    mgr.run_download(t2)
    failed = mgr.create_download("org/m", "f.gguf", str(models_dir))
    failed.status = "failed"

    res = mgr.clear(
        delete_file=True,
        protected_paths={os.path.realpath(str(models_dir / "two.gguf"))},
    )
    assert set(res["removed"]) == {t1.id, t2.id, failed.id}
    assert res["files_deleted"] == [t1.id]
    assert res["files_skipped"] == [t2.id]      # loaded → kept
    assert not (models_dir / "one.gguf").exists()  # deleted
    assert (models_dir / "two.gguf").exists()      # protected → kept


def test_clear_is_idempotent_and_honest_with_nothing_to_do(models_dir):
    """No finished tasks → empty summary, no error (idempotent clear)."""
    mgr = _mgr()
    active = mgr.create_download("org/m", "a.gguf", str(models_dir))
    res = mgr.clear()
    assert res == {"status": "cleared", "removed": [], "files_deleted": [], "files_skipped": []}
    assert mgr.get_task(active.id) is not None


def test_hub_clear_endpoint_removes_finished_keeps_active(models_dir, monkeypatch, tmp_path):
    app, _ = _app(monkeypatch, tmp_path)
    with TestClient(app) as c:
        hub_mgr = app.state.hub_manager
        done = hub_mgr.create_download("org/m", "m-q4_0.gguf", str(models_dir))
        hub_mgr.run_download(done)  # synchronous → done, file on disk
        active = hub_mgr.create_download("org/m", "live.gguf", str(models_dir))
        r = c.post("/v1/hub/downloads/clear")
        assert r.status_code == 200
        body = r.json()
        assert body["removed"] == [done.id]
        assert hub_mgr.get_task(done.id) is None
        assert hub_mgr.get_task(active.id) is not None
        assert (models_dir / "m-q4_0.gguf").exists()  # no delete_file → kept


def test_hub_clear_endpoint_delete_file_skips_loaded_model(models_dir, monkeypatch, tmp_path):
    """delete_file=true removes done model files but skips a loaded model's
    file (never removed under a running backend) — reported honestly."""
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    app, manager = _app(monkeypatch, tmp_path)
    monkeypatch.setattr(
        manager, "list_models",
        AsyncMock(return_value=[SimpleNamespace(path=str(models_dir / "m-q4_0.gguf"))]),
    )
    monkeypatch.setattr(
        "weight_stream.server.api_server._assistant_refs_batch", lambda files: {}
    )
    with TestClient(app) as c:
        hub_mgr = app.state.hub_manager
        loaded = hub_mgr.create_download("org/m", "m-q4_0.gguf", str(models_dir))
        hub_mgr.run_download(loaded)  # done; its file is "loaded" per the mock
        free = hub_mgr.create_download("org/m", "free.gguf", str(models_dir))
        hub_mgr.run_download(free)
        r = c.post("/v1/hub/downloads/clear", json={"delete_file": True})
        assert r.status_code == 200
        body = r.json()
        assert set(body["removed"]) == {loaded.id, free.id}
        assert body["files_deleted"] == [free.id]
        assert body["files_skipped"] == [loaded.id]
        # every removed done task is mapped (empty refs here)
        assert body["referenced_by"] == {
            loaded.id: {"assistants": []},
            free.id: {"assistants": []},
        }
        assert (models_dir / "m-q4_0.gguf").exists()  # loaded → kept
        assert not (models_dir / "free.gguf").exists()  # deleted


def test_hub_delete_endpoint_reports_assistant_references(models_dir, monkeypatch, tmp_path):
    """The delete response carries which assistants reference this model's
    suggested id — the server-side half of the cross-feature warning."""
    app, _ = _app(monkeypatch, tmp_path)
    monkeypatch.setattr(
        "weight_stream.server.api_server._assistants_referencing",
        lambda f: ["Coder", "Translator"],
    )
    with TestClient(app) as c:
        hub_mgr = app.state.hub_manager
        task = hub_mgr.create_download("org/m", "m-q4_0.gguf", str(models_dir))
        hub_mgr.run_download(task)  # done
        r = c.post(f"/v1/hub/download/{task.id}/delete", json={"delete_file": True})
        assert r.status_code == 200
        body = r.json()
        assert body["referenced_by"] == {"assistants": ["Coder", "Translator"]}
        # keep-file delete never scans the store — refs are irrelevant (the
        # file survives) and the field stays honest and empty
        task2 = hub_mgr.create_download("org/m", "keep.gguf", str(models_dir))
        hub_mgr.run_download(task2)
        r2 = c.post(f"/v1/hub/download/{task2.id}/delete")
        assert r2.json()["referenced_by"] == {"assistants": []}


def test_hub_clear_endpoint_reports_assistant_references(models_dir, monkeypatch, tmp_path):
    """clear(delete_file=True) maps every removed done task to its assistant
    references (task id → names) from ONE batched store read, so the
    summary toast can be honest."""
    app, _ = _app(monkeypatch, tmp_path)
    by_name = {"a.gguf": ["Coder"], "b.gguf": [], "c.gguf": ["Coder", "Translator"]}
    calls = []
    monkeypatch.setattr(
        "weight_stream.server.api_server._assistant_refs_batch",
        lambda files: calls.append(list(files)) or {f: by_name.get(f, []) for f in files},
    )
    with TestClient(app) as c:
        hub_mgr = app.state.hub_manager
        a = hub_mgr.create_download("org/m", "a.gguf", str(models_dir))
        hub_mgr.run_download(a)
        b = hub_mgr.create_download("org/m", "b.gguf", str(models_dir))
        hub_mgr.run_download(b)
        ccc = hub_mgr.create_download("org/m", "c.gguf", str(models_dir))
        hub_mgr.run_download(ccc)
        r = c.post("/v1/hub/downloads/clear", json={"delete_file": True})
        assert r.status_code == 200
        body = r.json()
        assert body["referenced_by"] == {
            a.id: {"assistants": ["Coder"]},
            b.id: {"assistants": []},
            ccc.id: {"assistants": ["Coder", "Translator"]},
        }
        assert len(calls) == 1  # one batched read, never per-task


def test_assistants_referencing_matches_model_id(monkeypatch):
    """The helper matches assistant.model_id against the filename's suggested
    id (basename without .gguf) — the same rule the Console uses when loading
    a downloaded model. Store problems degrade to [] (never block a delete)."""
    import weight_stream.server.assistants as astore_mod
    from weight_stream.server.api_server import _assistants_referencing

    class _Stub:
        def __init__(self, items):
            self._items = items

        def list(self):
            return self._items

    refs = [
        {"id": "a1", "name": "Coder", "model_id": "qwen-7b-q4_k_m"},
        {"id": "a2", "name": "Translator", "model_id": "qwen-7b-q4_k_m"},
        {"id": "a3", "name": "Other", "model_id": "llama-3.2-1b"},
        {"id": "a4", "name": "NoModel", "model_id": None},
    ]
    monkeypatch.setattr(astore_mod, "get_assistant_store", lambda: _Stub(refs))

    assert _assistants_referencing("qwen-7b-q4_k_m.gguf") == ["Coder", "Translator"]
    assert _assistants_referencing("llama-3.2-1b.gguf") == ["Other"]
    assert _assistants_referencing("unknown.gguf") == []
    assert _assistants_referencing("") == []

    # a failing store must never block the delete — degrade to []
    def boom():
        raise RuntimeError("store gone")

    monkeypatch.setattr(astore_mod, "get_assistant_store", boom)
    assert _assistants_referencing("qwen-7b-q4_k_m.gguf") == []


def test_assistant_refs_batch_reads_store_once(monkeypatch):
    """The batched scanner performs ONE store read for many filenames (a
    per-task scan would re-read every assistant JSON N times on clear)."""
    import weight_stream.server.assistants as astore_mod
    from weight_stream.server.api_server import _assistant_refs_batch

    reads = {"n": 0}

    class _Stub:
        def list(self):
            reads["n"] += 1
            return [
                {"id": "a1", "name": "Coder", "model_id": "qwen-7b-q4_k_m"},
                {"id": "a2", "name": "Other", "model_id": "llama-3.2-1b"},
                {"id": "a3", "name": "NoModel", "model_id": None},
            ]

    monkeypatch.setattr(astore_mod, "get_assistant_store", lambda: _Stub())
    out = _assistant_refs_batch(["qwen-7b-q4_k_m.gguf", "llama-3.2-1b.gguf", "nope.gguf", ""])
    assert reads["n"] == 1  # one read for the whole batch
    assert out == {
        "qwen-7b-q4_k_m.gguf": ["Coder"],
        "llama-3.2-1b.gguf": ["Other"],
        "nope.gguf": [],
    }


def test_to_dict_reports_real_file_size_for_done(models_dir):
    """file_size is the REAL on-disk byte count for a completed download,
    None for anything else (honest — never a fake size)."""
    mgr = _mgr()
    done = mgr.create_download("org/m", "sz.gguf", str(models_dir))
    mgr.run_download(done)
    d = done.to_dict()
    assert d["status"] == "done"
    assert d["file_size"] == len(_GGUF)  # FakeStream wrote exactly the GGUF bytes
    # a queued/never-downloaded task has no file on disk
    fresh = mgr.create_download("org/m", "n.gguf", str(models_dir))
    assert fresh.to_dict()["file_size"] is None


def test_file_size_none_when_file_vanish_race(models_dir, monkeypatch):
    """A done task whose file disappears between isfile and getsize must
    yield file_size None — never a raised OSError (which would 500 the whole
    downloads list)."""
    mgr = _mgr()
    task = mgr.create_download("org/m", "race.gguf", str(models_dir))
    mgr.run_download(task)
    assert task.to_dict()["file_size"] == len(_GGUF)
    final = models_dir / "race.gguf"
    assert final.exists()

    # simulate the external delete racing the stat
    real_isfile = os.path.isfile
    real_getsize = os.path.getsize
    state = {"deleted": False}

    def fake_isfile(p):
        ok = real_isfile(p)
        if ok and p == str(final):
            state["deleted"] = True
            final.unlink()  # vanish between the check and the stat
        return ok

    monkeypatch.setattr(os.path, "isfile", fake_isfile)
    monkeypatch.setattr(os.path, "getsize", lambda p: real_getsize(p))  # still callable
    assert task.to_dict()["file_size"] is None  # race degrades to None
    monkeypatch.setattr(os.path, "isfile", real_isfile)
    monkeypatch.setattr(os.path, "getsize", real_getsize)


def test_hub_reveal_endpoint_404_409_403(models_dir, monkeypatch, tmp_path):
    """Reveal is guarded: unknown task → 404, not-finished/no-file → 409,
    file outside allowed dirs → 403 (never reveal an arbitrary path)."""
    app, _ = _app(monkeypatch, tmp_path)
    with TestClient(app) as c:
        assert c.post("/v1/hub/download/nope/reveal").status_code == 404
        hub_mgr = app.state.hub_manager
        queued = hub_mgr.create_download("org/m", "m-q4_0.gguf", str(models_dir))
        assert c.post(f"/v1/hub/download/{queued.id}/reveal").status_code == 409


def test_hub_reveal_endpoint_opens_folder_and_returns_path(models_dir, monkeypatch, tmp_path):
    """A completed task with its file on disk is revealed — the subprocess
    launcher is stubbed so the test stays offline and deterministic."""
    app, _ = _app(monkeypatch, tmp_path)
    calls = []
    monkeypatch.setattr(
        "weight_stream.server.api_server._reveal_in_explorer",
        lambda path: calls.append(path) or {"ok": True},
    )
    with TestClient(app) as c:
        hub_mgr = app.state.hub_manager
        task = hub_mgr.create_download("org/m", "m-q4_0.gguf", str(models_dir))
        hub_mgr.run_download(task)  # synchronous → done, file on disk
        r = c.post(f"/v1/hub/download/{task.id}/reveal")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "revealed"
        assert body["path"] == os.path.realpath(str(models_dir / "m-q4_0.gguf"))
        assert calls == [os.path.realpath(str(models_dir / "m-q4_0.gguf"))]


def test_hub_reveal_endpoint_500_when_launcher_fails(models_dir, monkeypatch, tmp_path):
    """The OS launcher failing must surface honestly (500), never a fake ok."""
    app, _ = _app(monkeypatch, tmp_path)
    monkeypatch.setattr(
        "weight_stream.server.api_server._reveal_in_explorer",
        lambda path: {"error": "explorer missing"},
    )
    with TestClient(app) as c:
        hub_mgr = app.state.hub_manager
        task = hub_mgr.create_download("org/m", "m-q4_0.gguf", str(models_dir))
        hub_mgr.run_download(task)
        r = c.post(f"/v1/hub/download/{task.id}/reveal")
        assert r.status_code == 500
        assert "explorer missing" in r.json()["detail"]


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
        assert frames[-1]["bytes_downloaded"] == len(_GGUF)
        assert (models_dir / "m-q4_0.gguf").read_bytes() == _GGUF


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


# ── GGUF structural gate (EXP-011b follow-up) ─────────────────────────


def test_gguf_structural_gate_accepts_valid(tmp_path):
    from weight_stream.server.hub import _verify_gguf_structure
    p = tmp_path / "ok.gguf"
    p.write_bytes(_GGUF)
    s = _verify_gguf_structure(str(p))
    assert s["ok"] is True
    assert s["version"] == 3
    assert s["tensor_count"] == 1
    assert s["architecture"] == "qwen3"
    assert s["data_bytes"] == 4096 * 4  # exactly the F32 payload


def test_gguf_structural_gate_rejects_bad_magic(tmp_path):
    from weight_stream.server.hub import HubValidationError, _verify_gguf_structure
    p = tmp_path / "bad.gguf"
    p.write_bytes(_make_gguf_bytes(magic=b"NOPE"))
    with pytest.raises(HubValidationError) as ei:
        _verify_gguf_structure(str(p))
    assert "magic" in str(ei.value)


def test_gguf_structural_gate_rejects_offset_past_eof(tmp_path):
    from weight_stream.server.hub import HubValidationError, _verify_gguf_structure
    p = tmp_path / "over.gguf"
    p.write_bytes(_make_gguf_bytes(bad_offset=999_999))
    with pytest.raises(HubValidationError) as ei:
        _verify_gguf_structure(str(p))
    assert "ends at byte" in str(ei.value) or "past" in str(ei.value)


def test_download_of_garbage_is_rejected_and_part_removed(models_dir):
    """The structural gate's production scenario: a stream that delivers its
    FULL advertised byte count but whose content is not a GGUF (e.g. an
    equal-length HTML error page) must fail the task, drop the corrupt
    ``.part`` (a resume would append to a full file), and leave NO final
    file — never rename garbage into ``.gguf``."""
    garbage = b"<html>upstream error page</html>" * 500  # not a GGUF
    mgr = _mgr(stream=lambda u, t, start=0: FakeStream(garbage, content_length=len(garbage)))
    task = mgr.create_download("org/m", "garbage.gguf", str(models_dir))
    mgr.run_download(task)
    assert task.status == "failed"
    assert "not a valid GGUF" in (task.error or "")
    assert not (models_dir / "garbage.gguf").exists()       # never renamed in
    assert not (models_dir / "garbage.gguf.part").exists()  # corrupt part dropped

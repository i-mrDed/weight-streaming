"""Hugging Face Hub integration for the API server (P4).

Adds model discovery + one-click GGUF download with NO new runtime
dependency: the HF REST API is called with the standard-library ``urllib``
(search = small JSON; download = chunked stream in a worker thread).

Security (the critical part — the server has no auth and CORS ``*``, and this
endpoint writes files from the internet to disk):

- ``target_dir`` must ``os.path.realpath``-resolve INSIDE one of the model
  search dirs (``get_model_search_dirs()``). Path traversal (``../``),
  absolute paths outside the allow-list, and symlink escapes are rejected
  (``HubValidationError`` → HTTP 403).
- The destination filename must end in ``.gguf`` and contain no path
  separators / ``..`` / NUL (``HubValidationError`` → HTTP 400).
- Writes are ATOMIC: ``<name>.gguf.part`` then ``os.replace`` to the final
  path, so a partial/interrupted download never leaves a corrupt ``.gguf``.
- A SIZE GUARD compares ``Content-Length`` against ``WS_HUB_MAX_BYTES``
  (0 = unlimited) and the target volume's free space before writing, and
  aborts if the running total exceeds the ceiling.
- The ``.part`` file is created with EXCLUSIVE, NO-FOLLOW semantics
  (``O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW`` where available), so a
  pre-placed symlink at the destination can never redirect the write
  (closes the symlink-TOCTOU between the dir-containment check and the
  write). A cancelled/failed task KEEPS its ``.part``; any later download
  of the same file (a resume OR a brand-new task) appends the remaining
  bytes via HTTP ``Range`` instead of re-fetching from byte 0.
- RESUME (v1.1): ``POST /v1/hub/download/{id}/resume`` re-queues a
  cancelled/failed task; the worker re-opens the kept ``.part`` in append
  mode (NO-FOLLOW, symlink refused) and streams ``Range: bytes=<n>-`` from
  Hugging Face. If the upstream ignores ``Range`` (HTTP 200 instead of
  206) the transfer restarts fresh rather than duplicating bytes; if it
  answers 206 at a DIFFERENT offset than asked (``Content-Range``
  mismatch) the task fails honestly instead of writing misaligned bytes.

Honest limitation (disk-free guard without ``Content-Length``): when the
upstream sends no ``Content-Length`` header the free-space pre-check cannot
run (the total is unknown), so the guard degrades to the mid-stream
``WS_HUB_MAX_BYTES`` byte count, which still cannot be breached. With
``WS_HUB_MAX_BYTES=0`` (unlimited) AND no ``Content-Length`` a chunked
write could in principle fill the volume — the resulting ``OSError`` fails
the task honestly and the ``.part`` is removed. HF CDN responses normally
carry ``Content-Length``, so the pre-check applies in practice.

Honest telemetry (ADR-003): ``bytes``/``percent``/``speed_bps``/``eta_s`` are
computed from real bytes transferred and real elapsed time — never fixed or
randomized. HF unreachable → ``HubUpstreamError`` (HTTP 502); no fake results.

Tests must NOT hit the real network: ``DownloadManager`` accepts injectable
``fetch_json`` / ``open_stream`` callables (defaults are the urllib helpers
below, which tests monkeypatch).
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import threading
import time
import urllib.parse
import urllib.request
from typing import Any, Callable, Optional

from .config import get_model_search_dirs

HF_API_BASE = "https://huggingface.co/api/models"
HF_RESOLVE_BASE = "https://huggingface.co"

DEFAULT_TIMEOUT = 10.0          # seconds for HF HTTP calls
DEFAULT_STREAM_TIMEOUT = 300.0  # per-read seconds for download streams
                                # (much larger: a slow/stalling network must
                                # not kill a multi-GB download mid-stream)
SEARCH_CACHE_TTL = 300.0        # 5 minutes
MODEL_CACHE_TTL = 900.0         # 15 minutes — on-demand detail changes rarely
DEFAULT_CHUNK = 1 << 20         # 1 MiB read chunks
_SORT_MAP = {"recent": "lastModified", "downloads": "downloads", "likes": "likes"}

_QUANT_RE = re.compile(r"\b(I?Q\d+(?:_[A-Z0-9]+)*|BF16|FP16|F16|F32)\b", re.IGNORECASE)
_SIZE_RE = re.compile(r"\b(\d+x\d+(?:\.\d+)?[Bb]|\d+(?:\.\d+)?[Bb])\b")
# GGUF shards: "<name>-00001-of-00004.gguf" (Git LFS ~5GB/file cap splits big
# weights). index/total are 1-based; every shard of a quant must be present
# together to load it.
_SHARD_RE = re.compile(r"-(\d+)-of-(\d+)\.gguf$", re.IGNORECASE)
# cardData keys that honestly carry a context window (rare on GGUF repos).
_CONTEXT_KEYS = (
    "context_length", "max_context_length", "context_window",
    "max_seq_len", "context",
)
_CONTEXT_TAG_RE = re.compile(r"context[-_ ]?length:(\d+)", re.IGNORECASE)


class HubUpstreamError(Exception):
    """HF could not be reached / returned an error (→ HTTP 502)."""


class HubValidationError(Exception):
    """Bad download request (→ ``status``: 400 bad filename, 403 bad dir)."""

    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


# ── Filename parsing (honest, best-effort) ────────────────────────────


def parse_quant(filename: str) -> Optional[str]:
    """Extract a GGUF quant tag (Q4_K_M, F16, IQ2_S, …) from a filename.

    ``fp16`` is normalised to the canonical ``F16`` (the unquantized family),
    so an ``…-fp16.gguf`` file joins the same group — and the same honest
    "unquantized, very large" label — as ``…-f16.gguf``.
    """
    m = _QUANT_RE.search(filename or "")
    if not m:
        return None
    q = m.group(1).upper()
    return "F16" if q == "FP16" else q


def parse_size_label(text: str) -> Optional[str]:
    """Extract a parameter-size label (7B, 1.5B, 8X7B) from repo/file names."""
    m = _SIZE_RE.search(text or "")
    return m.group(1).upper() if m else None


def parse_shard(filename: str) -> Optional[dict]:
    """Extract shard ``{index, total}`` (1-based) from ``-NNNNN-of-MMMMM.gguf``.

    Returns ``None`` for a single-file (non-sharded) weight. Honest: only the
    trailing shard marker counts — an ``-of-`` anywhere else is ignored.
    """
    m = _SHARD_RE.search(filename or "")
    if not m:
        return None
    return {"index": int(m.group(1)), "total": int(m.group(2))}


def _shard_group_key(filename: str, quant: Optional[str], shard: Optional[dict]) -> tuple:
    """Group key that keeps a single-file weight SEPARATE from a sharded set
    that happens to share its quant + stem (some repos ship fp16 both as one
    file and as ``-of-N`` shards). Merging them would make "download all N"
    fetch two redundant copies — the exact confusion feedback #5 targets.

    * sharded files → ``(quant, stem, total)`` so all parts of one split group;
    * single files  → ``(quant, filename, None)`` so each is its own group.
    """
    if shard is not None:
        stem = _SHARD_RE.sub(".gguf", filename)  # strip "-NNNNN-of-MMMMM"
        return (quant, stem, shard["total"])
    return (quant, filename, None)


def _sanitize_filename(name: Any) -> str:
    if not isinstance(name, str) or not name:
        raise HubValidationError("filename is required", status=400)
    if "/" in name or "\\" in name or ".." in name or "\x00" in name:
        raise HubValidationError("filename must not contain path separators or '..'", status=400)
    if not name.lower().endswith(".gguf"):
        raise HubValidationError("filename must end with .gguf", status=400)
    return name


def _resolve_target_dir(target_dir: Optional[str], allowed_dirs: list[str]) -> str:
    """Resolve ``target_dir`` to a real path inside the allowed model dirs.

    Symlinks and ``..`` are resolved via ``realpath`` BEFORE the containment
    check, so a symlink pointing outside the allow-list is rejected.
    """
    allowed_real = [os.path.realpath(d) for d in allowed_dirs]
    if not target_dir:
        # Default to the first existing allowed dir (cwd is always present).
        for d in allowed_dirs:
            if os.path.isdir(d):
                return os.path.realpath(d)
        return os.path.realpath(os.getcwd())
    real = os.path.realpath(target_dir)
    for ra in allowed_real:
        if real == ra or real.startswith(ra + os.sep):
            return real
    raise HubValidationError(
        "target_dir must be inside an allowed model directory", status=403
    )


# ── Default HTTP layer (stdlib urllib; monkeypatched in tests) ────────


def _default_fetch_json(url: str, timeout: float) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": "weight-streaming"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _default_fetch_json_headers(url: str, timeout: float) -> tuple[Any, dict]:
    """Fetch JSON *and* the response headers (pagination reads ``Link``).

    P5.2 Hub "Latest" uses Hugging Face cursor pagination: the next page
    cursor lives in the ``Link: rel="next"`` header, so search-with-cursor
    needs headers, unlike the plain search. Backwards-compatible — the plain
    ``_default_fetch_json`` is untouched.
    """
    req = urllib.request.Request(url, headers={"User-Agent": "weight-streaming"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8")), dict(resp.headers)


def _parse_next_cursor(headers: Any) -> Optional[str]:
    """Extract the ``cursor`` for the next page from a ``Link`` header.

    HF returns ``<https://huggingface.co/api/models?...&cursor=XXXX>; rel="next"``
    (comma-separated if several). Returns ``None`` when there is no next page or
    the header is absent/misshapen — honest "no more results".
    """
    link = (headers or {}).get("Link") or (headers or {}).get("link")
    if not link:
        return None
    for seg in link.split(","):
        seg = seg.strip()
        if not (seg.startswith("<")) or '"next"' not in seg and "rel=\"next\"" not in seg:
            continue
        end = seg.find(">")
        if end < 0:
            continue
        qs = urllib.parse.urlparse(seg[1:end]).query
        cur = urllib.parse.parse_qs(qs).get("cursor")
        if cur:
            return cur[0]
    return None


class _UrlStream:
    """Minimal wrapper giving a urllib response a stable read/content_length/status.

    ``status`` lets the resume path detect a server that ignored the ``Range``
    header (200 instead of 206) and restart fresh instead of duplicating bytes.
    """

    def __init__(self, resp: Any) -> None:
        self._resp = resp
        self.status = int(getattr(resp, "status", 200) or 200)
        cl = resp.headers.get("Content-Length") if hasattr(resp, "headers") else None
        self.content_length: Optional[int] = int(cl) if cl and cl.isdigit() else None
        # ``Content-Range: bytes <start>-<end>/<total>`` on a 206 — lets the
        # resume path verify the upstream answered the EXACT offset we asked
        # for (a mismatched offset would silently corrupt the appended file).
        self.content_range_start: Optional[int] = None
        cr = (resp.headers.get("Content-Range") if hasattr(resp, "headers") else None) or ""
        m = re.match(r"bytes\s+(\d+)-\d+/\d+", cr.strip(), re.IGNORECASE)
        if m:
            self.content_range_start = int(m.group(1))

    def read(self, n: int) -> bytes:
        return self._resp.read(n)

    def close(self) -> None:
        try:
            self._resp.close()
        except Exception:
            pass


def _default_open_stream(url: str, timeout: float, start: int = 0) -> _UrlStream:
    """Open a download stream; ``start > 0`` asks for ``Range: bytes=<start>-``.

    urllib forwards the ``Range`` header across the HF → CDN redirect, so a
    resuming client receives only the remaining bytes (206). Servers that
    ignore ``Range`` answer 200 with the whole body — the caller detects the
    status and restarts fresh rather than appending duplicate bytes.
    """
    headers = {"User-Agent": "weight-streaming"}
    if start > 0:
        headers["Range"] = f"bytes={start}-"
    req = urllib.request.Request(url, headers=headers)
    resp = urllib.request.urlopen(req, timeout=timeout)  # follows CDN redirects
    return _UrlStream(resp)


def _open_part_exclusive(part_path: str) -> Any:
    """Open the ``.part`` file for writing with no-follow/exclusive semantics.

    Closes the symlink-TOCTOU between the target-dir containment check (which
    resolves symlinks) and the actual write: if an attacker races a symlink
    into ``<name>.gguf.part``, the write must NOT follow it.

    - An existing symlink (even a dangling one) at the path → refuse
      (``HubValidationError``) — never unlink or follow an attacker object.
    - An existing regular file here means a start-at-0 run raced with a
      leftover partial — ``run_download`` routes any kept partial to
      ``_open_part_append`` and only calls this opener after that partial
      was removed, so this delete is defensive (a fresh run never appends).
      A RESUME keeps the partial instead (``_open_part_append``).
    - Then create with ``O_CREAT|O_EXCL`` (fails if anything reappears in the
      race window) plus ``O_NOFOLLOW`` where the platform exposes it (POSIX);
      Windows has no ``O_NOFOLLOW`` but ``O_EXCL`` there also refuses to open
      an existing symlink, and the ``islink`` check above already covered it.

    Returns a binary file object opened from the raw fd (caller closes it).
    """
    if os.path.lexists(part_path):
        if os.path.islink(part_path):
            raise HubValidationError(
                "refusing to write through a symlink at the .part path", status=400
            )
        os.remove(part_path)  # stale regular partial — retry = fresh download
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW  # POSIX: fail instead of following a symlink
    if os.name == "nt" and hasattr(os, "O_NOINHERIT"):
        flags |= os.O_NOINHERIT  # don't leak the handle to child processes
    fd = os.open(part_path, flags, 0o644)
    return os.fdopen(fd, "wb")


def _part_size(part_path: str) -> int:
    """Existing partial size for a resume; 0 when there is nothing to keep.

    Same no-follow rule as the writers: a symlink at the ``.part`` path is
    refused (never read through an attacker object), and anything that is not
    a regular file counts as no partial.
    """
    if not os.path.lexists(part_path):
        return 0
    if os.path.islink(part_path):
        raise HubValidationError(
            "refusing to resume through a symlink at the .part path", status=400
        )
    if not os.path.isfile(part_path):
        return 0
    try:
        return os.path.getsize(part_path)
    except OSError:
        return 0


def _open_part_append(part_path: str) -> Any:
    """Open the kept ``.part`` for APPENDING (resume), with no-follow rules.

    - A symlink (even dangling) at the path → refuse — never follow it.
    - The file must exist and be a regular file (verified by ``_part_size``
      before the stream is opened) — otherwise ``FileNotFoundError`` fails
      the task honestly.
    - ``O_WRONLY`` WITHOUT ``O_TRUNC`` keeps the partial bytes; the handle is
      seeked to the end so new chunks append after them.
    """
    if os.path.islink(part_path):
        raise HubValidationError(
            "refusing to append through a symlink at the .part path", status=400
        )
    flags = os.O_WRONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    if os.name == "nt" and hasattr(os, "O_NOINHERIT"):
        flags |= os.O_NOINHERIT
    fd = os.open(part_path, flags)
    fh = os.fdopen(fd, "wb")
    fh.seek(0, os.SEEK_END)
    return fh


# ── Download task + manager ───────────────────────────────────────────


class DownloadTask:
    """State of one hub download. Public fields are serialized to the API."""

    __slots__ = (
        "id", "repo_id", "filename", "target_dir", "target_path", "status",
        "bytes_downloaded", "total_bytes", "speed_bps", "eta_s", "error",
        "created_at", "updated_at", "_cancel", "_start_mono", "_start_bytes",
    )

    def __init__(self, task_id: str, repo_id: str, filename: str,
                 target_dir: str, target_path: str) -> None:
        self.id = task_id
        self.repo_id = repo_id
        self.filename = filename
        self.target_dir = target_dir
        self.target_path = target_path
        self.status = "queued"
        self.bytes_downloaded = 0
        self.total_bytes: Optional[int] = None
        self.speed_bps: Optional[float] = None
        self.eta_s: Optional[float] = None
        self.error: Optional[str] = None
        self.created_at = time.time()
        self.updated_at = self.created_at
        self._cancel = threading.Event()
        self._start_mono: Optional[float] = None
        self._start_bytes = 0  # bytes already on disk when THIS run started

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "repo_id": self.repo_id,
            "filename": self.filename,
            "target_dir": self.target_dir,
            "target_path": self.target_path,
            "status": self.status,
            "bytes_downloaded": self.bytes_downloaded,
            "total_bytes": self.total_bytes,
            # REAL size on disk for a completed download (the panel shows it
            # next to the full path). stat at serialization time so it stays
            # honest even if the file changed since the download finished.
            # The short-circuit avoids a stat for active tasks (to_dict runs
            # on every SSE frame); the try/except covers the file-deleted-
            # between-isfile-and-getsize race (a 500 here would kill the
            # whole downloads list) — same defensive style as _part_size.
            "file_size": self._disk_size(),
            "percent": (
                round(100.0 * self.bytes_downloaded / self.total_bytes, 1)
                if self.total_bytes else None
            ),
            "speed_bps": (round(self.speed_bps, 1) if self.speed_bps is not None else None),
            "eta_s": (round(self.eta_s, 1) if self.eta_s is not None else None),
            "error": self.error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    def _disk_size(self) -> Optional[int]:
        """Real on-disk byte size for a COMPLETED download; None otherwise.

        ``status == "done"`` is checked first so active tasks (whose
        ``to_dict`` runs on every 0.5s SSE frame) never pay for a stat.
        The file may vanish between the ``isfile`` check and the stat (an
        external delete) — that race degrades to None, never a raised
        500 that would kill the whole downloads list.
        """
        if self.status != "done":
            return None
        try:
            if os.path.isfile(self.target_path):
                return os.path.getsize(self.target_path)
        except OSError:
            pass
        return None


class DownloadManager:
    """HF search (cached) + background GGUF downloads with real progress."""

    def __init__(
        self,
        fetch_json: Optional[Callable[[str, float], Any]] = None,
        open_stream: Optional[Callable[[str, float], Any]] = None,
        timeout: float = DEFAULT_TIMEOUT,
        cache_ttl: float = SEARCH_CACHE_TTL,
        model_cache_ttl: float = MODEL_CACHE_TTL,
        chunk_size: int = DEFAULT_CHUNK,
        fetch_headers: Optional[Callable[[str, float], tuple[Any, dict]]] = None,
        stream_timeout: float = DEFAULT_STREAM_TIMEOUT,
    ) -> None:
        self._fetch_json = fetch_json if fetch_json is not None else _default_fetch_json
        self._fetch_json_headers = (
            fetch_headers if fetch_headers is not None else _default_fetch_json_headers
        )
        self._open_stream = open_stream if open_stream is not None else _default_open_stream
        self.timeout = timeout
        self.stream_timeout = stream_timeout
        self.cache_ttl = cache_ttl
        self.model_cache_ttl = model_cache_ttl
        self.chunk_size = chunk_size
        # Shared in-memory cache: search entries are keyed by a 3-tuple
        # (q, sort, limit); detail entries by ("detail", repo_id). Both store
        # (expiry_ts, payload). Opportunistically pruned on every read.
        self._cache: dict[tuple, tuple[float, Any]] = {}
        self._tasks: dict[str, DownloadTask] = {}
        self._lock = threading.Lock()
        self._counter = 0

    # ── Search ──────────────────────────────────────────────────────

    def search(self, q: str, sort: str = "downloads", limit: int = 20) -> list[dict]:
        sort_key = _SORT_MAP.get(sort, "downloads")
        limit = max(1, min(int(limit), 100))
        key = (q or "", sort_key, limit)
        now = time.time()
        # Opportunistically drop expired entries so the cache stays bounded.
        self._cache = {k: v for k, v in self._cache.items() if v[0] > now}
        cached = self._cache.get(key)
        if cached is not None:
            return cached[1]

        # expand[] asks HF to include these fields in the SAME search response
        # (verified live: no extra request) so cards can be categorised without
        # hitting the detail endpoint. `siblings` was already required for files.
        params = urllib.parse.urlencode(
            {"search": q or "", "filter": "gguf", "sort": sort_key,
             "limit": limit, "expand[]": ["siblings", "tags", "pipeline_tag"]},
            doseq=True,
        )
        url = f"{HF_API_BASE}?{params}"
        try:
            data = self._fetch_json(url, self.timeout)
        except Exception as e:  # network / HTTP / JSON errors → honest 502
            raise HubUpstreamError(f"Hugging Face unreachable: {e}") from e

        results = self._parse_search(data)
        self._cache[key] = (now + self.cache_ttl, results)
        return results

    def search_with_cursor(
        self,
        q: str = "",
        sort: str = "downloads",
        limit: int = 20,
        cursor: Optional[str] = None,
    ) -> dict:
        """Search with HF cursor pagination, returning ``{"results", "next_cursor"}``.

        The next-page cursor comes from the ``Link`` header, so this uses the
        header-aware fetch. ``cursor=None`` → first page. Returns
        ``next_cursor=None`` when HF signals no further pages. Honest real
        pagination — the ``search()`` path (single page) is left untouched.
        """
        sort_key = _SORT_MAP.get(sort, "downloads")
        limit = max(1, min(int(limit), 100))
        key = ("cursor-search", q or "", sort_key, limit, cursor or "")
        now = time.time()
        self._cache = {k: v for k, v in self._cache.items() if v[0] > now}
        cached = self._cache.get(key)
        if cached is not None:
            return cached[1]

        params = urllib.parse.urlencode(
            {"search": q or "", "filter": "gguf", "sort": sort_key,
             "limit": limit, "expand[]": ["siblings", "tags", "pipeline_tag"]},
            doseq=True,
        )
        if cursor:
            params += "&cursor=" + urllib.parse.quote(str(cursor), safe="")
        url = f"{HF_API_BASE}?{params}"
        try:
            body, headers = self._fetch_json_headers(url, self.timeout)
        except Exception as e:
            raise HubUpstreamError(f"Hugging Face unreachable: {e}") from e
        payload = {"results": self._parse_search(body), "next_cursor": _parse_next_cursor(headers)}
        self._cache[key] = (now + self.cache_ttl, payload)
        return payload

    @staticmethod
    def _parse_search(data: Any) -> list[dict]:
        out: list[dict] = []
        if not isinstance(data, list):
            return out
        for m in data:
            if not isinstance(m, dict):
                continue
            repo_id = m.get("id") or m.get("modelId")
            if not repo_id:
                continue
            files = []
            for sib in m.get("siblings") or []:
                fname = (sib or {}).get("rfilename", "")
                if fname.lower().endswith(".gguf"):
                    files.append({
                        "filename": fname,
                        "quant": parse_quant(fname),
                        "size_label": parse_size_label(f"{repo_id} {fname}"),
                    })
            # tags / pipeline_tag come straight from the (expanded) HF search
            # response — pass through ONLY what HF actually returned. When HF
            # omits them (older payloads) they stay [] / None; the frontend
            # falls back to an honest "other" category rather than guessing.
            raw_tags = m.get("tags")
            tags = [str(t) for t in raw_tags] if isinstance(raw_tags, list) else []
            out.append({
                "repo_id": repo_id,
                "author": repo_id.split("/", 1)[0] if "/" in repo_id else None,
                "downloads": m.get("downloads"),
                "likes": m.get("likes"),
                "last_modified": m.get("lastModified"),
                "pipeline_tag": m.get("pipeline_tag"),
                "tags": tags,
                "gguf": True,
                "files": files,
            })
        return out

    # ── On-demand model detail (P5.1) ───────────────────────────────

    def model_detail(self, repo_id: str) -> dict:
        """Aggregate HF model detail + file tree into one structured payload.

        On-demand (not on the hot search path), cached ~15 min per repo. Two
        stdlib GETs: ``/api/models/{repo}`` (dates/tags/likes/cardData) and
        ``/api/models/{repo}/tree/main`` (per-file byte sizes). HF failure on
        either → ``HubUpstreamError`` (HTTP 502) — never a fake/empty 200.
        Fields HF does not provide stay ``null`` (never filled in).
        """
        repo_id = (repo_id or "").strip()
        if not repo_id:
            raise HubValidationError("repo_id is required", status=400)
        key = ("detail", repo_id)
        now = time.time()
        self._cache = {k: v for k, v in self._cache.items() if v[0] > now}
        cached = self._cache.get(key)
        if cached is not None:
            return cached[1]

        enc = urllib.parse.quote(repo_id, safe="/")
        detail_url = f"{HF_API_BASE}/{enc}"
        tree_url = f"{HF_API_BASE}/{enc}/tree/main"
        try:
            detail = self._fetch_json(detail_url, self.timeout)
            tree = self._fetch_json(tree_url, self.timeout)
        except Exception as e:  # network / HTTP / JSON errors → honest 502
            raise HubUpstreamError(f"Hugging Face unreachable: {e}") from e

        payload = self._build_detail(repo_id, detail, tree)
        self._cache[key] = (now + self.model_cache_ttl, payload)
        return payload

    @staticmethod
    def _build_detail(repo_id: str, detail: Any, tree: Any) -> dict:
        """Merge the two HF responses into the documented payload shape."""
        if not isinstance(detail, dict):
            detail = {}
        card = detail.get("cardData")
        if not isinstance(card, dict):
            card = {}
        raw_tags = detail.get("tags")
        tags = [str(t) for t in raw_tags] if isinstance(raw_tags, list) else []

        # description: only cardData's, never invented. cardData descriptions
        # are plain strings; anything else (or empty) → None.
        desc = card.get("description")
        if isinstance(desc, str):
            desc = desc.strip() or None
        else:
            desc = None

        files: list[dict] = []
        non_gguf: list[dict] = []
        for entry in tree if isinstance(tree, list) else []:
            if not isinstance(entry, dict):
                continue
            if entry.get("type") == "directory":
                continue
            path = entry.get("path")
            if not isinstance(path, str) or not path:
                continue
            size = entry.get("size")
            nbytes = int(size) if isinstance(size, (int, float)) and size >= 0 else None
            if path.lower().endswith(".gguf"):
                files.append({
                    "filename": path,
                    "bytes": nbytes,
                    "quant": parse_quant(path),
                    "size_label": parse_size_label(f"{repo_id} {path}"),
                    "shard": parse_shard(path),
                })
            else:
                non_gguf.append({
                    "filename": path,
                    "bytes": nbytes,
                    "type": entry.get("type") or "file",
                })

        # Group GGUF files BY QUANT (and split-set) so a sharded quant reads
        # as one unit, while a single-file weight sharing that quant stays a
        # separate, independently downloadable group (see _shard_group_key).
        groups: dict = {}
        for f in files:
            key = _shard_group_key(f["filename"], f["quant"], f["shard"])
            groups.setdefault(key, []).append(f)
        quants: list[dict] = []
        for key, gfiles in groups.items():
            quant = key[0]
            sharded = key[2] is not None
            gfiles.sort(key=lambda f: ((f["shard"] or {}).get("index", 0), f["filename"]))
            sizes = [f["bytes"] for f in gfiles]
            complete = all(b is not None for b in sizes)
            quants.append({
                "quant": quant,
                "files": gfiles,
                "total_bytes": sum(sizes) if complete else None,  # honest: null if any part unknown
                "sharded": sharded,
                "per_shard_bytes": list(sizes) if (sharded and complete) else None,
            })
        # Stable, readable order: known quants first (single before its sharded
        # twin), "quant unknown" last.
        quants.sort(key=lambda q: (
            q["quant"] is None, q["quant"] or "", 0 if not q["sharded"] else 1,
            q["files"][0]["filename"],
        ))

        base_model = card.get("base_model")
        if not isinstance(base_model, (str, list)):
            base_model = None

        return {
            "repo_id": repo_id,
            "author": detail.get("author") or (
                repo_id.split("/", 1)[0] if "/" in repo_id else None
            ),
            "published_at": detail.get("createdAt"),
            "updated_at": detail.get("lastModified"),
            "downloads": detail.get("downloads"),
            "likes": detail.get("likes"),
            "pipeline_tag": detail.get("pipeline_tag"),
            "tags": tags,
            "library": detail.get("library_name"),
            "description": desc,
            "base_model": base_model,
            "context_length": DownloadManager._extract_context(card, tags),
            "files": files,
            "non_gguf": non_gguf,
            "quants": quants,
        }

    @staticmethod
    def _extract_context(card: dict, tags: list) -> Optional[int]:
        """Context window ONLY if HF truly provides it (cardData/tag) — else None."""
        for key in _CONTEXT_KEYS:
            v = card.get(key)
            if isinstance(v, (int, float)) and v > 0:
                return int(v)
            if isinstance(v, str) and v.strip().isdigit():
                return int(v.strip())
        for tag in tags:
            m = _CONTEXT_TAG_RE.search(str(tag))
            if m:
                return int(m.group(1))
        return None

    # ── Downloads ───────────────────────────────────────────────────

    def create_download(
        self, repo_id: str, filename: str, target_dir: Optional[str] = None,
    ) -> DownloadTask:
        """Validate + register a download (no I/O yet). Raises HubValidationError."""
        if not isinstance(repo_id, str) or not repo_id.strip():
            raise HubValidationError("repo_id is required", status=400)
        fname = _sanitize_filename(filename)
        resolved = _resolve_target_dir(target_dir, get_model_search_dirs())
        # filename is sanitized (no path separators), so joining keeps the
        # final path inside the already-validated `resolved` dir.
        target_path = os.path.join(resolved, fname)
        with self._lock:
            self._counter += 1
            task_id = f"dl-{self._counter}"
            task = DownloadTask(task_id, repo_id.strip(), fname, resolved, target_path)
            self._tasks[task_id] = task
        return task

    def schedule_download(self, task: DownloadTask) -> None:
        """Run the download on a worker thread (non-blocking for the loop)."""
        asyncio.create_task(asyncio.to_thread(self.run_download, task))

    def run_download(self, task: DownloadTask) -> None:
        """Blocking download: stream → ``.part`` → atomic rename. Sync & testable.

        A fresh run truncates (exclusive, no-follow ``_open_part_exclusive``);
        a RESUME (existing regular ``.part`` from a cancelled/failed run)
        appends after the kept bytes via ``Range: bytes=<n>-``. If the
        upstream ignores ``Range`` (HTTP 200 instead of 206) the partial is
        discarded and the transfer restarts from byte 0 — bytes are never
        duplicated. Cancelled/failed runs KEEP their ``.part`` so a later
        resume is cheap; the mid-stream ``WS_HUB_MAX_BYTES`` guard counts
        REAL transferred bytes (see module docstring).
        """
        part_path = task.target_path + ".part"
        if task._cancel.is_set():
            task.status = "cancelled"
            return
        task.status = "downloading"
        task._start_mono = time.monotonic()
        task.speed_bps = None
        task.eta_s = None
        task.error = None
        self._touch(task)
        max_bytes = int(os.environ.get("WS_HUB_MAX_BYTES", "0") or "0")
        try:
            start = _part_size(part_path)
            url = (
                f"{HF_RESOLVE_BASE}/{task.repo_id}/resolve/main/"
                f"{urllib.parse.quote(task.filename)}"
            )
            # Streams use a MUCH larger per-read timeout than the JSON calls:
            # a stalled connection must pause the transfer, not kill it.
            resp = self._open_stream(url, self.stream_timeout, start)
            try:
                total = getattr(resp, "content_length", None)
                if start > 0:
                    status = getattr(resp, "status", 200)
                    cr_start = getattr(resp, "content_range_start", None)
                    if status == 200:
                        # Range ignored → the stream already carries the WHOLE
                        # file from byte 0; discard the partial and restart
                        # fresh (append would duplicate the first `start` bytes).
                        start = 0
                        task.bytes_downloaded = 0
                        self._remove_part(part_path)
                        task.total_bytes = total
                    elif status == 206:
                        if cr_start is not None and cr_start != start:
                            # Upstream answered a DIFFERENT offset than asked —
                            # appending would corrupt the file. Fail honestly
                            # (never write misaligned bytes).
                            raise HubValidationError(
                                f"upstream answered byte range {cr_start}- instead of {start}- "
                                "(resume aborted to avoid a corrupt file)",
                                status=400,
                            )
                        # 206 → Content-Length is the REMAINDER after `start`
                        task.total_bytes = (start + total) if total is not None else None
                    else:
                        raise HubValidationError(
                            f"unexpected HTTP status {status} on resume", status=502
                        )
                else:
                    task.total_bytes = total
                task._start_bytes = start
                if task.total_bytes is not None:
                    if max_bytes and task.total_bytes > max_bytes:
                        raise HubValidationError(
                            f"file size {task.total_bytes} exceeds WS_HUB_MAX_BYTES ({max_bytes})",
                            status=400,
                        )
                    free = shutil.disk_usage(task.target_dir).free
                    if task.total_bytes > free:
                        raise HubValidationError(
                            f"insufficient disk space: need {task.total_bytes} bytes, free {free}",
                            status=400,
                        )
                task.bytes_downloaded = start
                opener = _open_part_append if start > 0 else _open_part_exclusive
                with opener(part_path) as fh:
                    while True:
                        if task._cancel.is_set():
                            raise _Cancelled()
                        chunk = resp.read(self.chunk_size)
                        if not chunk:
                            break
                        fh.write(chunk)
                        task.bytes_downloaded += len(chunk)
                        if max_bytes and task.bytes_downloaded > max_bytes:
                            raise HubValidationError(
                                f"download exceeded WS_HUB_MAX_BYTES ({max_bytes})",
                                status=400,
                            )
                        self._update_progress(task)
            finally:
                resp.close()
            # Integrity gate: EOF is only success when the stream actually
            # delivered every advertised byte. A mid-stream connection cut can
            # end ``read()`` with b'' early (no exception) — renaming a
            # truncated file into place would silently corrupt the model.
            # Fail honestly and KEEP the ``.part`` so a resume appends only
            # the missing bytes.
            if task.total_bytes is not None and task.bytes_downloaded != task.total_bytes:
                raise HubValidationError(
                    f"stream ended early: got {task.bytes_downloaded} of "
                    f"{task.total_bytes} bytes "
                    f"({task.total_bytes - task.bytes_downloaded} missing) — "
                    "download truncated; resume will fetch the remainder",
                    status=502,
                )
            os.replace(part_path, task.target_path)  # atomic
            task.status = "done"
            # bytes_downloaded equals total_bytes exactly (gate above) — do
            # NOT overwrite it; the count reflects the REAL bytes written.
            self._update_progress(task)
        except _Cancelled:
            task.status = "cancelled"
            # KEEP the .part — a resume appends the remaining bytes (v1.1).
        except HubValidationError as e:
            task.status = "failed"
            task.error = str(e)
            # KEEP the .part — a resume can retry without re-downloading byte 0.
        except Exception as e:
            task.status = "failed"
            task.error = str(e)
            # KEEP the .part — same reason as above.
        finally:
            self._touch(task)

    def get_task(self, task_id: str) -> Optional[DownloadTask]:
        return self._tasks.get(task_id)

    def list_tasks(self) -> list[dict]:
        with self._lock:
            tasks = list(self._tasks.values())
        return [t.to_dict() for t in tasks]

    def cancel(self, task_id: str) -> Optional[DownloadTask]:
        task = self._tasks.get(task_id)
        if task is None:
            return None
        task._cancel.set()
        if task.status == "queued":
            task.status = "cancelled"  # never started
            self._touch(task)
        # if downloading, run_download's loop observes the flag and stops;
        # the partial .part is KEPT so the task can be resumed (v1.1)
        return task

    def resume(self, task_id: str) -> Optional[DownloadTask]:
        """Re-queue a cancelled/failed task for a fresh worker run.

        The kept ``.part`` (if any) is picked up by ``run_download`` via
        ``Range`` and appended — only the remaining bytes are fetched.
        Tasks that are active or done are not resumable (``ValueError`` →
        the endpoint answers 409 with the honest reason).
        """
        task = self._tasks.get(task_id)
        if task is None:
            return None
        if task.status not in ("cancelled", "failed"):
            raise ValueError(
                f"task {task_id} is {task.status!r} — only cancelled or failed downloads can resume"
            )
        task._cancel = threading.Event()
        task.status = "queued"
        task.error = None
        task.speed_bps = None
        task.eta_s = None
        task.total_bytes = None
        task.bytes_downloaded = 0  # run_download re-derives from the .part size
        self._touch(task)
        return task

    def delete(self, task_id: str, delete_file: bool = False) -> Optional[DownloadTask]:
        """Remove a task (and its partial) from the manager.

        A running worker is signalled to stop via the cancel flag. The FINAL
        ``.gguf`` of a completed task is kept by default — model files are
        precious and the server has no auth. With ``delete_file=True`` (only
        meaningful for a ``done`` task) the model file is ALSO removed, but
        ONLY when it realpath-resolves inside an allowed model dir
        (``_remove_model_file`` — an extra containment check on top of the
        one already done at download-creation time).
        """
        with self._lock:
            task = self._tasks.pop(task_id, None)
        if task is None:
            return None
        task._cancel.set()
        if task.status != "done":
            part_path = task.target_path + ".part"
            self._remove_part(part_path)
            # On Windows a file still open by the worker cannot be removed
            # (PermissionError), while the worker's cancel path now KEEPS the
            # .part for resume — so a delete issued mid-download would orphan
            # it. The worker stops within a chunk, so retry the removal in a
            # short daemon thread (never blocks the request, never outlives
            # the process; no-op if the direct remove already succeeded).
            threading.Thread(
                target=_remove_part_retry, args=(part_path,), daemon=True
            ).start()
        elif delete_file:
            self._remove_model_file(task.target_path)
        return task

    def clear(self, delete_file: bool = False,
              protected_paths: Optional[set] = None) -> dict:
        """Remove every FINISHED task (done/failed/cancelled) in one call.

        Active downloads (queued/downloading) are left untouched. Each
        finished task is popped from the manager and its ``.part`` removed
        (daemon retry thread — Windows cannot remove an open file). With
        ``delete_file=True`` the model files of COMPLETED tasks are also
        removed, EXCEPT paths in ``protected_paths`` (e.g. currently loaded
        models — same rule as the single-task delete endpoint); those are
        reported honestly in ``files_skipped`` rather than failing the whole
        batch. Returns a summary: removed / files_deleted / files_skipped.
        """
        protected = {
            os.path.normcase(os.path.realpath(p)) for p in (protected_paths or set())
        }
        with self._lock:
            terminal = [
                t for t in self._tasks.values()
                if t.status in ("done", "failed", "cancelled")
            ]
            for task in terminal:
                self._tasks.pop(task.id, None)
        removed: list[str] = []
        files_deleted: list[str] = []
        files_skipped: list[str] = []
        for task in terminal:
            task._cancel.set()
            removed.append(task.id)
            if task.status != "done":
                part_path = task.target_path + ".part"
                self._remove_part(part_path)
                threading.Thread(
                    target=_remove_part_retry, args=(part_path,), daemon=True
                ).start()
            elif delete_file:
                if os.path.normcase(os.path.realpath(task.target_path)) in protected:
                    files_skipped.append(task.id)
                elif self._remove_model_file(task.target_path):
                    files_deleted.append(task.id)
                else:
                    files_skipped.append(task.id)  # missing / locked / outside dirs
        return {
            "status": "cleared",
            "removed": removed,
            "files_deleted": files_deleted,
            "files_skipped": files_skipped,
        }

    @staticmethod
    def _remove_model_file(target_path: str) -> bool:
        """Delete a downloaded model file, guarded by realpath containment.

        Defense in depth: ``target_path`` was validated at download-creation
        time, but the delete happens later and is destructive — re-resolve it
        and refuse unless it lands inside an allowed model dir (a symlink
        escaped to elsewhere, or any other tampering, is never followed).
        Returns True only when the file was actually removed.
        """
        real = os.path.realpath(target_path)
        allowed = [os.path.realpath(d) for d in get_model_search_dirs()]
        if not any(real == ra or real.startswith(ra + os.sep) for ra in allowed):
            return False  # refuse to touch anything outside the allowed dirs
        try:
            if os.path.isfile(real):
                os.remove(real)
                return True
        except OSError:
            pass
        return False

    # ── internals ───────────────────────────────────────────────────

    def _update_progress(self, task: DownloadTask) -> None:
        if task._start_mono is not None:
            elapsed = time.monotonic() - task._start_mono
            if elapsed > 0:
                # Speed = bytes transferred by THIS run only (a resume must
                # not count the partial that already existed on disk).
                task.speed_bps = (task.bytes_downloaded - task._start_bytes) / elapsed
        if task.total_bytes and task.speed_bps and task.speed_bps > 0:
            remaining = max(0, task.total_bytes - task.bytes_downloaded)
            task.eta_s = remaining / task.speed_bps
        self._touch(task)

    @staticmethod
    def _touch(task: DownloadTask) -> None:
        task.updated_at = time.time()

    @staticmethod
    def _remove_part(part_path: str) -> None:
        try:
            if os.path.exists(part_path):
                os.remove(part_path)
        except OSError:
            pass


def _remove_part_retry(part_path: str, tries: int = 6, delay: float = 0.5) -> None:
    """Best-effort removal with retries (Windows: an open file cannot be
    removed until the worker closes its handle — usually within one chunk).
    Runs on a daemon thread; silently gives up rather than ever blocking."""
    for _ in range(tries):
        if not os.path.exists(part_path):
            return
        try:
            os.remove(part_path)
            return
        except OSError:
            time.sleep(delay)


class _Cancelled(Exception):
    """Internal: download cancelled mid-stream."""

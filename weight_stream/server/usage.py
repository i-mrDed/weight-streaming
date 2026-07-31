"""Generation usage history for the API server (P4).

Records a compact, honest summary of every generation through a single choke
point (``ModelManager``) into:

- an in-memory ring buffer (default capacity 500, oldest → newest), and
- an append-only JSONL file (``data/usage_history.jsonl`` by default) that is
  truncated back to the capacity so disk never grows unbounded.

Every value is real telemetry from the backend's ``get_stats()`` — token
count, tokens/sec, elapsed, and a short paging summary. When a path has no
real tokens/sec (e.g. a stream that never recorded backend stats) ``tok_s``
is stored as ``None`` (serialized to JSON ``null``); numbers are never
fabricated (ADR-003 honest telemetry).
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any, Optional

DEFAULT_CAPACITY = 500
DEFAULT_PATH = Path("data") / "usage_history.jsonl"

# Paging keys worth keeping per record (the full backend paging dict carries
# long human-readable notes; history only needs the quantitative summary).
_PAGING_SUMMARY_KEYS = (
    "faults",
    "faults_per_token",
    "fault_mb_per_token",
    "disk_demand_mb",
    "disk_mb_per_token",
)


def _summarize_paging(paging: Any) -> Optional[dict]:
    """Return a compact, real-values-only subset of a backend paging dict."""
    if not isinstance(paging, dict):
        return None
    summary = {k: paging[k] for k in _PAGING_SUMMARY_KEYS if k in paging}
    return summary or None


class UsageRecorder:
    """Thread-safe ring buffer + JSONL persistence for generation usage."""

    def __init__(
        self,
        path: str | Path | None = None,
        capacity: int = DEFAULT_CAPACITY,
    ) -> None:
        self._capacity = max(1, int(capacity))
        self._path = Path(path) if path is not None else DEFAULT_PATH
        self._records: list[dict] = []
        self._lock = threading.RLock()
        self._load()

    # ── Writing ─────────────────────────────────────────────────────

    def record(
        self,
        *,
        model: str,
        tokens: Optional[int],
        tok_s: Optional[float],
        elapsed_s: Optional[float],
        paging: Any = None,
        ts: Optional[int] = None,
    ) -> dict:
        """Append one generation record and persist it.

        ``ts`` is epoch milliseconds (defaults to now). ``tok_s``/``elapsed_s``
        may be ``None`` when a path has no real measurement.
        """
        rec: dict = {
            "ts": int(ts if ts is not None else time.time() * 1000),
            "model": model,
            "tokens": tokens,
            "tok_s": (round(float(tok_s), 2) if tok_s is not None else None),
            "elapsed_s": (round(float(elapsed_s), 3) if elapsed_s is not None else None),
        }
        paging_summary = _summarize_paging(paging)
        if paging_summary is not None:
            rec["paging"] = paging_summary

        with self._lock:
            self._records.append(rec)
            if len(self._records) > self._capacity:
                # Keep only the newest `capacity` records.
                self._records = self._records[-self._capacity:]
            self._persist()
        return rec

    # ── Reading ─────────────────────────────────────────────────────

    def history(
        self,
        limit: Optional[int] = None,
        since: Optional[int] = None,
    ) -> list[dict]:
        """Return records oldest→newest.

        ``since`` filters to ``ts >= since`` (epoch ms); ``limit`` keeps the
        newest N of what remains (clamped to the ring capacity).
        """
        with self._lock:
            records = list(self._records)
        if since is not None:
            records = [r for r in records if r.get("ts", 0) >= since]
        if limit is not None:
            records = records[-limit:] if limit > 0 else []
        return records

    @property
    def capacity(self) -> int:
        return self._capacity

    def __len__(self) -> int:
        with self._lock:
            return len(self._records)

    # ── Persistence ─────────────────────────────────────────────────

    def _load(self) -> None:
        """Seed the ring from the JSONL file (tail ``capacity`` lines)."""
        if not self._path.exists():
            return
        try:
            lines = self._path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return
        records: list[dict] = []
        for line in lines[-self._capacity:]:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        self._records = records

    def _persist(self) -> None:
        """Rewrite the JSONL file from the in-memory ring (caller holds lock).

        The in-memory ring is the source of truth and is already capped, so
        rewriting keeps the file equal to the ring and bounded on disk.
        """
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._path.with_suffix(self._path.suffix + ".tmp")
            with tmp.open("w", encoding="utf-8") as fh:
                for rec in self._records:
                    fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            tmp.replace(self._path)
        except OSError:
            # Telemetry must never break generation; drop the write quietly.
            pass

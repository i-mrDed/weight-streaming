"""
Streaming buffer abstraction prototype (TASKS.md #145).

Bridges the two worlds that observe a streaming buffer:

1. **Simulator-backed** — the existing `StreamingBuffer` (LRU/LFU/priority)
   driven by synthetic access patterns. `SimulatorBufferAdapter` wraps it
   without changing its behavior.
2. **Telemetry-backed** — production can't see llama.cpp's expert accesses
   (`StreamingBuffer.total_accesses = 0` — ARCHITECTURE.md §0 open gap), but
   the server already ships OS signals in `generation.paging`
   (faults_per_token, disk_mb_per_token). `TelemetryBufferObserver` converts
   those into buffer-equivalent stats.

Both implement the same `BufferBackend` protocol and return the same
`BufferStatsView`, so downstream code (and the future `core/native/`
tracker) can consume either source. Predicted throughput uses the
calibrated physics bandwidths from EXP-025 (cpu-ram hit path, disk-mmap
miss path) — never made-up numbers.

Per ADR-003 this does NOT intercept llama.cpp reads; it observes.
"""
from dataclasses import dataclass
from typing import Dict, Optional, Protocol

from . import physics
from .buffer import StreamingBuffer
from .config import SimConfig


@dataclass
class BufferStatsView:
    """Unified stats from either a simulator buffer or telemetry observer.

    All values are buffer-equivalent: a telemetry observer reports what an
    ideal buffer WOULD have produced from the OS signals it saw.
    """
    source: str                    # "simulator" | "telemetry"
    accesses: int = 0
    hits: int = 0
    misses: int = 0
    evictions: int = 0
    hit_rate: float = 0.0
    bytes_per_token_gb: float = 0.0   # physics-derived active bytes/token
    miss_bytes_per_token_gb: float = 0.0
    stall_ms_per_token: float = 0.0   # miss path time (disk-mmap BW)
    compute_ms_per_token: float = 0.0 # hit path time (cpu-ram BW)
    predicted_tok_per_sec: float = 0.0
    ram_bw_gbps: float = 0.0          # calibrated BW used (hit path)
    disk_bw_gbps: float = 0.0         # calibrated BW used (miss path)


class BufferBackend(Protocol):
    """Any buffer observer: simulator-backed or telemetry-backed."""

    def on_access(self, shard_id: int, bytes_gb: float = 0.0) -> bool:
        """Record one access. Returns True on hit. (Telemetry observer is
        event-driven too; it converts paging data into per-token events.)"""
        ...

    def stats(self) -> BufferStatsView:
        """Current buffer-equivalent stats."""
        ...


def predicted_tok_per_sec(
    hit_rate: float,
    bytes_per_token_gb: float,
    ram_bw_gbps: float,
    disk_bw_gbps: float,
) -> float:
    """Physics: time/token = hit bytes at cpu-ram BW + miss bytes at
    disk-mmap BW. Inverse = tok/s. (EXP-025 calibrated BWs.)"""
    if bytes_per_token_gb <= 0:
        return 0.0
    hit_gb = bytes_per_token_gb * hit_rate
    miss_gb = bytes_per_token_gb * (1.0 - hit_rate)
    time_s = hit_gb / ram_bw_gbps + miss_gb / disk_bw_gbps
    return 1.0 / time_s if time_s > 0 else 0.0


class SimulatorBufferAdapter:
    """Wraps the existing StreamingBuffer with the unified interface.

    Behavior of the underlying LRU/LFU/priority buffer is untouched; this
    only records accesses and derives physics-based throughput. Shard bytes
    come from the model config (4 MB per expert shard).
    """

    def __init__(self, buffer: StreamingBuffer, config: SimConfig):
        self._buffer = buffer
        self._cfg = config
        self._shard_bytes_gb = config.model.shard_size_bytes / physics.GB
        self._accesses = 0
        self._hits = 0

    def on_access(self, shard_id: int, bytes_gb: float = 0.0) -> bool:
        self._accesses += 1
        hit = self._buffer.access(shard_id)
        if hit:
            self._hits += 1
        return hit

    def stats(self) -> BufferStatsView:
        bs = self._buffer.get_stats()
        hit_rate = self._hits / self._accesses if self._accesses else 0.0
        bytes_per_token = physics.bytes_per_token_gb(
            self._cfg.model.active_params, self._cfg.model.bits_per_weight
        )
        ram_bw = physics.DEFAULT_EFFECTIVE_BW_GBPS["cpu-ram"]
        disk_bw = physics.DEFAULT_EFFECTIVE_BW_GBPS["disk-mmap"]
        miss_gb = bytes_per_token * (1.0 - hit_rate)
        return BufferStatsView(
            source="simulator",
            accesses=self._accesses,
            hits=self._hits,
            misses=bs.misses,
            evictions=bs.evictions,
            hit_rate=hit_rate,
            bytes_per_token_gb=bytes_per_token,
            miss_bytes_per_token_gb=miss_gb,
            stall_ms_per_token=miss_gb / disk_bw * 1000.0,
            compute_ms_per_token=bytes_per_token * hit_rate / ram_bw * 1000.0,
            predicted_tok_per_sec=predicted_tok_per_sec(
                hit_rate, bytes_per_token, ram_bw, disk_bw
            ),
            ram_bw_gbps=ram_bw,
            disk_bw_gbps=disk_bw,
        )


class TelemetryBufferObserver:
    """Converts production OS signals (generation.paging / spike data) into
    buffer-equivalent stats.

    Input keys (any of these, most-specific wins):
      disk_mb_per_token      — /v1/stats generation.paging (hard faults)
      fault_mb_per_token     — /v1/stats generation.paging (all faults)
      fault_bytes_per_token_MB — spike_page_faults_2026-07-30.json
    Plus token_count / n_tokens for per-token normalization when needed.
    """

    def __init__(
        self,
        bytes_per_token_gb: float,
        ram_bw_gbps: Optional[float] = None,
        disk_bw_gbps: Optional[float] = None,
    ):
        self._bytes_per_token = bytes_per_token_gb
        self._ram_bw = ram_bw_gbps or physics.DEFAULT_EFFECTIVE_BW_GBPS["cpu-ram"]
        self._disk_bw = disk_bw_gbps or physics.DEFAULT_EFFECTIVE_BW_GBPS["disk-mmap"]

    def observe(self, paging: Dict, n_tokens: Optional[int] = None) -> BufferStatsView:
        # Pick the most specific miss-bytes signal available.
        if "disk_mb_per_token" in paging and paging.get("disk_mb_per_token") is not None:
            miss_mb_per_token = paging["disk_mb_per_token"]
        elif "fault_mb_per_token" in paging and paging.get("fault_mb_per_token") is not None:
            miss_mb_per_token = paging["fault_mb_per_token"]
        elif "fault_bytes_per_token_MB" in paging:
            miss_mb_per_token = paging["fault_bytes_per_token_MB"]
        elif "fault_bytes_per_token" in paging:
            miss_mb_per_token = paging["fault_bytes_per_token"] / (1024 * 1024)
        else:
            # No per-token value: derive from totals if available.
            total_mb = paging.get("fault_bytes_MB") or paging.get("fault_mb")
            total = paging.get("faults")
            n = n_tokens or paging.get("tokens") or paging.get("token_count")
            if total_mb and n:
                miss_mb_per_token = total_mb / n
            elif total and n:
                miss_mb_per_token = total * 4 / 1024 / n  # 4 KB pages
            else:
                miss_mb_per_token = 0.0

        miss_gb = miss_mb_per_token / 1000.0
        hit_rate = max(0.0, 1.0 - miss_gb / self._bytes_per_token) \
            if self._bytes_per_token > 0 else 0.0
        return BufferStatsView(
            source="telemetry",
            accesses=n_tokens or paging.get("tokens") or paging.get("token_count") or 0,
            hits=max(0, int((n_tokens or 1) * hit_rate)) if (n_tokens or paging.get("tokens") or paging.get("token_count")) else 0,
            misses=0,  # not directly observable; miss bytes carry the signal
            evictions=0,  # OS manages the page cache; not observable
            hit_rate=hit_rate,
            bytes_per_token_gb=self._bytes_per_token,
            miss_bytes_per_token_gb=miss_gb,
            stall_ms_per_token=miss_gb / self._disk_bw * 1000.0,
            compute_ms_per_token=self._bytes_per_token * hit_rate / self._ram_bw * 1000.0,
            predicted_tok_per_sec=predicted_tok_per_sec(
                hit_rate, self._bytes_per_token, self._ram_bw, self._disk_bw
            ),
            ram_bw_gbps=self._ram_bw,
            disk_bw_gbps=self._disk_bw,
        )

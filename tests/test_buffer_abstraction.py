"""
Hermetic tests for the streaming buffer abstraction prototype (TASKS.md #145).

Proves:
- Simulator-backed adapter wraps StreamingBuffer without changing behavior.
- Telemetry-backed observer converts real spike data (docs/verification/
  spike_page_faults_2026-07-30.json) into buffer-equivalent stats.
- Predicted throughput uses EXP-025 calibrated BWs (cpu-ram / disk-mmap).
"""
import json
from pathlib import Path

import pytest

from simulator import physics
from simulator.buffer import StreamingBuffer
from simulator.buffer_abstraction import (
    SimulatorBufferAdapter,
    TelemetryBufferObserver,
    predicted_tok_per_sec,
)
from simulator.config import SimConfig

ROOT = Path(__file__).resolve().parents[1]
SPIKE = ROOT / "docs/verification/spike_page_faults_2026-07-30.json"

# Qwen1.5-MoE-A2.7B Q2_K (EXP-004): 2.7B active @ 2.5 bpw = 0.84375 GB/token
QWEN_BYTES_PER_TOKEN_GB = 0.84375


def _make_config(policy: str = "lru") -> SimConfig:
    cfg = SimConfig()
    cfg.buffer.eviction_policy = policy
    # Use the Qwen model spec (2.7B active @ 2.5 bpw) so the adapter's
    # physics-derived bytes/token matches QWEN_BYTES_PER_TOKEN_GB.
    cfg.model.active_params = 2.7e9
    cfg.model.bits_per_weight = 2.5
    return cfg


def _make_adapter(policy: str = "lru") -> SimulatorBufferAdapter:
    cfg = _make_config(policy)
    return SimulatorBufferAdapter(StreamingBuffer(cfg), cfg)


# ---------------------------------------------------------------------------
# Simulator-backed adapter
# ---------------------------------------------------------------------------
def test_adapter_preserves_underlying_buffer_behavior():
    """Same access sequence → adapter reports the same hit rate as the raw
    StreamingBuffer (behavior unchanged by the abstraction layer)."""
    cfg = _make_config("lru")
    raw = StreamingBuffer(cfg)
    adapter = SimulatorBufferAdapter(raw, cfg)

    # Synthetic sequence: reuse a hot set of 8 experts within a 64-shard buffer
    for i in range(500):
        expert = i % 8 if i < 400 else (i % 8 + 60)  # later: cold shift
        adapter.on_access(expert)

    raw_stats = raw.get_stats()
    assert adapter.stats().hit_rate == pytest.approx(raw_stats.hit_rate)


def test_adapter_hit_rate_full_hit_when_fits():
    """Buffer holds 64 shards; only 8 unique experts → ~100% hit after warmup.
    (Exact hit rate is 192/200 = 0.96: the first 8 accesses cold-start.)"""
    adapter = _make_adapter("lru")
    for i in range(200):
        adapter.on_access(i % 8)
    view = adapter.stats()
    assert view.source == "simulator"
    assert view.hit_rate == pytest.approx(192 / 200)  # 8 cold misses only
    # 4% miss × 0.84375 GB/token = 0.03375 GB/token (8 cold misses)
    assert view.miss_bytes_per_token_gb == pytest.approx(0.03375, abs=0.002)
    # predicted must match the physics helper exactly for the same inputs
    ram = physics.DEFAULT_EFFECTIVE_BW_GBPS["cpu-ram"]
    disk = physics.DEFAULT_EFFECTIVE_BW_GBPS["disk-mmap"]
    expected = predicted_tok_per_sec(192 / 200, QWEN_BYTES_PER_TOKEN_GB, ram, disk)
    assert view.predicted_tok_per_sec == pytest.approx(expected)
    # even 4% miss at disk BW (0.38 GB/s) dominates → far below RAM ceiling
    assert view.predicted_tok_per_sec < 8.0
    assert view.predicted_tok_per_sec > 5.0


def test_adapter_no_hit_is_disk_bound():
    """~6% hit (64/1000 unique) → mostly disk-mmap → predicted ≈ disk BW path."""
    cfg = _make_config("lru")
    adapter = SimulatorBufferAdapter(StreamingBuffer(cfg), cfg)
    # 1000 unique experts cycling (buffer capacity 64) → mostly misses
    for i in range(500):
        adapter.on_access(i % 1000)
    view = adapter.stats()
    assert view.hit_rate < 0.1
    # predicted must match the physics helper exactly for the same inputs
    ram = physics.DEFAULT_EFFECTIVE_BW_GBPS["cpu-ram"]
    disk = physics.DEFAULT_EFFECTIVE_BW_GBPS["disk-mmap"]
    expected = predicted_tok_per_sec(view.hit_rate, QWEN_BYTES_PER_TOKEN_GB, ram, disk)
    assert view.predicted_tok_per_sec == pytest.approx(expected)
    assert view.predicted_tok_per_sec < 0.6  # 0.38/0.844 ≈ 0.45 tok/s disk-bound


def test_predicted_tok_per_sec_uses_calibrated_bws():
    """Helper: 50% hit → half at cpu-ram BW, half at disk-mmap BW."""
    ram = physics.DEFAULT_EFFECTIVE_BW_GBPS["cpu-ram"]
    disk = physics.DEFAULT_EFFECTIVE_BW_GBPS["disk-mmap"]
    tps = predicted_tok_per_sec(0.5, 1.0, ram, disk)
    # time = 0.5/19.18 + 0.5/0.38 = 0.0261 + 1.3158 = 1.3419 s → 0.745 tok/s
    assert tps == pytest.approx(0.745, rel=0.05)
    # monotonic: higher hit rate → faster
    assert predicted_tok_per_sec(0.9, 1.0, ram, disk) > tps


# ---------------------------------------------------------------------------
# Telemetry-backed observer (real spike data)
# ---------------------------------------------------------------------------
def _spike():
    """Load the real spike page-fault measurement (2026-07-30)."""
    return json.loads(SPIKE.read_text(encoding="utf-8"))


def test_telemetry_observer_cold_run_matches_spike():
    """Cold run faulted 174.72 MB/token → miss ≈ 20.7% of 0.844 GB/token,
    predicted tok/s must stay sane (< 1.5, disk-heavy) and stall > compute."""
    d = _spike()["runs"][0]  # run1-cold
    obs = TelemetryBufferObserver(QWEN_BYTES_PER_TOKEN_GB)
    view = obs.observe(d, n_tokens=d["tokens"])

    assert view.source == "telemetry"
    # 174.72 MB / 1000 = 0.1747 GB of 0.84375 GB
    assert view.miss_bytes_per_token_gb == pytest.approx(0.17472, rel=0.01)
    # hit rate = 1 - 0.1747/0.84375 ≈ 0.793
    assert view.hit_rate == pytest.approx(1 - 0.17472 / QWEN_BYTES_PER_TOKEN_GB, rel=0.01)
    # disk-mmap stall dominates a cold run
    assert view.stall_ms_per_token > view.compute_ms_per_token
    # predicted: treating all faults as disk traffic is a *conservative lower
    # bound* — real cold run measured 10.32 tok/s (most faults were page-cache
    # hits, not disk reads). The observer's number must stay below it.
    assert view.predicted_tok_per_sec < 10.32
    assert view.predicted_tok_per_sec > 1.0


def test_telemetry_observer_warm_run_is_ram_bound():
    """Warm run faulted only 0.55 MB/token → ~99.9% hit → near cpu-ram ceiling."""
    d = _spike()["runs"][1]  # run2-warm
    obs = TelemetryBufferObserver(QWEN_BYTES_PER_TOKEN_GB)
    view = obs.observe(d, n_tokens=d["tokens"])

    assert view.hit_rate > 0.99
    # 21.88 tok/s measured; predicted (ram-bound) should be ≥ measured
    assert view.predicted_tok_per_sec > d["tok_s"]
    assert view.predicted_tok_per_sec <= physics.DEFAULT_EFFECTIVE_BW_GBPS["cpu-ram"] / QWEN_BYTES_PER_TOKEN_GB * 1.01


def test_telemetry_observer_vs_measured_throughput():
    """Honesty check: predicted tok/s from OS signals should bracket the
    measured tok/s from the same run (cold: disk-heavy → predicted below
    measured; warm: RAM-heavy → predicted at/above measured)."""
    for run in _spike()["runs"]:
        obs = TelemetryBufferObserver(QWEN_BYTES_PER_TOKEN_GB)
        view = obs.observe(run, n_tokens=run["tokens"])
        if run["label"].startswith("run1"):  # cold
            assert view.predicted_tok_per_sec < run["tok_s"]
        else:  # warm
            assert view.predicted_tok_per_sec >= run["tok_s"]


def test_telemetry_observer_generation_paging_keys():
    """Supports the /v1/stats generation.paging key shapes too."""
    obs = TelemetryBufferObserver(QWEN_BYTES_PER_TOKEN_GB)
    view = obs.observe({"disk_mb_per_token": 41.559}, n_tokens=100)
    assert view.miss_bytes_per_token_gb == pytest.approx(0.041559, rel=0.01)

    view2 = obs.observe({"fault_mb_per_token": 41.559}, n_tokens=100)
    assert view2.miss_bytes_per_token_gb == pytest.approx(0.041559, rel=0.01)

    # totals-based fallback: 725171 faults × 4 KB / 17 tokens
    view3 = obs.observe({"faults": 725171}, n_tokens=17)
    assert view3.miss_bytes_per_token_gb == pytest.approx(725171 * 4 / 1024 / 17 / 1000, rel=0.01)


def test_telemetry_observer_uses_calibrated_bw():
    """The observer must report the EXP-025 calibrated BWs it used."""
    obs = TelemetryBufferObserver(QWEN_BYTES_PER_TOKEN_GB)
    view = obs.observe({"disk_mb_per_token": 41.559}, n_tokens=100)
    assert view.ram_bw_gbps == pytest.approx(physics.DEFAULT_EFFECTIVE_BW_GBPS["cpu-ram"])
    assert view.disk_bw_gbps == pytest.approx(physics.DEFAULT_EFFECTIVE_BW_GBPS["disk-mmap"])

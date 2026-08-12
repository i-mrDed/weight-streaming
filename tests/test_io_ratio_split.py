"""
Hermetic tests for the compute-vs-I/O ratio split (TASKS.md #151, Phase 3b).

The split uses EXP-025 calibrated BWs (cpu-ram 19.18 GB/s hit path,
disk-mmap 0.38 GB/s miss path) through the EXP-026 buffer observer, so the
resulting compute/stall numbers are derived from physics, not fabricated.
"""
import pytest

from simulator import physics
from simulator.buffer_abstraction import TelemetryBufferObserver, predicted_tok_per_sec

QWEN_BYTES_PER_TOKEN_GB = 0.84375


@pytest.fixture
def obs():
    return TelemetryBufferObserver(QWEN_BYTES_PER_TOKEN_GB)


# ---------------------------------------------------------------------------
# The split itself
# ---------------------------------------------------------------------------
def test_warm_low_faults_is_compute_dominated(obs):
    """1.28 MB/token faulted (measured warm run, /v1/stats) → >99% hit,
    compute time ≈ 44 ms/token (EXP-025: 0.844 GB / 19.18 GB/s), I/O stall
    small → ratio > 10:1."""
    view = obs.observe({"fault_mb_per_token": 1.281}, n_tokens=100)
    assert view.hit_rate > 0.99
    # compute = 0.84375 GB × 0.9985 / 19.18 GB/s ≈ 43.9 ms
    assert view.compute_ms_per_token == pytest.approx(43.9, rel=0.05)
    # stall = 0.001281 GB / 0.38 GB/s ≈ 3.4 ms
    assert view.stall_ms_per_token == pytest.approx(3.37, rel=0.05)
    ratio = view.compute_ms_per_token / view.stall_ms_per_token
    assert ratio > 10
    # predicted throughput ≈ measured warm 22-23 tok/s
    assert 15 < view.predicted_tok_per_sec < 25


def test_cold_heavy_faults_is_io_dominated(obs):
    """174.7 MB/token faulted (spike run1-cold) → ~79% hit → I/O stall
    dominates compute → ratio < 0.5 (I/O-bound)."""
    view = obs.observe({"fault_mb_per_token": 174.72}, n_tokens=17)
    assert view.hit_rate == pytest.approx(1 - 0.17472 / QWEN_BYTES_PER_TOKEN_GB, rel=0.01)
    assert view.stall_ms_per_token > view.compute_ms_per_token
    assert view.compute_ms_per_token / view.stall_ms_per_token < 0.5


def test_zero_faults_is_pure_compute(obs):
    """Perfect hit → stall = 0, throughput = cpu-ram BW / bytes-per-token
    (= 22.73 tok/s — the EXP-004/025 RAM ceiling)."""
    view = obs.observe({"fault_mb_per_token": 0.0}, n_tokens=100)
    assert view.hit_rate == pytest.approx(1.0)
    assert view.stall_ms_per_token == pytest.approx(0.0, abs=1e-9)
    assert view.predicted_tok_per_sec == pytest.approx(22.73, rel=0.02)


# ---------------------------------------------------------------------------
# Ratio helper invariant
# ---------------------------------------------------------------------------
def test_ratio_breaks_even_at_50_percent_miss():
    """At 50% miss, the two terms should be comparable: half at cpu-ram BW,
    half at disk-mmap BW → stall ≈ compute × (ram/disk) / ... — sanity: both
    terms non-zero and predicted below RAM ceiling."""
    ram = physics.DEFAULT_EFFECTIVE_BW_GBPS["cpu-ram"]
    disk = physics.DEFAULT_EFFECTIVE_BW_GBPS["disk-mmap"]
    tps = predicted_tok_per_sec(0.5, 1.0, ram, disk)
    # time = 0.5/19.18 + 0.5/0.38 ≈ 1.34 s → 0.745 tok/s
    assert tps == pytest.approx(0.745, rel=0.05)
    assert tps < ram / 1.0  # far below pure-RAM


def test_monotonic_hit_rate_improves_ratio():
    """More hits → lower I/O fraction → higher compute/(compute+io)."""
    obs = TelemetryBufferObserver(QWEN_BYTES_PER_TOKEN_GB)
    lo = obs.observe({"fault_mb_per_token": 100.0}, n_tokens=100)
    hi = obs.observe({"fault_mb_per_token": 1.0}, n_tokens=100)
    lo_frac = lo.compute_ms_per_token / (lo.compute_ms_per_token + lo.stall_ms_per_token)
    hi_frac = hi.compute_ms_per_token / (hi.compute_ms_per_token + hi.stall_ms_per_token)
    assert hi_frac > lo_frac


# ---------------------------------------------------------------------------
# K3 projection (the whole point of Phase 3b: does K3 flip to I/O-bound?)
# ---------------------------------------------------------------------------
def test_k3_projection_io_bound_at_real_miss_rates():
    """K3 (50B active, 15.6 GB/token): even modest disk faults push it to
    I/O-bound. At 5% miss (0.78 GB/token from disk) stall ≈ 2 s ≫ compute
    815 ms — confirming EXP-004's I/O-bound prediction for >RAM models."""
    k3_bpt = physics.bytes_per_token_gb(50e9, 2.5)  # 15.625 GB
    obs = TelemetryBufferObserver(k3_bpt)
    # 5% miss = 0.78 GB/token from disk
    miss_mb = k3_bpt * 0.05 * 1000
    view = obs.observe({"fault_mb_per_token": miss_mb}, n_tokens=100)
    assert view.hit_rate == pytest.approx(0.95)
    # compute = 15.625 × 0.95 / 19.18 ≈ 774 ms; stall = 0.78 / 0.38 ≈ 2056 ms
    assert view.stall_ms_per_token > view.compute_ms_per_token
    ratio = view.compute_ms_per_token / view.stall_ms_per_token
    assert ratio < 0.4
    # predicted throughput collapses below 0.4 tok/s
    assert view.predicted_tok_per_sec < 0.4

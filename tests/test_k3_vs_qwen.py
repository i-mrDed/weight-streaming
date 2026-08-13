"""Hermetic tests for the K3 (>RAM) vs Qwen (fits RAM) comparison (EXP-029).

Pins the physics math the K3 benchmark relies on: at a given hit rate,
per-token stall comes from the miss bytes at the calibrated disk-mmap
bandwidth, and the resulting tok/s is dominated by the I/O path even at
moderate miss rates — the reason the project's target (K3, 15.6 GB/token)
needs a very high hit rate to approach the compute ceiling.
"""

from __future__ import annotations

import pytest

from simulator.buffer_abstraction import predicted_tok_per_sec
import simulator.physics as physics
from weight_stream.eval.metrics import latency_percentiles, evaluate_run

K3 = physics.K3
RAM_BW = physics.DEFAULT_EFFECTIVE_BW_GBPS["cpu-ram"]
DISK_BW = physics.DEFAULT_EFFECTIVE_BW_GBPS["disk-mmap"]
K3_BYTES_GB = K3.bytes_per_token_gb          # 15.625 GB/token
K3_COMPUTE_MS = physics.ms_per_token(RAM_BW, K3_BYTES_GB)  # ~815 ms


class TestK3Physics:
    def test_k3_active_set_is_over_ram(self) -> None:
        # 15.6 GB/token — the whole point of the project.
        assert K3_BYTES_GB == pytest.approx(15.625, rel=0.01)
        assert K3_BYTES_GB > 8.0  # does not fit a typical 8 GB consumer RAM

    def test_compute_ms_matches_exp004(self) -> None:
        # EXP-004 estimated 815 ms compute/token for K3; EXP-025 calibrated
        # physics reproduces it from Qwen's measured bandwidth.
        assert K3_COMPUTE_MS == pytest.approx(815, rel=0.01)

    def test_perfect_hit_rate_is_compute_bound(self) -> None:
        pred = predicted_tok_per_sec(1.0, K3_BYTES_GB, RAM_BW, DISK_BW)
        assert pred == pytest.approx(1000.0 / K3_COMPUTE_MS, rel=0.01)

    def test_moderate_miss_is_io_bound(self) -> None:
        # 50% hit: half of 15.6 GB streams at 0.38 GB/s -> ~20 s/token.
        pred = predicted_tok_per_sec(0.5, K3_BYTES_GB, RAM_BW, DISK_BW)
        stall_s = 0.5 * K3_BYTES_GB / DISK_BW
        assert stall_s == pytest.approx(20.5, rel=0.05)
        assert pred < 0.05  # I/O-bound, ~0.05 tok/s

    def test_high_hit_rate_approaches_compute_ceiling(self) -> None:
        # 99.9% hit (4 GB buffer in EXP-029): stall < 1% of compute time.
        pred = predicted_tok_per_sec(0.999, K3_BYTES_GB, RAM_BW, DISK_BW)
        assert pred == pytest.approx(1000.0 / K3_COMPUTE_MS, rel=0.05)

    def test_miss_bytes_per_token_math(self) -> None:
        # EXP-027 anchor: 5% miss -> ~2.1 s stall (matches its 2056 ms).
        stall_ms = 0.05 * K3_BYTES_GB / DISK_BW * 1000.0
        assert stall_ms == pytest.approx(2056, rel=0.05)


class TestK3Metrics:
    def test_latency_distribution_has_tail(self) -> None:
        # Per-token: mostly compute-bound (fast) with occasional big stalls.
        lat = latency_percentiles([K3_COMPUTE_MS] * 90 + [21_000.0] * 10)
        assert lat["p50"] < 1000.0
        assert lat["p99"] > 10_000.0
        assert lat["max"] == 21_000.0

    def test_evaluate_run_at_50_percent_hit(self) -> None:
        rec = evaluate_run(
            tok_s=0.05,
            predicted_tok_s=0.05,
            disk_mb_per_token=0.5 * K3_BYTES_GB * 1024.0,
            bytes_per_token_mb=K3_BYTES_GB * 1024.0,
            per_token_ms=[20_000.0] * 50,
        )
        assert rec["hit_rate"] == pytest.approx(0.5, rel=0.01)
        assert rec["throughput_match"] is True

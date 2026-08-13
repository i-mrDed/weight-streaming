"""Hermetic tests for Phase 4 evaluation metrics (weight_stream/eval/metrics.py).

These exercise the pure metric definitions with known inputs — no server,
no model, no network. They pin the semantics the benchmark script relies
on: hit rate from paging telemetry, latency percentiles from per-token
timings, and throughput tolerance vs the physics prediction.
"""

from __future__ import annotations

import pytest

from weight_stream.eval.metrics import (
    evaluate_run,
    hit_rate,
    latency_percentiles,
    throughput_error,
    throughput_matches,
)

# Qwen1.5-MoE-A2.7B Q2_K: 2.7B active x 2.5 bpw = 0.844 GB = 864 MB/token.
QWEN_BYTES_MB = 864.0
# EXP-025 calibrated cpu-ram bandwidth / physics prediction.
PREDICTED_TPS = 22.73


# ── hit rate ─────────────────────────────────────────────────────────

class TestHitRate:
    def test_no_disk_demand_is_100_percent(self) -> None:
        assert hit_rate(0.0, QWEN_BYTES_MB) == 1.0

    def test_none_telemetry_treated_as_zero_disk(self) -> None:
        assert hit_rate(None, QWEN_BYTES_MB) == 1.0

    def test_disk_demand_lowers_hit_rate(self) -> None:
        # 200 MB faulted per token out of 864 MB -> 76.9% resident.
        assert hit_rate(200.0, QWEN_BYTES_MB) == pytest.approx(1 - 200 / 864)

    def test_disk_demand_above_active_set_clamps_to_zero(self) -> None:
        assert hit_rate(2000.0, QWEN_BYTES_MB) == 0.0

    def test_zero_bytes_raises(self) -> None:
        with pytest.raises(ValueError):
            hit_rate(1.0, 0.0)


# ── latency distribution ─────────────────────────────────────────────

class TestLatencyPercentiles:
    def test_percentiles_on_known_sample(self) -> None:
        # 100 tokens, 40..139 ms; p50=89, p90=129, p99=138 (nearest-rank).
        vals = list(range(40, 140))
        d = latency_percentiles(vals)
        assert d["p50"] == 89.0
        assert d["p90"] == 129.0
        assert d["p99"] == 138.0
        assert d["mean"] == pytest.approx(89.5)
        assert d["max"] == 139.0

    def test_single_token(self) -> None:
        d = latency_percentiles([123.0])
        assert all(d[k] == 123.0 for k in ("p50", "p90", "p99", "mean", "max"))

    def test_empty_raises(self) -> None:
        with pytest.raises(ValueError):
            latency_percentiles([])


# ── throughput vs physics ────────────────────────────────────────────

class TestThroughput:
    def test_error_formula(self) -> None:
        assert throughput_error(20.76, PREDICTED_TPS) == pytest.approx(
            (20.76 - PREDICTED_TPS) / PREDICTED_TPS)

    def test_exact_match_zero_error(self) -> None:
        assert throughput_error(PREDICTED_TPS, PREDICTED_TPS) == 0.0

    def test_missing_measured_raises(self) -> None:
        with pytest.raises(ValueError):
            throughput_error(None, PREDICTED_TPS)

    def test_zero_prediction_raises(self) -> None:
        with pytest.raises(ValueError):
            throughput_error(10.0, 0.0)

    def test_validation_within_tolerance(self) -> None:
        # EXP-025 real validation: 20.76 vs 22.73 = -8.7% -> within +-15%.
        assert throughput_matches(20.76, PREDICTED_TPS) is True

    def test_outside_tolerance_fails(self) -> None:
        assert throughput_matches(PREDICTED_TPS * 0.5, PREDICTED_TPS) is False


# ── combined run record ──────────────────────────────────────────────

class TestEvaluateRun:
    def test_full_record(self) -> None:
        rec = evaluate_run(
            tok_s=20.76,
            predicted_tok_s=PREDICTED_TPS,
            disk_mb_per_token=0.0,
            bytes_per_token_mb=QWEN_BYTES_MB,
            per_token_ms=[45.0, 46.0, 44.0, 50.0, 43.0],
        )
        assert rec["throughput_match"] is True
        assert rec["hit_rate"] == 1.0
        assert rec["latency"]["p50"] == 45.0
        assert rec["throughput_error"] == pytest.approx(
            (20.76 - PREDICTED_TPS) / PREDICTED_TPS)

    def test_missing_tok_s_raises(self) -> None:
        with pytest.raises(ValueError):
            evaluate_run(None, PREDICTED_TPS, 0.0, QWEN_BYTES_MB, [10.0])

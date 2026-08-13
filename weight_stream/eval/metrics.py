"""Phase 4 evaluation metrics — pure, hermetic-testable definitions.

The project's ground rule is honest telemetry: every number comes from a
real measurement, never a fabricated value. This module defines the THREE
Phase 4 metrics (TASKS.md "Define evaluation metrics") as pure functions
over the telemetry the server already ships (generation.paging from
/v1/stats + per-token timings captured from the SSE stream), so the
definitions are testable offline and the benchmark script only collects
raw data.

Metrics
-------
1. **Hit rate** — fraction of per-token weight bytes served from RAM
   (page-cache hit) rather than faulted from disk::

       hit_rate = 1 - disk_bytes_per_token / bytes_per_token

   ``disk_bytes_per_token`` comes from ``generation.paging.disk_mb_per_token``
   (hard-fault demand); ``bytes_per_token`` is the physics value
   ``active_params x bits_per_weight / 8`` (EXP-025). 100% = model fully
   resident (warm Qwen); low = the honest I/O-bound case (K3 > RAM).

2. **Latency distribution** — per-token generation latency (ms), captured
   from the SSE stream (one chunk per token). Reported as percentiles
   p50 / p90 / p99 plus mean and max, so "average 45 ms" cannot hide a
   long-tail stall (a disk fault on one token).

3. **Throughput** — tokens/sec from /v1/stats, compared against the
   physics prediction (EXP-025 calibrated bandwidth):
   ``error = (measured - predicted) / predicted``. Acceptance: within
   +/-15% (the tolerance EXP-025 validated on real HW).

All functions accept plain numbers / lists so they can be unit-tested
without a server.
"""

from __future__ import annotations

import math
from typing import Sequence

# Acceptance threshold carried over from EXP-025's real-HW validation
# (Qwen 20.76 tok/s measured vs 22.73 predicted = -8.7%): a measurement
# within +/-15% of the physics prediction counts as "matches the model".
THROUGHPUT_TOLERANCE = 0.15

# Percentiles reported for the latency distribution.
LATENCY_PERCENTILES = (50, 90, 99)


# ── hit rate ──────────────────────────────────────────────────────────

def hit_rate(disk_mb_per_token: float | None,
             bytes_per_token_mb: float) -> float:
    """Fraction of per-token bytes served from RAM (1 = fully resident).

    ``disk_mb_per_token`` is the measured hard-fault demand (None when the
    telemetry recorded no disk reads — treat as 0). ``bytes_per_token_mb``
    is the physics active-set size (e.g. Qwen 0.844 GB = 844 MB/token).
    """
    if bytes_per_token_mb <= 0:
        raise ValueError("bytes_per_token_mb must be > 0")
    disk = disk_mb_per_token or 0.0
    if disk <= 0:
        return 1.0
    return max(0.0, 1.0 - disk / bytes_per_token_mb)


# ── latency distribution ─────────────────────────────────────────────

def _percentile(sorted_vals: Sequence[float], pct: float) -> float:
    """Nearest-rank percentile on an already-sorted ascending list.

    Standard nearest-rank definition: the value at the ceil(pct/100 * N)
    position (1-indexed), i.e. the smallest value that is >= pct of the
    sample. E.g. p50 of 100 values 40..139 is 89.
    """
    if not sorted_vals:
        raise ValueError("empty latency sample")
    n = len(sorted_vals)
    rank = max(1, min(n, math.ceil((pct / 100.0) * n)))
    return sorted_vals[rank - 1]


def latency_percentiles(per_token_ms: Sequence[float]) -> dict[str, float]:
    """Compute p50/p90/p99 + mean/max from per-token latencies (ms).

    Returns keys: p50, p90, p99, mean, max. Raises ValueError on an empty
    sample (never silently report a latency from zero tokens).
    """
    vals = [float(v) for v in per_token_ms]
    if not vals:
        raise ValueError("empty latency sample")
    vals.sort()
    out: dict[str, float] = {
        f"p{p}": _percentile(vals, p) for p in LATENCY_PERCENTILES
    }
    out["mean"] = sum(vals) / len(vals)
    out["max"] = vals[-1]
    return out


# ── throughput vs physics ────────────────────────────────────────────

def throughput_error(measured_tok_s: float | None,
                     predicted_tok_s: float) -> float:
    """Relative error of measured vs physics-predicted tok/s.

    ``error = (measured - predicted) / predicted``. Positive = faster than
    predicted. Raises ValueError if predicted is 0 or measured is missing.
    """
    if measured_tok_s is None:
        raise ValueError("measured tok/s missing")
    if predicted_tok_s <= 0:
        raise ValueError("predicted tok/s must be > 0")
    return (measured_tok_s - predicted_tok_s) / predicted_tok_s


def throughput_matches(measured_tok_s: float | None,
                       predicted_tok_s: float,
                       tolerance: float = THROUGHPUT_TOLERANCE) -> bool:
    """True if measured tok/s is within +/-tolerance of the prediction."""
    return abs(throughput_error(measured_tok_s, predicted_tok_s)) <= tolerance


# ── combined evaluation record ───────────────────────────────────────

def evaluate_run(
    tok_s: float | None,
    predicted_tok_s: float,
    disk_mb_per_token: float | None,
    bytes_per_token_mb: float,
    per_token_ms: Sequence[float],
) -> dict[str, object]:
    """One run's full metric record: hit rate + latency + throughput.

    Returns a dict with keys ``hit_rate``, ``latency`` (percentiles dict),
    ``tok_s``, ``throughput_error`` and ``throughput_match``. Raises
    ValueError when a component cannot be computed (no tokens measured).
    """
    return {
        "tok_s": tok_s,
        "predicted_tok_s": predicted_tok_s,
        "throughput_error": throughput_error(tok_s, predicted_tok_s),
        "throughput_match": throughput_matches(tok_s, predicted_tok_s),
        "hit_rate": hit_rate(disk_mb_per_token, bytes_per_token_mb),
        "latency": latency_percentiles(per_token_ms),
    }

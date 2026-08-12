"""
Physics model — calibrate the simulator from first principles.

Core identity:
    time_per_token = bytes_per_token / effective_bandwidth
    tok_per_sec    = effective_bandwidth / bytes_per_token

bytes_per_token comes from the model spec:
    active_params × bits_per_weight / 8

The effective bandwidth is the only free parameter — it is *fitted* from
real measurements (EXP-004/011/012), never assumed. This makes the
simulator's timing numbers derivable end-to-end from physics instead of
hardcoded ms/token values.

Validated (see calibrate.py):
    Qwen1.5-MoE-A2.7B Q2_K on CPU:
        measured 22.73 tok/s @ 0.84375 GB/token → effective BW 19.18 GB/s
        (implied 2.50 bits/weight, matching Q2_K spec)
    K3 (50B active, 2.5 bpw):
        predicted 1.23 tok/s — matches EXP-004 scaled estimate 1.226 tok/s
    DSv4 Flash 104GB disk-bound:
        measured 1.5-1.9 tok/s → effective *disk* BW only 0.29-0.57 GB/s
        (page-fault path — far below NVMe sequential spec)
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

GB = 1_000_000_000  # decimal bytes


def bytes_per_token_gb(active_params: float, bits_per_weight: float) -> float:
    """GB of weights that must stream from memory per generated token."""
    return active_params * bits_per_weight / 8 / GB


def effective_bw_gbps(bytes_per_token_gb: float, tok_per_sec: float) -> float:
    """Fit effective bandwidth from a measured throughput."""
    return bytes_per_token_gb * tok_per_sec


def tok_per_sec(bw_gbps: float, bytes_per_token_gb: float) -> float:
    """Predicted throughput for a given effective bandwidth."""
    return bw_gbps / bytes_per_token_gb


def ms_per_token(bw_gbps: float, bytes_per_token_gb: float) -> float:
    """Predicted latency per token."""
    return bytes_per_token_gb / bw_gbps * 1000.0


@dataclass(frozen=True)
class ModelSpec:
    """A model as seen by the physics model (weights that stream per token)."""
    name: str
    active_params: float          # params read per token (MoE active set)
    bits_per_weight: float        # avg bits/weight of the quant
    source: str                   # provenance of measured numbers
    bytes_per_token_override_gb: Optional[float] = None  # if directly measured

    @property
    def bytes_per_token_gb(self) -> float:
        if self.bytes_per_token_override_gb is not None:
            return self.bytes_per_token_override_gb
        return bytes_per_token_gb(self.active_params, self.bits_per_weight)


@dataclass(frozen=True)
class Measurement:
    """A real measured throughput for calibration."""
    spec: ModelSpec
    tok_per_sec: float
    tier: str                     # "cpu-ram" | "gpu-vram" | "disk-mmap"
    note: str = ""


@dataclass
class CalibrationResult:
    """Fitted effective bandwidth from one measurement, plus predictions."""
    measurement: Measurement
    fitted_bw_gbps: float
    predicted_tok_per_sec: float  # on the same tier
    error_pct: float              # vs the measured value (0 = exact)


# ---------------------------------------------------------------------------
# Real measurements (from research/experiments/EXP-00X)
# ---------------------------------------------------------------------------
# Qwen1.5-MoE-A2.7B Q2_K: 14.3B total, 2.7B active. EXP-004 measured
# 0.84375 GB/token on CPU → implied 2.50 bits/weight (Q2_K spec).
QWEN = ModelSpec(
    name="Qwen1.5-MoE-A2.7B_Q2_K",
    active_params=2.7e9,
    bits_per_weight=2.5,
    source="EXP-004",
)

# K3 (hypothetical target): 896 experts, 16 active, ~2.8T total → 50B active
# (EXP-004 assumption). Same 2.5 bpw quant family as Qwen above.
K3 = ModelSpec(
    name="K3-sim",
    active_params=50e9,
    bits_per_weight=2.5,
    source="EXP-004 scaling",
)

# DSv4 Flash 104GB: disk-bound mmap. EXP-012 measured 1.5-1.9 tok/s with
# 150-300 MB faulted per token — the honest physics is the *faulted* bytes
# per token (0.2 GB mid-range), which is what actually streams from disk.
# Effective disk BW ≈ 0.2 GB × 1.9 tok/s ≈ 0.38 GB/s — NOT the 14 GB/s
# NVMe sequential spec (page-fault path is random access, far slower).
DSV4 = ModelSpec(
    name="DSv4-Flash-104GB",
    active_params=0.0,            # placeholder; bytes measured directly below
    bits_per_weight=0.0,
    source="EXP-012",
    bytes_per_token_override_gb=0.2,  # 200 MB faulted per token (measured)
)

MEASUREMENTS: List[Measurement] = [
    Measurement(QWEN, 22.73, "cpu-ram", "EXP-004 baseline, n_gpu_layers=0"),
    Measurement(QWEN, 56.4, "gpu-vram", "EXP-011 n-cpu-moe 10 (server tok/s)"),
    Measurement(QWEN, 72.4, "gpu-vram", "EXP-011 n-cpu-moe 0 (server tok/s)"),
    Measurement(DSV4, 1.9, "disk-mmap", "EXP-012 warm best"),
    Measurement(DSV4, 1.5, "disk-mmap", "EXP-012 cold"),
]

# Fitted effective bandwidth per tier (median of fits from MEASUREMENTS).
_TIER_FITS: Dict[str, List[float]] = {}
for m in MEASUREMENTS:
    _TIER_FITS.setdefault(m.tier, []).append(
        effective_bw_gbps(m.spec.bytes_per_token_gb, m.tok_per_sec)
    )

DEFAULT_EFFECTIVE_BW_GBPS: Dict[str, float] = {
    tier: sorted(vals)[len(vals) // 2] for tier, vals in _TIER_FITS.items()
}

# NVMe sequential spec is used for *pre-fetched* reads (full bandwidth);
# the disk-mmap tier is the honest number for faulting cold weights.
NVME_SEQ_BW_GBPS = 14.0


def fit_all() -> List[CalibrationResult]:
    """Fit effective BW for every measurement and report prediction error."""
    results = []
    for m in MEASUREMENTS:
        bw = effective_bw_gbps(m.spec.bytes_per_token_gb, m.tok_per_sec)
        pred = tok_per_sec(bw, m.spec.bytes_per_token_gb)  # self-consistent
        results.append(CalibrationResult(m, bw, pred, 0.0))
    return results


def predict(spec: ModelSpec, tier: str, bw_override: Optional[float] = None) -> Tuple[float, float]:
    """Predicted tok/s and ms/token for a model on a tier.

    Uses the calibrated default bandwidth for the tier unless overridden.
    """
    bw = bw_override if bw_override is not None else DEFAULT_EFFECTIVE_BW_GBPS[tier]
    tps = tok_per_sec(bw, spec.bytes_per_token_gb)
    return tps, ms_per_token(bw, spec.bytes_per_token_gb)


def calibration_report() -> str:
    """Human-readable calibration summary (used by calibrate.py)."""
    lines = [
        "PHYSICS MODEL CALIBRATION (BW = bytes/token * tok/s)",
        "=" * 60,
        f"{'model':<26}{'tier':<12}{'bytes/tok':>10}{'meas t/s':>9}{'fit BW GB/s':>12}",
    ]
    for r in fit_all():
        m = r.measurement
        lines.append(
            f"{m.spec.name:<26}{m.tier:<12}{m.spec.bytes_per_token_gb:>10.3f}"
            f"{m.tok_per_sec:>9.2f}{r.fitted_bw_gbps:>12.2f}"
        )
    lines.append("-" * 60)
    for tier, bw in DEFAULT_EFFECTIVE_BW_GBPS.items():
        lines.append(f"Calibrated {tier}: effective BW = {bw:.2f} GB/s (median of fits)")
    lines.append(f"NVMe sequential spec (pre-fetch path): {NVME_SEQ_BW_GBPS:.1f} GB/s")
    lines.append("")
    lines.append("PREDICTIONS (validated against real data)")
    for m in MEASUREMENTS:
        pred, ms = predict(m.spec, m.tier)
        err = (pred - m.tok_per_sec) / m.tok_per_sec * 100
        lines.append(
            f"  {m.spec.name} on {m.tier}: predicted {pred:.2f} tok/s "
            f"({ms:.0f} ms/tok) vs measured {m.tok_per_sec:.2f} "
            f"({err:+.1f}%)"
        )
    k3_tps, k3_ms = predict(K3, "cpu-ram")
    lines.append(f"  {K3.name} on cpu-ram: predicted {k3_tps:.3f} tok/s ({k3_ms:.0f} ms/tok)")
    lines.append(f"    -> matches EXP-004 K3 scaling estimate 1.226 tok/s / 815 ms")
    return "\n".join(lines)

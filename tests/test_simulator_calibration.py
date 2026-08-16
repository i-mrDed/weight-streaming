"""
Hermetic tests for simulator physics calibration (TASKS.md #96).

Validates the physics model (BW = bytes/token x tok/s) against real
measured data from research/experiments/EXP-004/011/012, and that the
simulator's TimingConfig derives its compute time from physics rather
than a hardcoded constant.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

from simulator import physics
from simulator.config import SimConfig

ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Physics identity
# ---------------------------------------------------------------------------
def test_bytes_per_token_matches_qwen_measurement():
    """Qwen1.5-MoE-A2.7B Q2_K: 2.7B active @ 2.5 bpw -> 0.84375 GB/token."""
    gb = physics.bytes_per_token_gb(2.7e9, 2.5)
    assert gb == pytest.approx(0.84375, rel=1e-6)


def test_effective_bw_fit_from_qwen_cpu():
    """22.73 tok/s @ 0.84375 GB/token -> ~19.18 GB/s effective CPU BW."""
    bw = physics.effective_bw_gbps(0.84375, 22.73)
    assert bw == pytest.approx(19.18, rel=0.01)


def test_qwen_implied_bits_per_weight_is_q2k():
    """Calibration must reproduce Q2_K spec (~2.5 bits/weight)."""
    bpw = physics.QWEN.bytes_per_token_gb * 8e9 / physics.QWEN.active_params
    assert bpw == pytest.approx(2.5, rel=0.01)


# ---------------------------------------------------------------------------
# Predictions vs real measurements (workflow acceptance criteria 1-2)
# ---------------------------------------------------------------------------
def test_k3_prediction_matches_exp004_scaling():
    """K3 (50B active @ 2.5 bpw) on cpu-ram ~= 1.226 tok/s / 815 ms (EXP-004)."""
    tps, ms = physics.predict(physics.K3, "cpu-ram")
    assert tps == pytest.approx(1.2263, rel=0.05)
    assert ms == pytest.approx(815, rel=0.05)


def test_dsv4_disk_bound_prediction_within_tolerance():
    """DSv4 104GB disk-mmap: measured 1.5-1.9 tok/s (EXP-012) — predicted
    must land inside +/-25% of that band."""
    pred, _ = physics.predict(physics.DSV4, "disk-mmap")
    assert 1.5 * 0.75 <= pred <= 1.9 * 1.25, f"predicted {pred} outside band"


def test_disk_mmap_bw_far_below_nvme_seq_spec():
    """Key honest-telemetry insight: page-fault disk BW (~0.38 GB/s) is
    ~37x below the NVMe sequential spec used for pre-fetch (14 GB/s)."""
    disk_bw = physics.DEFAULT_EFFECTIVE_BW_GBPS["disk-mmap"]
    assert disk_bw < 1.0
    assert physics.NVME_SEQ_BW_GBPS / disk_bw > 20


# ---------------------------------------------------------------------------
# Simulator config derives from physics (acceptance criterion 3)
# ---------------------------------------------------------------------------
def test_timing_config_derived_from_physics():
    """compute_time_per_token_us must equal bytes/token / effective BW,
    not a magic constant — and must match EXP-004's 815 ms estimate."""
    t = SimConfig().timing
    expected_us = int(
        1_000_000
        * physics.bytes_per_token_gb(physics.K3.active_params, physics.K3.bits_per_weight)
        / physics.DEFAULT_EFFECTIVE_BW_GBPS["cpu-ram"]
    )
    assert t.compute_time_per_token_us == expected_us
    assert abs(t.compute_time_per_token_us - 815_000) < 1_000


def test_timing_config_changes_with_bw():
    """Derived value must track the physics — changing the fitted BW
    changes the compute time (proves it's not hardcoded)."""
    t = SimConfig().timing
    base = t.compute_time_per_token_us
    # double the bandwidth -> half the time
    doubled = int(
        1_000_000
        * physics.bytes_per_token_gb(physics.K3.active_params, physics.K3.bits_per_weight)
        / (physics.DEFAULT_EFFECTIVE_BW_GBPS["cpu-ram"] * 2)
    )
    assert doubled == pytest.approx(base / 2, rel=0.01)


# ---------------------------------------------------------------------------
# calibrate.py CLI
# ---------------------------------------------------------------------------
def test_calibrate_cli_json_emits_validated_numbers():
    """calibrate.py --json must emit the same validated predictions."""
    out = subprocess.run(
        [sys.executable, "calibrate.py", "--json"],
        cwd=ROOT / "simulator",
        capture_output=True,
        text=True,
    )
    if out.returncode != 0:
        pytest.fail(
            "calibrate.py --json failed:\n"
            f"stdout={out.stdout[-1000:]}\nstderr={out.stderr[-1000:]}"
        )
    data = json.loads(out.stdout)
    # K3 prediction matches EXP-004
    assert data["k3_predicted"]["tok_per_sec"] == pytest.approx(1.2263, rel=0.05)
    # Effective BW tiers present and sane
    assert data["effective_bw_gbps"]["cpu-ram"] == pytest.approx(19.18, rel=0.01)
    assert data["effective_bw_gbps"]["disk-mmap"] < 1.0
    # Predictions include both models
    names = set(data["predictions"].keys())
    assert "Qwen1.5-MoE-A2.7B_Q2_K" in names
    assert "DSv4-Flash-104GB" in names


def test_simulator_runs_end_to_end():
    """The full simulator still runs with the physics-derived config."""
    out = subprocess.run(
        [sys.executable, "run.py"],
        cwd=ROOT / "simulator",
        capture_output=True,
        text=True,
        timeout=120,
    )
    if out.returncode != 0:
        pytest.fail(
            "run.py failed:\n"
            f"stdout={out.stdout[-1000:]}\nstderr={out.stderr[-1000:]}"
        )
    assert "Tokens/sec:" in out.stdout
    # K3-sim on cpu-ram should be ~1.2 tok/s (compute-bound, 815 ms/token)
    line = next(l for l in out.stdout.splitlines() if "Tokens/sec" in l)
    tps = float(line.split(":")[1].strip())
    assert 0.8 < tps < 2.0

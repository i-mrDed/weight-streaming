#!/usr/bin/env python3
"""
Calibrate simulator timing from physics (BW = bytes/token × tok/s).

Usage:
    python calibrate.py            # print calibration report
    python calibrate.py --json     # print as JSON (for tests/scripts)

Validated against real data in research/experiments/EXP-004/011/012.
See simulator/physics.py for the model.
"""
import argparse
import json
import os
import sys

# Add parent to path for direct execution (same pattern as run.py)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from simulator.physics import (
    DEFAULT_EFFECTIVE_BW_GBPS,
    K3,
    MEASUREMENTS,
    NVME_SEQ_BW_GBPS,
    calibration_report,
    fit_all,
    predict,
)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true", help="emit JSON instead of text")
    args = ap.parse_args()

    if args.json:
        preds = {}
        for m in MEASUREMENTS:
            pred, ms = predict(m.spec, m.tier)
            preds[m.spec.name] = {
                "tier": m.tier,
                "bytes_per_token_gb": m.spec.bytes_per_token_gb,
                "measured_tok_per_sec": m.tok_per_sec,
                "predicted_tok_per_sec": round(pred, 3),
                "error_pct": round((pred - m.tok_per_sec) / m.tok_per_sec * 100, 1),
            }
        k3_pred, k3_ms = predict(K3, "cpu-ram")
        print(json.dumps({
            "effective_bw_gbps": DEFAULT_EFFECTIVE_BW_GBPS,
            "nvme_seq_bw_gbps": NVME_SEQ_BW_GBPS,
            "k3_predicted": {
                "tok_per_sec": round(k3_pred, 4),
                "ms_per_token": round(k3_ms, 1),
                "exp004_estimate_tok_per_sec": 1.2263,
            },
            "predictions": preds,
        }, indent=2))
        return

    print(calibration_report())


if __name__ == "__main__":
    main()

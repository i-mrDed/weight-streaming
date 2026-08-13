"""Phase 4 metrics on the K3 (>RAM) target — the honest comparison.

Phase 4 (EXP-028) benchmarked Qwen1.5-MoE-A2.7B on real hardware and got
the compute-bound story: throughput matches physics, hit rate 1.000, no
latency tail. But Qwen FITS in RAM — the project's actual target is K3
(~2.8T params, 50B active/token = 15.6 GB/token), which does NOT fit.

This script runs the K3 simulator (the same `run_simulation` used by
EXP-001/002/003) through the Phase 4 metric definitions
(`weight_stream.eval.metrics`) so the numbers are directly comparable to
the real Qwen benchmark:

1. **Hit rate** — from the simulator's StreamingBuffer (LRU + priority
   boost) on a K3-like expert workload.
2. **Latency distribution** — per-token times from the TimingSimulator:
   compute (physics-derived 815 ms) + stall (missed bytes at disk-mmap BW
   0.38 GB/s). Reported as p50/p90/p99/mean/max, same as EXP-028.
3. **Throughput** — physics prediction at the measured hit rate:
   ``time = hit bytes / cpu-ram BW + miss bytes / disk-mmap BW``
   (the EXP-026 `predicted_tok_per_sec` formula), reported with the same
   +-15% tolerance lane as Qwen.

Usage:

    python scripts/bench_k3_sim.py [--tokens 1000] [--buffer-mb 256]
                                   [--json out.json]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from simulator.config import SimConfig  # noqa: E402
from simulator.run import run_simulation  # noqa: E402
from simulator.buffer_abstraction import predicted_tok_per_sec  # noqa: E402
import simulator.physics as physics  # noqa: E402
from weight_stream.eval.metrics import (  # noqa: E402
    evaluate_run,
    latency_percentiles,
    throughput_matches,
)

# Real Qwen benchmark from EXP-028 (the compute-bound reference).
QWEN_REF = {
    "tok_s": 22.73,
    "hit_rate": 1.000,
    "p50_ms": 41.3,
    "p90_ms": 48.6,
    "p99_ms": 69.6,
}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tokens", type=int, default=1000)
    ap.add_argument("--buffer-mb", type=int, default=256)
    ap.add_argument("--json", default="", help="Write JSON report to path")
    args = ap.parse_args()

    cfg = SimConfig()
    cfg.workload.n_tokens = args.tokens
    cfg.buffer.size_mb = args.buffer_mb

    # Run the same simulator as EXP-001/002/003 (collect per-token hits
    # so the latency distribution is honest per-token physics, not flat).
    result = run_simulation(cfg, collect_per_token=True)
    bs = result.buffer_stats
    ts = result.timing_stats
    hit_rate = bs["hit_rate"]

    # K3 physics.
    k3 = physics.K3
    bytes_per_token_mb = k3.bytes_per_token_gb * 1024.0
    ram_bw = physics.DEFAULT_EFFECTIVE_BW_GBPS["cpu-ram"]
    disk_bw = physics.DEFAULT_EFFECTIVE_BW_GBPS["disk-mmap"]
    compute_ms = physics.ms_per_token(ram_bw, k3.bytes_per_token_gb)
    predicted = predicted_tok_per_sec(hit_rate, k3.bytes_per_token_gb,
                                      ram_bw, disk_bw)

    # Per-token latency: compute (hit path) is fixed; each token's stall is
    # its miss fraction x bytes/token at the calibrated disk-mmap BW.
    # (EXP-026: stall = miss bytes / disk BW; Qwen real p50 came from the
    # same formula on real telemetry.)
    n = cfg.workload.n_tokens
    per_token_ms = []
    for pt in result.per_token:
        total = pt["hits"] + pt["misses"]
        miss_frac = pt["misses"] / total if total else 0.0
        stall = miss_frac * bytes_per_token_mb / 1024.0 / disk_bw * 1000.0
        per_token_ms.append(compute_ms + stall)

    rec = evaluate_run(
        tok_s=predicted,
        predicted_tok_s=predicted,   # sim predicts itself at its hit rate
        disk_mb_per_token=(1.0 - hit_rate) * bytes_per_token_mb,
        bytes_per_token_mb=bytes_per_token_mb,
        per_token_ms=per_token_ms,
    )
    lat = rec["latency"]

    print(f"K3 (>RAM) simulation — {args.tokens} tokens, "
          f"buffer {args.buffer_mb} MB")
    print(f"  active bytes/token: {bytes_per_token_mb:.0f} MB "
          f"(15.6 GB — does NOT fit RAM)")
    print(f"  hit rate (sim LRU+priority): {hit_rate:.4f}")
    print(f"  compute/token: {compute_ms:.0f} ms @ cpu-ram {ram_bw:.2f} GB/s")
    print(f"  predicted tok/s: {predicted:.4f} (at hit rate)")
    print(f"  latency: p50 {lat['p50']:.0f} / p90 {lat['p90']:.0f} / "
          f"p99 {lat['p99']:.0f} / max {lat['max']:.0f} ms")
    print(f"  throughput_match(self): {rec['throughput_match']}")
    print()

    print("vs Qwen real (EXP-028, fits RAM):")
    print(f"  {'metric':<24}{'Qwen real':>12}{'K3 sim':>12}")
    print(f"  {'tok/s':<24}{QWEN_REF['tok_s']:>12.2f}{predicted:>12.2f}")
    print(f"  {'hit rate':<24}{QWEN_REF['hit_rate']:>12.3f}{hit_rate:>12.3f}")
    print(f"  {'p50 (ms)':<24}{QWEN_REF['p50_ms']:>12.1f}{lat['p50']:>12.0f}")
    print(f"  {'p90 (ms)':<24}{QWEN_REF['p90_ms']:>12.1f}{lat['p90']:>12.0f}")
    print(f"  {'p99 (ms)':<24}{QWEN_REF['p99_ms']:>12.1f}{lat['p99']:>12.0f}")

    if args.json:
        Path(args.json).write_text(json.dumps({
            "model": "K3-sim",
            "tokens": args.tokens,
            "buffer_mb": args.buffer_mb,
            "hit_rate": hit_rate,
            "bytes_per_token_mb": bytes_per_token_mb,
            "compute_ms_per_token": compute_ms,
            "predicted_tok_s": predicted,
            "latency": lat,
            "throughput_match": rec["throughput_match"],
            "qwen_real_ref": QWEN_REF,
        }, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\n  wrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Track B — Gate 3: latency-gap measurement (idle disk stall vs total gen time).

Question (DECISION criteria, see docs/TRACK-B-GATE2-3-PLAN.md): on a disk-bound
config (model bigger than RAM), how much of the generation wall time is the
pipeline idle waiting on disk-mmap faults — i.e. what a prefetcher could
theoretically hide?

    idle_gap_% = disk_stall_ms_per_token / total_ms_per_token * 100
    total_ms_per_token       = 1000 / tok_s
    disk_stall_ms_per_token  = fault_mb_per_token / disk_bw_gbps   (1 GB/s = 1 MB/ms)

Verdict vs DECISION:  gap >= 10% → prefetch could matter (worth a deeper look);
gap < 10% → not worth (close Track B).

Inputs come from REAL telemetry only (honest — no fabricated numbers):
  --from-history PATH   read records from the server's usage_history.jsonl
                        (each generation: tok_s + paging.fault_mb_per_token)
  --tok-s / --fault-mb  or give explicit numbers (e.g. from EXP tables)
Default disk BW = EXP-025 calibrated effective disk→RAM bandwidth (0.38 GB/s).
Caveat: for models that FIT in RAM the stall is RAM-speed, not disk-speed, so
the default OVER-estimates their gap — only meaningful for >RAM models
(DS V4 Flash, K3). Use --disk-bw to override.

Dry-run on the committed data works out of the box:
    python scripts/measure_gate3_latency_gap.py --from-history data/usage_history.jsonl
Live run on a real machine (needs the model + server):
    python scripts/measure_dsv4flash.py   # records to usage_history.jsonl
    python scripts/measure_gate3_latency_gap.py --from-history data/usage_history.jsonl --model dsv4flash
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from typing import Iterator

# Windows consoles default to a legacy code page (e.g. cp874) that cannot
# encode arrows/em-dashes — force UTF-8 so the Thai docstring/help and the
# verdict lines never crash on print().
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# EXP-025 calibrated effective disk→RAM bandwidth (GB/s) for disk-mmap stalls
# on this rig. 0.38 GB/s is the honest measured value used across the repo.
DEFAULT_DISK_BW_GBPS = 0.38
DECISION_THRESHOLD_PCT = 10.0


@dataclass
class Record:
    model: str
    tok_s: float
    fault_mb_per_token: float


def idle_gap_percent(tok_s: float, fault_mb_per_token: float, disk_bw_gbps: float) -> float:
    """Fraction of wall time the pipeline is idle waiting on disk faults (%)."""
    if tok_s <= 0:
        return 0.0
    total_ms = 1000.0 / tok_s
    if disk_bw_gbps <= 0:
        return 0.0
    stall_ms = fault_mb_per_token / disk_bw_gbps  # MB / (GB/s) = ms (1 GB/s = 1 MB/ms)
    return min(100.0, stall_ms / total_ms * 100.0)


def read_history(path: str) -> Iterator[Record]:
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            paging = rec.get("paging") or {}
            tok_s = rec.get("tok_s")
            fault_mb = paging.get("fault_mb_per_token")
            if tok_s is None or fault_mb is None:
                continue
            yield Record(model=str(rec.get("model", "?")), tok_s=float(tok_s), fault_mb_per_token=float(fault_mb))


def summarize(records: list[Record], disk_bw: float, model_filter: str) -> tuple[float, float]:
    gaps = [idle_gap_percent(r.tok_s, r.fault_mb_per_token, disk_bw) for r in records]
    if not gaps:
        return 0.0, 0.0
    return min(gaps), max(gaps)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--from-history", metavar="PATH", help="read data/usage_history.jsonl records")
    src.add_argument("--tok-s", type=float, help="explicit tokens/sec (with --fault-mb)")
    ap.add_argument("--fault-mb", type=float, help="explicit disk MB pulled per token (with --tok-s)")
    ap.add_argument("--model", default="", help="filter history records by model name substring (e.g. dsv4)")
    ap.add_argument("--disk-bw", type=float, default=os.environ.get("WS_DISK_BW_GBPS", DEFAULT_DISK_BW_GBPS),
                    help="effective disk->RAM bandwidth GB/s (default EXP-025: 0.38)")
    ap.add_argument("--threshold", type=float, default=DECISION_THRESHOLD_PCT,
                    help="DECISION gap threshold %% (default 10)")
    args = ap.parse_args()

    records: list[Record] = []
    if args.tok_s is not None:
        if args.fault_mb is None:
            ap.error("--tok-s requires --fault-mb")
        records.append(Record(model="explicit", tok_s=args.tok_s, fault_mb_per_token=args.fault_mb))
    else:
        if not os.path.isfile(args.from_history):
            print(f"error: no such file: {args.from_history}", file=sys.stderr)
            return 2
        records = list(read_history(args.from_history))
        if args.model:
            records = [r for r in records if args.model.lower() in r.model.lower()]

    if not records:
        print("no records found", file=sys.stderr)
        return 2

    print(f"disk BW assumption: {args.disk_bw:g} GB/s (EXP-025 calibrated default; --disk-bw to override)")
    print(f"threshold (DECISION): gap >= {args.threshold:g}% = worth looking deeper | < {args.threshold:g}% = not worth\n")
    print(f"{'model':<22} {'tok/s':>7} {'MB/tok':>8} {'stall ms':>9} {'total ms':>9} {'gap %':>7}  verdict")
    print("-" * 82)
    for r in records:
        total_ms = 1000.0 / r.tok_s
        stall_ms = r.fault_mb_per_token / args.disk_bw
        gap = idle_gap_percent(r.tok_s, r.fault_mb_per_token, args.disk_bw)
        verdict = "worth looking" if gap >= args.threshold else "not worth"
        print(f"{r.model:<22} {r.tok_s:>7.2f} {r.fault_mb_per_token:>8.2f} {stall_ms:>9.1f} {total_ms:>9.1f} {gap:>6.1f}%  {verdict}")

    lo, hi = summarize(records, args.disk_bw, args.model)
    n = len(records)
    print("-" * 82)
    print(f"summary ({n} records): idle-gap min {lo:.1f}% / max {hi:.1f}%")
    if hi < args.threshold:
        print(f"verdict: gap < {args.threshold:g}% -> prefetch cannot hide meaningful time -> Track B not worth (per DECISION)")
    else:
        print(f"verdict: gap up to {hi:.1f}% >= {args.threshold:g}% -> prefetch COULD hide real time on some configs - "
              "check which config/phase (cold vs warm) before deciding")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Summarize the EXP-012 DS V4 Flash measurement matrix.

Reads the JSON written by measure_dsv4flash.py and prints a
markdown-ready comparison table (tok/s + paging, cold vs warm) plus
verdicts: best config, disk-bound vs compute-bound diagnosis.

Usage:
    python scripts/summarize_dsv4flash.py [matrix.json] [--baseline qwen.json]
    # default matrix.json = scripts/.dsv4flash_matrix_out.json

Output: prints table to stdout and appends a dated section to
research/experiments/EXP-012-dsv4flash-103gb/results.md
"""
import argparse
import datetime
import json
import os
import sys

DEFAULT_MATRIX = "scripts/.dsv4flash_matrix_out.json"
RESULTS_DOC = "research/experiments/EXP-012-dsv4flash-103gb/results.md"

# Qwen3.6-35B-A3B IQ1_M baseline (10 GB, fits RAM) — reference for how
# expert offload scales on the SAME machine/flags.
# NOTE 2026-08-10 P8: re-measured n-cpu-moe 0 t8 same-session = 75.9/73.9
# (old 66.1/60.8 from commit b73faa1 had colder page cache; faults/tok
# dropped 282->141 cold as the file became resident). Use the SAME-SESSION
# anchor from the DS V4 matrix for comparison, not this absolute number.
QWEN_BASELINE = {
    "cpu-moe t8":      {"cold": 14.2, "warm": 14.6, "cf": 7978, "wf": 4226},
    "n-cpu-moe 10 t8": {"cold": 36.9, "warm": 39.8, "cf": 2193, "wf": 1779},
    "n-cpu-moe 5 t8":  {"cold": 46.7, "warm": 44.1, "cf": 1386, "wf": 1370},
    "n-cpu-moe 0 t8":  {"cold": 75.9, "warm": 73.9, "cf": 141,  "wf": 550},
    "cpu-moe t16":     {"cold": 14.3, "warm": 13.6, "cf": 7978, "wf": 4109},
}


def fmt(v, nd=1):
    return "-" if v is None else f"{v:.{nd}f}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("matrix", nargs="?", default=DEFAULT_MATRIX)
    ap.add_argument("--baseline", default=None,
                    help="Qwen baseline matrix JSON (same shape) for comparison")
    ap.add_argument("--no-save", action="store_true",
                    help="print only, do not append to results.md")
    args = ap.parse_args()

    if not os.path.exists(args.matrix):
        print(f"matrix file not found: {args.matrix}", file=sys.stderr)
        print("run scripts/measure_dsv4flash.py first", file=sys.stderr)
        return 1
    with open(args.matrix, encoding="utf-8") as f:
        results = json.load(f)

    print("=== DS V4 Flash matrix (cold = page cache ว่าง, warm = cache อุ่น) ===\n")
    hdr = ("| config | cold tok/s | warm tok/s | cold faults/tok | "
           "warm faults/tok | cold disk MB/tok | warm disk MB/tok | VRAM MiB |")
    print(hdr)
    print("|---|---:|---:|---:|---:|---:|---:|---:|")
    for r in results:
        if "error" in r:
            print(f"| {r['config']} | **FAILED** — {r['error'][:60]} |")
            continue
        c, w = r["cold"], r["warm"]
        print(f"| {r['config']} | {fmt(c.get('tok_s'))} | {fmt(w.get('tok_s'))} "
              f"| {fmt(c.get('faults_per_token'), 0)} | {fmt(w.get('faults_per_token'), 0)} "
              f"| {fmt(c.get('disk_mb_per_token'))} | {fmt(w.get('disk_mb_per_token'))} "
              f"| {fmt(w.get('used_vram_mb'), 0)} |")

    ok = [r for r in results if "error" not in r]
    if not ok:
        print("\n### ALL CONFIGS FAILED — see errors above (likely OOM on >VRAM model).")
        return 0

    # --- verdicts ---
    print("\n### Verdicts")
    best = max(ok, key=lambda r: (r["warm"].get("tok_s") or 0))
    print(f"- **Best warm tok/s:** {best['config']} = "
          f"{fmt(best['warm'].get('tok_s'))} tok/s "
          f"(cold {fmt(best['cold'].get('tok_s'))})")

    if args.baseline and os.path.exists(args.baseline):
        with open(args.baseline, encoding="utf-8") as f:
            base = json.load(f)
        print("\n- **Vs Qwen baseline (same flags):**")
        for rb in base:
            if rb["config"] in QWEN_BASELINE:
                q = QWEN_BASELINE[rb["config"]]
                print(f"  - {rb['config']}: DS V4 {fmt(rb['warm'].get('tok_s'))} vs "
                      f"Qwen warm {fmt(q['warm'])} tok/s "
                      f"({fmt((rb['warm'].get('tok_s') or 0) / q['warm'] * 100, 0)}%)")

    # disk-bound heuristic: > 2 MB/tok sustained => paging dominates.
    # Fall back to page-FAULTS when the disk-MB estimate is unavailable
    # (GPU backend on Windows reports None — the DS V4 runs faulted 36-77k
    # pages/token with disk_mb None, which must still count as paging).
    worst_disk = max(ok, key=lambda r: (r["cold"].get("disk_mb_per_token") or 0))
    dd = worst_disk["cold"].get("disk_mb_per_token") or 0
    worst_fault = max(ok, key=lambda r: (r["cold"].get("faults_per_token") or 0))
    ff = worst_fault["cold"].get("faults_per_token") or 0
    if dd > 2:
        print(f"\n- **Disk-bound confirmed:** {worst_disk['config']} cold "
              f"{fmt(dd)} MB/tok — paging dominates; expect sharp dropoff "
              f"as page cache thrashes. (กุญแจ: ลด expert bytes หรือเพิ่ม RAM)")
    elif dd > 0 or ff > 0:
        print(f"\n- **Paging observed:** {worst_fault['config']} cold "
              f"{fmt(ff, 0)} faults/tok"
              + (f", {fmt(dd)} MB/tok" if dd else " (disk-MB estimate n/a)")
              + " — model does NOT fit RAM; each token faults the "
                "working set in from disk.")
    else:
        print("\n- **No paging observed** (model fits in RAM/page cache).")

    if not args.no_save:
        os.makedirs(os.path.dirname(RESULTS_DOC), exist_ok=True)
        with open(RESULTS_DOC, "a", encoding="utf-8") as f:
            f.write(f"\n## Matrix run {datetime.date.today().isoformat()}\n\n")
            f.write(hdr + "\n" + "|---|---:|---:|---:|---:|---:|---:|---:|\n")
            for r in results:
                if "error" in r:
                    f.write(f"| {r['config']} | **FAILED** — {r['error'][:60]} |\n")
                    continue
                c, w = r["cold"], r["warm"]
                f.write(f"| {r['config']} | {fmt(c.get('tok_s'))} | {fmt(w.get('tok_s'))} "
                        f"| {fmt(c.get('faults_per_token'), 0)} | {fmt(w.get('faults_per_token'), 0)} "
                        f"| {fmt(c.get('disk_mb_per_token'))} | {fmt(w.get('disk_mb_per_token'))} "
                        f"| {fmt(w.get('used_vram_mb'), 0)} |\n")
            f.write(f"\nBest warm tok/s: **{best['config']}** = "
                    f"{fmt(best['warm'].get('tok_s'))} tok/s\n")
        print(f"\nappended to {RESULTS_DOC}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

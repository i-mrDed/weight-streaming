"""Download DS V4 Flash 0731 UD-IQ3_XXS (4 shards, 104.21 GB) via the hub.

EXP-012 Phase 1: each shard is a separate hub download task
(``POST /v1/hub/download``). The hub streams to ``.part``, verifies the
FULL byte count AND the GGUF structure before rename (EXP-011b gate —
including the metadata-only shard-1 split case), and supports resume
from ``.part`` on cancel/failure.

Usage:
    python scripts/download_dsv4flash.py [--target DIR] [--dry-run]

Env:
    WS_PORT        hub server port (default 8765)
    WS_MODELS_DIR  default target dir (default: server's first model dir)

Prereq: disk free >= 110 GB. Check with --dry-run first (no writes).
"""
import argparse
import json
import os
import sys
import time
import urllib.request

REPO = "unsloth/DeepSeek-V4-Flash-0731-GGUF"
QUANT_DIR = "UD-IQ3_XXS"
SHARDS = [
    # (remote filename, exact size from HF tree API 2026-08-10)
    ("DeepSeek-V4-Flash-0731-UD-IQ3_XXS-00001-of-00004.gguf", 5_257_696),
    ("DeepSeek-V4-Flash-0731-UD-IQ3_XXS-00002-of-00004.gguf", 49_910_532_416),
    ("DeepSeek-V4-Flash-0731-UD-IQ3_XXS-00003-of-00004.gguf", 49_257_859_456),
    ("DeepSeek-V4-Flash-0731-UD-IQ3_XXS-00004-of-00004.gguf", 5_034_198_464),
]
TOTAL_BYTES = sum(s for _, s in SHARDS)

# Alternative (EXP-012 quant-options-comparison.md): TacoTakumi's
# expert-only requant — better KLD (0.263) + imatrix, 1.52x decode on
# spill rigs, but +11 GB. Select with --variant tacotakumi.
TACO_SHARDS = [
    ("DeepSeek-V4-Flash-0731-IQ3_XXS-imat-00001-of-00004.gguf", 28_787_493_728),
    ("DeepSeek-V4-Flash-0731-IQ3_XXS-imat-00002-of-00004.gguf", 28_772_928_160),
    ("DeepSeek-V4-Flash-0731-IQ3_XXS-imat-00003-of-00004.gguf", 28_772_928_160),
    ("DeepSeek-V4-Flash-0731-IQ3_XXS-imat-00004-of-00004.gguf", 28_924_047_424),
]
TACO_REPO = "TacoTakumi/DeepSeek-V4-Flash-0731-GGUF"


def req(method, path, body=None, timeout=30):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(f"http://127.0.0.1:{PORT}{path}", data=data,
                               method=method,
                               headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(r, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main():
    global PORT
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", default=os.environ.get("WS_MODELS_DIR", ""))
    ap.add_argument("--port", default=os.environ.get("WS_PORT", "8765"))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--variant", choices=["unsloth", "tacotakumi"],
                    default="unsloth",
                    help="unsloth UD-IQ3_XXS 104 GB (default) or "
                         "TacoTakumi IQ3_XXS 115 GB (better KLD, imatrix)")
    args = ap.parse_args()
    PORT = args.port
    global REPO, QUANT_DIR, SHARDS, TOTAL_BYTES
    if args.variant == "tacotakumi":
        REPO = TACO_REPO
        QUANT_DIR = ""
        SHARDS = TACO_SHARDS
        TOTAL_BYTES = sum(s for _, s in SHARDS)

    print(f"=== DS V4 Flash {args.variant} ({REPO}): {len(SHARDS)} shards, "
          f"{TOTAL_BYTES / 1e9:.2f} GB ===")
    if args.dry_run:
        for name, size in SHARDS:
            print(f"  {name}: {size / 1e9:.2f} GB")
        print(f"TOTAL: {TOTAL_BYTES / 1e9:.2f} GB — disk free must be "
              f">= {TOTAL_BYTES / 1e9 + 6:.0f} GB")
        return 0

    # Resolve target dir against the server's configured model dirs.
    if not args.target:
        cfg = req("GET", "/v1/config")
        dirs = cfg.get("models_dirs") or []
        if not dirs:
            print("ERROR: no model dirs on server — set WS_MODELS_DIR or "
                  "--target", file=sys.stderr)
            return 2
        args.target = dirs[0]
    print(f"target dir: {args.target}\n")

    results = []
    for name, size in SHARDS:
        remote = f"{QUANT_DIR}/{name}"
        print(f"--- {name} ({size / 1e9:.2f} GB) ---", flush=True)
        # If a previous run left a complete file, skip (idempotent re-run).
        final = os.path.join(args.target, name)
        if os.path.isfile(final) and os.path.getsize(final) == size:
            print("  already complete on disk — skip")
            results.append({"shard": name, "status": "skip",
                            "bytes": size})
            continue
        try:
            task = req("POST", "/v1/hub/download", {
                "repo_id": REPO, "filename": remote,
                "target_dir": args.target,
            }, timeout=30)
        except Exception as e:
            print(f"  ERROR starting download: {e}", file=sys.stderr)
            return 1
        tid = task["id"]
        # Poll progress (SSE would be nicer; polling is fine for a script).
        while True:
            time.sleep(5)
            t = req("GET", f"/v1/hub/downloads")
            cur = next((x for x in t["downloads"] if x["id"] == tid), None)
            if cur is None:
                print("  task vanished from list", file=sys.stderr)
                return 1
            status = cur["status"]
            done = cur.get("bytes_downloaded") or 0
            pct = done / size * 100 if size else 0
            eta = cur.get("eta_s")
            etas = f" eta {eta:.0f}s" if isinstance(eta, (int, float)) else ""
            print(f"  [{status}] {pct:6.2f}%  {done/1e9:.2f}/{size/1e9:.2f} GB"
                  f"{etas}  ", end="\r", flush=True)
            if status == "done":
                print(f"  [{status}] {pct:6.2f}%  {done/1e9:.2f} GB      ")
                results.append({"shard": name, "status": "done",
                                "bytes": done})
                break
            if status in ("failed", "cancelled"):
                print(f"\n  FAILED: {cur.get('error')}", file=sys.stderr)
                print("  Resume: re-run this script (hub resumes from .part)",
                      file=sys.stderr)
                return 1

    print("\n=== SUMMARY ===")
    ok = all(r["status"] in ("done", "skip") for r in results)
    for r in results:
        print(f"  {r['status']:>6}  {r['shard']}  ({r['bytes']/1e9:.2f} GB)")
    print(f"TOTAL on disk: {sum(r['bytes'] for r in results) / 1e9:.2f} / "
          f"{TOTAL_BYTES / 1e9:.2f} GB")
    if not ok:
        print("INCOMPLETE — re-run to resume remaining shards",
              file=sys.stderr)
        return 1
    print("ALL SHARDS COMPLETE ✓ — point WS_TEST_MODEL at "
          f"{os.path.join(args.target, SHARDS[0][0])} and run "
          "measure_dsv4flash.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())

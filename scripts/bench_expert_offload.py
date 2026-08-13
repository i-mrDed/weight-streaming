"""Expert offloading tiering matrix — real Qwen on the running server.

TASKS.md "Test llama.cpp expert offloading": measures whether llama.cpp's
expert-offload flags help on the PoC model (Qwen1.5-MoE-A2.7B Q2_K,
5.88 GB — fits the 12 GB VRAM entirely). Previous work covered the
35B-A3B (>VRAM) case (EXP-005/007/011); this closes the fits-VRAM case
on the PoC model with the same honest method.

Configs (llama.cpp expert tiering):
  baseline      — no extra args (server default: all GPU, auto placement)
  n-cpu-moe 10  — force 10 expert layers to CPU (offload experts to RAM)
  n-cpu-moe 0   — all experts on GPU (explicit, matches EXP-011 best)

Method: load through the API server with extra_args per config, warm up,
measure 3 warm runs of 100 tokens, read /v1/stats (tok/s + paging + VRAM).
The server is NOT restarted (it is the user's own server) — the clean-room
discipline does not apply here, matching EXP-025/027/028.

    python scripts/bench_expert_offload.py [--runs 3] [--json out.json]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from weight_stream.bench.measure import req, read_model_stats  # noqa: E402
from weight_stream.bench.measure import llama_cmdline  # noqa: E402

BASE = "http://127.0.0.1:8765"
MODEL_ID = "Qwen1.5-MoE-A2.7B_Q2_k"
MODEL_PATH = "research/models/Qwen1.5-MoE-A2.7B_Q2_k.gguf"
PROMPT = "The future of artificial intelligence is"

CONFIGS = {
    "baseline (auto)": "",
    "n-cpu-moe 10": "--n-cpu-moe 10",
    "n-cpu-moe 0 (all GPU)": "--n-cpu-moe 0",
}


def load(base: str, extra_args: str, timeout: int = 900) -> None:
    req(base, "POST", "/v1/models/unload", {"model_id": MODEL_ID}, timeout=30)
    req(base, "POST", "/v1/models/load", {
        "model_id": MODEL_ID,
        "model_path": MODEL_PATH,
        "n_ctx": 2048,
        "extra_args": extra_args,
    }, timeout=timeout)
    time.sleep(1)


def warm_gen(base: str, tokens: int = 8) -> None:
    req(base, "POST", "/v1/chat/completions", {
        "model": MODEL_ID,
        "messages": [{"role": "user", "content": "warmup"}],
        "max_tokens": tokens, "stream": False, "reasoning_mode": "off",
    }, timeout=600)
    time.sleep(1)


def gen(base: str, tokens: int = 100) -> dict[str, Any]:
    req(base, "POST", "/v1/chat/completions", {
        "model": MODEL_ID,
        "messages": [{"role": "user", "content": PROMPT}],
        "max_tokens": tokens, "stream": False, "reasoning_mode": "off",
    }, timeout=600)
    time.sleep(1)
    return read_model_stats(base, MODEL_ID)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--json", default="", help="Write JSON report to path")
    args = ap.parse_args()

    print(f"Expert offloading matrix — {MODEL_ID} (fits 12 GB VRAM)")
    print(f"  machine: i9-9900KF + RTX 3060 12 GB + 64 GB RAM\n")

    results: dict[str, Any] = {}
    for name, extra in CONFIGS.items():
        print(f"[{name}] extra_args='{extra}'")
        try:
            load(BASE, extra)
            cmd = llama_cmdline()
            print(f"  llama-server: {cmd[:160]}")
        except Exception as e:
            print(f"  LOAD FAILED: {e}")
            results[name] = {"error": str(e)}
            continue
        try:
            warm_gen(BASE)
            stats = []
            for i in range(args.runs):
                s = gen(BASE)
                stats.append(s)
                print(f"  run {i+1}: {s['tok_s']:.2f} tok/s "
                      f"(faults/tok {s['faults_per_token']}, "
                      f"VRAM {s['used_vram_mb']} MiB)")
            tok = [s["tok_s"] for s in stats]
            results[name] = {
                "extra_args": extra,
                "cmdline": cmd,
                "avg_tok_s": sum(tok) / len(tok),
                "runs": stats,
            }
            print(f"  avg: {sum(tok)/len(tok):.2f} tok/s\n")
        except Exception as e:
            print(f"  MEASURE FAILED: {e}")
            results[name] = {"error": str(e)}

    print("\n=== Summary ===")
    print(f"{'config':<22}{'avg tok/s':>12}")
    for name, r in results.items():
        if "error" in r:
            print(f"{name:<22}{'FAILED':>12}  {r['error']}")
        else:
            print(f"{name:<22}{r['avg_tok_s']:>12.2f}")

    # Restore baseline for the user's server.
    try:
        load(BASE, "")
        print("\n  (restored baseline: unloaded + reloaded without extra args)")
    except Exception:
        pass

    if args.json:
        Path(args.json).write_text(
            json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"  wrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

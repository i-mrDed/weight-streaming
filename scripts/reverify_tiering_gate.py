"""EXP-023 — re-verify the Thai quality gate on the auto-tiering default pair.

The gate re-runs the SAME fixed question set as EXP-022 (weight_stream/bench/
thai.py — 9 questions, temp 0) on the CURRENT default pair:

- fast    → Gemma 4 12B QAT+MTP (t8, EXP-022: 75.7 tok/s, gate 9/9, tonal 6/6)
- quality → Gemma 4 26B-A4B QAT+MTP (t12, EXP-019/020: 49-51 tok/s, 9/9, 6/6)

Each tier is loaded through the PRODUCTION routing path (POST /v1/tiering/route
with a deterministic short/long prompt), so the run uses the exact config the
user has — extra_args (MTP draft flags) + n_threads included. This confirms the
shipped defaults are still the best pair after all the surrounding changes,
not a hand-tuned lab load.

Usage: python scripts/reverify_tiering_gate.py [--out DIR]
Run against a LIVE server (python -m weight_stream.server) on 127.0.0.1:8765.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from weight_stream.bench import thai  # noqa: E402

BASE = "http://127.0.0.1:8765"


def _req(method: str, path: str, body: dict | None = None, timeout: int = 1800):
    import urllib.request

    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(
        f"{BASE}{path}",
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(r, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def load_tier(tier: str) -> tuple[str, int | None]:
    """Route a deterministic request to the tier and return the effective
    model_id + the tier's own max_tokens budget (production path: config
    extra_args + n_threads + evict/reuse)."""
    content = "สวัสดี" if tier == "fast" else "x" * 3001
    r = _req("POST", "/v1/tiering/route", {
        "messages": [{"role": "user", "content": content}],
    })
    assert r.get("tier") == tier, f"route returned {r.get('tier')} != {tier}"
    return r["model_id"], r.get("max_tokens")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="research/experiments/EXP-023-reverify-thai-gate")
    ap.add_argument("--tiers", default="fast,quality",
                    help="comma list of tiers to re-verify")
    ap.add_argument("--max-tokens", type=int, default=0,
                    help="max output tokens per question; 0 (default) = use "
                         "each tier's OWN budget from the route response "
                         "(fast 2048 / quality 8192 — EXP-023: the fast tier "
                         "burns its budget on a temp-0 repetition loop, so "
                         "never give it the full 8192)")
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    results: dict[str, dict] = {}

    for tier in args.tiers.split(","):
        tier = tier.strip()
        print(f"\n=== loading tier {tier} via production route ===", flush=True)
        model_id, tier_max_tokens = load_tier(tier)
        max_tokens = args.max_tokens or tier_max_tokens or 4096
        print(f"    loaded model_id={model_id} max_tokens={max_tokens}", flush=True)
        print(f"=== running Thai quality gate (9 fixed questions) ===", flush=True)
        t0 = time.monotonic()
        gate = thai.run_quality_gate(BASE, model_id,
                                     max_tokens=max_tokens)
        gate["tier"] = tier
        gate["load_path"] = "route"
        results[tier] = gate
        wall = time.monotonic() - t0
        print(f"    gate done in {wall:.0f}s — tok/s={gate['tok_s']}", flush=True)
        for qid, a in gate["answers"].items():
            final = (a["final"] or "").replace("\n", " ").strip()
            print(f"    [{qid}] {final[:100]}", flush=True)
        # free the slot for the next tier (single-port backend)
        try:
            _req("POST", "/v1/models/unload", {"model_id": model_id})
            print("    unloaded", flush=True)
        except Exception as e:
            print(f"    unload failed (ignored): {e}", flush=True)

    (out_dir / "gate.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nsaved -> {out_dir / 'gate.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

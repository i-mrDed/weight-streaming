"""Phase 4 real benchmark — hit rate / latency distribution / throughput.

Measures the REAL engine (llama-server via the API server at :8765) the
same honest way EXP-025/027 did, then computes the three Phase 4 metrics
with ``weight_stream.eval.metrics``:

1. **Hit rate** — from ``generation.paging.disk_mb_per_token`` vs the
   physics active-set size (EXP-025: Qwen 0.844 GB/token).
2. **Latency distribution** — per-token generation latency captured from
   the SSE stream (one chunk per token): p50/p90/p99/mean/max.
3. **Throughput** — tok/s from /v1/stats vs the physics prediction
   (calibrated cpu-ram bandwidth / bytes per token).

Run against the ALREADY-RUNNING server (no clean-room restart — that is
the user's own server; see EXP-025 validation which measured the same
way):

    python scripts/bench_phase4.py [--runs 3] [--tokens 100]
                                   [--prompt "The future of artificial intelligence is"]
                                   [--json out.json]

The first run after load is the honest COLD number (weights fault in from
disk); subsequent runs are warm. The script reports both, but the Phase 4
metrics spec (TASKS.md "Define evaluation metrics") requires warm runs for
the headline numbers — cold is recorded for the hit-rate story.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any, Optional

import sys as _sys
from pathlib import Path as _Path

_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent))

from weight_stream.eval.metrics import evaluate_run  # noqa: E402
from weight_stream.eval.metrics import throughput_matches  # noqa: E402

DEFAULT_BASE = "http://127.0.0.1:8765"
DEFAULT_MODEL = "Qwen1.5-MoE-A2.7B_Q2_k"
DEFAULT_PROMPT = "The future of artificial intelligence is"


def _req(base: str, method: str, path: str, body: Optional[dict] = None,
         timeout: int = 600) -> Any:
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(
        f"{base}{path}", data=data, method=method,
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(r, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
    return json.loads(raw) if raw else None


def stream_generate(base: str, model: str, prompt: str, tokens: int,
                    timeout: int = 600) -> tuple[list[float], float]:
    """Stream one generation; return (per_token_ms, total_seconds).

    Each SSE ``data:`` chunk carries one token; inter-chunk arrival times
    are the per-token generation latency. The first token's latency is
    measured from the first chunk (includes prompt processing), which is
    the honest end-to-end per-token cost a caller sees.
    """
    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": tokens,
        "stream": True,
        "temperature": 0.7,
        "reasoning_mode": "off",
    }
    req = urllib.request.Request(
        f"{base}/v1/chat/completions", data=json.dumps(body).encode(),
        method="POST", headers={"Content-Type": "application/json"})
    t0 = time.perf_counter()
    per_token: list[float] = []
    last = t0
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        for raw_line in resp:
            line = raw_line.decode("utf-8").strip()
            if not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if payload == "[DONE]":
                break
            now = time.perf_counter()
            per_token.append((now - last) * 1000.0)
            last = now
    total = time.perf_counter() - t0
    return per_token, total


def read_stats(base: str, model: str) -> dict[str, Any]:
    raw = _req(base, "GET", f"/v1/stats?model={model}", timeout=30)
    models = (raw or {}).get("models", {}) or {}
    m = models.get(model, models)
    gen = m.get("generation") or {}
    paging = gen.get("paging") or {}
    return {
        "tok_s": gen.get("tokens_per_sec"),
        "faults_per_token": paging.get("faults_per_token"),
        "fault_mb_per_token": paging.get("fault_mb_per_token"),
        "disk_mb_per_token": paging.get("disk_mb_per_token"),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base", default=DEFAULT_BASE)
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--tokens", type=int, default=100)
    ap.add_argument("--prompt", default=DEFAULT_PROMPT)
    ap.add_argument("--json", default="", help="Write JSON report to path")
    args = ap.parse_args()

    # Physics prediction: EXP-025 calibrated cpu-ram bandwidth (19.18 GB/s)
    # over Qwen's active set (2.7B x 2.5 bpw = 0.844 GB/token).
    import simulator.physics as physics
    spec = physics.QWEN
    bw = physics.DEFAULT_EFFECTIVE_BW_GBPS["cpu-ram"]
    bytes_per_token_mb = spec.bytes_per_token_gb * 1024.0
    predicted = physics.tok_per_sec(bw, spec.bytes_per_token_gb)

    print(f"Phase 4 evaluation — {args.model}")
    print(f"  physics prediction: {predicted:.2f} tok/s "
          f"(bytes/token {bytes_per_token_mb:.1f} MB)")
    print()

    # Warmup (also evicts nothing — just touches the model once).
    _req(args.base, "POST", "/v1/chat/completions", {
        "model": args.model,
        "messages": [{"role": "user", "content": "warmup"}],
        "max_tokens": 8, "stream": False, "reasoning_mode": "off",
    }, timeout=600)
    time.sleep(1)

    runs: list[dict[str, object]] = []
    for i in range(args.runs):
        per_token, _total = stream_generate(
            args.base, args.model, args.prompt, args.tokens)
        stats = read_stats(args.base, args.model)
        if not per_token:
            print(f"  run {i+1}: no tokens streamed — retrying")
            continue
        rec = evaluate_run(
            tok_s=stats["tok_s"],
            predicted_tok_s=predicted,
            disk_mb_per_token=stats["disk_mb_per_token"],
            bytes_per_token_mb=bytes_per_token_mb,
            per_token_ms=per_token,
        )
        rec["run"] = i + 1
        rec["n_tokens"] = len(per_token)
        rec["faults_per_token"] = stats["faults_per_token"]
        rec["fault_mb_per_token"] = stats["fault_mb_per_token"]
        runs.append(rec)
        lat = rec["latency"]  # type: ignore[assignment]
        print(f"  run {i+1}: {rec['tok_s']:.2f} tok/s "
              f"(err {rec['throughput_error']:+.1%}) "
              f"hit {rec['hit_rate']:.3f} "
              f"lat p50 {lat['p50']:.1f} / p90 {lat['p90']:.1f} / "
              f"p99 {lat['p99']:.1f} ms")

    if not runs:
        print("ERROR: no valid runs captured")
        return 1

    # Headline = warm runs (skip run 1 if it was the cold first touch —
    # EXP-025 established the honest number is the WARM average).
    warm = runs[1:] if len(runs) > 1 else runs
    avg_tok = sum(float(r["tok_s"]) for r in warm) / len(warm)  # type: ignore[arg-type]
    hit_vals = [float(r["hit_rate"]) for r in warm]
    lat_vals = [float(r["latency"]["p50"]) for r in warm]  # type: ignore[index]
    match = throughput_matches(avg_tok, predicted)

    summary = {
        "model": args.model,
        "runs": runs,
        "summary": {
            "n_runs": len(runs),
            "n_warm": len(warm),
            "avg_tok_s_warm": avg_tok,
            "predicted_tok_s": predicted,
            "throughput_error_warm": (avg_tok - predicted) / predicted,
            "throughput_match": match,
            "avg_hit_rate_warm": sum(hit_vals) / len(hit_vals),
            "avg_latency_p50_warm": sum(lat_vals) / len(lat_vals),
        },
    }

    print()
    print(f"  warm average: {avg_tok:.2f} tok/s vs predicted {predicted:.2f} "
          f"({(avg_tok - predicted) / predicted:+.1%}) "
          f"{'PASS' if match else 'FAIL'} (tol +/-15%)")
    print(f"  hit rate (warm avg): {summary['summary']['avg_hit_rate_warm']:.3f}")
    print(f"  latency p50 (warm avg): "
          f"{summary['summary']['avg_latency_p50_warm']:.1f} ms")

    if args.json:
        Path(args.json).write_text(
            json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\n  wrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

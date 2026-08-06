"""Measure llama-server CPU-thread scaling on the loaded GPU MoE model.

For each -t value (default 8, 12, 16, then 8 again to check drift):
  1. unload any loaded model
  2. load the target model with n_threads=N (GPU backend + --cpu-moe via
     WS_LLAMA_EXTRA_ARGS on the server)
  3. one warm-up generation (fills OS page cache)
  4. one measured generation, streaming via /v1/generate?stream=true with
     per-SSE-event timestamps → average tok/s AND p95 per-token latency
  5. also read /v1/stats generation block for the server-side numbers

Usage: python scripts/measure_threads_scaling.py
Env: WS_THREADS="8 12 16" to override; model path fixed to the A3B test model.
"""
import json
import os
import statistics
import sys
import time
import urllib.request

BASE = os.environ.get("WS_API", "http://127.0.0.1:8765")
MODEL = os.environ.get(
    "WS_TEST_MODEL",
    "D:/models/Qwen3.6-35B-A3B-GGUF/Qwen3.6-35B-A3B-UD-IQ2_M.gguf",
)
MODEL_ID = os.environ.get("WS_TEST_MODEL_ID", "qwen36a3b")
PROMPT = os.environ.get(
    "WS_TEST_PROMPT",
    "Write a 3-sentence story about a cat astronaut. Be concise.",
)
MAX_TOKENS = int(os.environ.get("WS_TEST_TOKENS", "200"))
THREADS = [int(t) for t in os.environ.get("WS_THREADS", "8 12 16 8").split()]


def req(method, path, body=None, timeout=600):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(f"{BASE}{path}", data=data, method=method,
                               headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(r, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def unload():
    try:
        req("POST", "/v1/models/unload", {"model_id": MODEL_ID}, timeout=30)
    except Exception:
        pass
    time.sleep(1)


def load(n_threads):
    r = req("POST", "/v1/models/load", {
        "model_id": MODEL_ID,
        "model_path": MODEL,
        "n_ctx": 2048,
        "n_threads": n_threads,
        "buffer_mb": 64,
    }, timeout=600)
    assert r.get("status") == "loaded", r


def stream_measure():
    """Stream /v1/chat/completions (SSE, per-delta events), timing each chunk.

    llama-server's OpenAI-compat endpoint emits one data: event per token
    delta (reasoning/content/tool fragments). Each non-empty content delta
    counts as one generated token; inter-event gaps give the per-token
    latency distribution → p95. The first event (prompt processing) is
    excluded from the per-token stats.

    Returns (token_count, per_token_ms list, elapsed_s, tok_s_avg).
    """
    body = json.dumps({
        "model": MODEL_ID,
        "messages": [{"role": "user", "content": PROMPT}],
        "max_tokens": MAX_TOKENS, "temperature": 0.7, "stream": True,
    }).encode()
    req = urllib.request.Request(
        f"{BASE}/v1/chat/completions", data=body, method="POST",
        headers={"Content-Type": "application/json"})
    start = time.time()
    times = []
    last = start
    n = 0
    with urllib.request.urlopen(req, timeout=900) as resp:
        for raw in resp:
            line = raw.decode("utf-8", errors="replace").strip()
            if not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if payload == "[DONE]":
                break
            try:
                ev = json.loads(payload)
            except json.JSONDecodeError:
                continue
            delta = (ev.get("choices") or [{}])[0].get("delta") or {}
            tok = delta.get("content") or ""
            now = time.time()
            times.append((now - last) * 1000)
            last = now
            if tok:
                n += 1
    elapsed = time.time() - start
    if n == 0:
        return 0, [], elapsed, 0.0
    # Drop the FIRST inter-event gap: it includes prompt processing (prefill
    # is a different beast from decode latency and would skew p95 badly).
    decode_times = times[1:]
    # sum(decode_times) spans first→last token, i.e. n-1 decode steps.
    denom = (sum(decode_times) / 1000) if decode_times else elapsed
    tok_s = max(n - 1, 1) / max(denom, 1e-6)
    return n, decode_times, elapsed, tok_s


def server_stats():
    d = req("GET", f"/v1/stats?model={MODEL_ID}", timeout=10)
    return d["models"]["generation"]


def p95(xs):
    if not xs:
        return None
    xs = sorted(xs)
    return xs[int(len(xs) * 0.95)]


def main():
    results = []
    for t in THREADS:
        print(f"\n=== n_threads = {t} ===", flush=True)
        unload()
        load(t)
        # warm-up: fill OS page cache so the measured run is steady-state
        print("  warm-up…", flush=True)
        stream_measure()
        time.sleep(1)
        n, per_tok, elapsed, raw_tok_s = stream_measure()
        stats = server_stats()
        sv_tok_s = stats.get("tokens_per_sec")
        sv_elapsed = stats.get("elapsed")
        p = p95(per_tok) if per_tok else None
        med = statistics.median(per_tok) if per_tok else None
        avg = statistics.mean(per_tok) if per_tok else None
        print(f"  tokens={n}  SSE tok/s={raw_tok_s:.1f}  server tok/s={sv_tok_s:.1f}  "
              f"elapsed={elapsed:.2f}s  server_elapsed={sv_elapsed:.2f}")
        if per_tok:
            print(f"  per-token ms: avg={avg:.1f}  median={med:.1f}  p95={p:.1f}  "
                  f"max={max(per_tok):.1f}")
        results.append({
            "threads": t, "tokens": n, "raw_tok_s": round(raw_tok_s, 2),
            "server_tok_s": sv_tok_s, "elapsed": round(elapsed, 2),
            "server_elapsed": sv_elapsed,
            "per_token_ms_avg": round(avg, 1) if avg else None,
            "per_token_ms_median": round(med, 1) if med else None,
            "per_token_ms_p95": round(p, 1) if p else None,
            "per_token_ms_max": round(max(per_tok), 1) if per_tok else None,
        })
        unload()

    print("\n\n=== SUMMARY ===")
    print(json.dumps(results, indent=2))
    # machine-readable tail for the EXP writeup
    with open("scripts/.threads_scaling_out.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print("saved scripts/.threads_scaling_out.json")


if __name__ == "__main__":
    sys.exit(main())

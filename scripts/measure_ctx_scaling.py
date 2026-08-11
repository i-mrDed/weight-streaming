"""Measure KV-cache / n_ctx scaling on the loaded GPU MoE model.

For each n_ctx value (default 2048, 8192, 32768, then 2048 again to check
drift):
  1. unload any loaded model
  2. capture baseline VRAM (nvidia-smi memory.used)
  3. load the target model with n_ctx=N, n_threads=8 (GPU backend +
     --cpu-moe via WS_LLAMA_EXTRA_ARGS on the server)
  4. capture VRAM with model loaded → delta = model + KV cache at ctx N
  5. one warm-up generation (fills OS page cache)
  6. one measured generation, streaming via /v1/chat/completions with
     per-SSE-event timestamps → avg tok/s AND p95 per-token latency
  7. read /v1/stats for the server-side numbers
  8. unload, verify VRAM returns to baseline

Usage: python scripts/measure_ctx_scaling.py
Env: WS_CTX="2048 8192 32768 2048" to override; WS_TEST_TOKENS for length.
"""
import json
import os
import statistics
import subprocess
import sys
import time
import urllib.request

BASE = os.environ.get("WS_API", "http://127.0.0.1:8765")
# ~ expands to THIS machine's home (hermetic default — no dev-machine
# path baked in); override with WS_TEST_MODEL for any other model.
MODEL = os.path.expanduser(os.environ.get(
    "WS_TEST_MODEL",
    "~/models/Qwen3.6-35B-A3B-GGUF/Qwen3.6-35B-A3B-UD-IQ2_M.gguf",
))
MODEL_ID = os.environ.get("WS_TEST_MODEL_ID", "qwen36a3b")
PROMPT = os.environ.get(
    "WS_TEST_PROMPT",
    "Write a 3-sentence story about a cat astronaut. Be concise.",
)
MAX_TOKENS = int(os.environ.get("WS_TEST_TOKENS", "200"))
CTX_VALUES = [int(c) for c in os.environ.get("WS_CTX", "2048 8192 32768 2048").split()]


def req(method, path, body=None, timeout=600):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(f"{BASE}{path}", data=data, method=method,
                               headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(r, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def vram_mib():
    """Current GPU memory.used in MiB via nvidia-smi (or None if unavailable)."""
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10,
        ).stdout.strip()
        return int(out.splitlines()[0])
    except Exception:
        return None


def unload():
    try:
        req("POST", "/v1/models/unload", {"model_id": MODEL_ID}, timeout=30)
    except Exception:
        pass
    time.sleep(2)


def backend_props():
    """Read the backend llama-server's /props to verify WHICH model/ctx is live.

    Regression guard (2026-08-06): a stale Jan llama-server was squatting on
    port 8805 (our default backend port) and answered /health, so the backend
    thought its own subprocess was ready while requests went to the WRONG
    model (Qwythos-9B @ -c 1024). After every load we now confirm the props
    show our model path — otherwise the measurement is meaningless.
    """
    try:
        with urllib.request.urlopen(
            os.environ.get("WS_BACKEND_PROPS", "http://127.0.0.1:8805/props"),
            timeout=5,
        ) as r:
            return json.loads(r.read().decode("utf-8", errors="replace"))
    except Exception:
        return {}


def load(n_ctx):
    r = req("POST", "/v1/models/load", {
        "model_id": MODEL_ID,
        "model_path": MODEL,
        "n_ctx": n_ctx,
        "n_threads": 8,
        "buffer_mb": 64,
    }, timeout=900)
    assert r.get("status") == "loaded", r


def verify_backend():
    """After the first generation (subprocess spawn), confirm /props shows
    OUR model. Lazy-spawn guard: the backend only starts llama-server on the
    first request, so this must run AFTER a warm-up generation, not after
    load(). Raises if a stale server is answering on the backend port."""
    for _ in range(5):
        props = backend_props()
        live_path = props.get("model_path") or props.get("model_name") or ""
        if "Qwen3.6-35B" in live_path:
            return props
        time.sleep(1)
    raise RuntimeError(
        f"backend /props does not show our model — stale server? got: {live_path!r}"
    )


def stream_measure():
    """Stream /v1/chat/completions (SSE), timing each content delta."""
    body = json.dumps({
        "model": MODEL_ID,
        "messages": [{"role": "user", "content": PROMPT}],
        "max_tokens": MAX_TOKENS, "temperature": 0.7, "stream": True,
    }).encode()
    r = urllib.request.Request(
        f"{BASE}/v1/chat/completions", data=body, method="POST",
        headers={"Content-Type": "application/json"})
    start = time.time()
    times = []
    last = start
    n = 0
    with urllib.request.urlopen(r, timeout=900) as resp:
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
    decode_times = times[1:]  # drop prefill gap
    denom = (sum(decode_times) / 1000) if decode_times else elapsed
    tok_s = max(n - 1, 1) / max(denom, 1e-6)
    return n, decode_times, elapsed, tok_s


def server_stats():
    d = req("GET", f"/v1/stats?model={MODEL_ID}", timeout=10)
    return d["models"].get("generation", {}), d["models"]


def p95(xs):
    if not xs:
        return None
    xs = sorted(xs)
    return xs[int(len(xs) * 0.95)]


def main():
    # EXP-009 clean-room gate: abort when the environment is contaminated
    # (legacy server, orphan llama-server, port squatting). Read-only check.
    # SKIPPED when this harness is invoked as a SUB-HARNESS by
    # measure_ncmoe_matrix.py (WS_SKIP_GATE=1): there a llama-server is
    # deliberately running (the matrix loads the model and verified its
    # flags itself) — the gate would false-FAIL on it.
    if os.environ.get("WS_SKIP_GATE") != "1":
        checker = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "check_clean_environment.py")
        p = subprocess.run([sys.executable, checker], capture_output=True, text=True)
        print(p.stdout, end="", flush=True)
        if p.returncode >= 2:
            print("ABORTING: environment check FAILED - fix the findings and re-run.",
                  file=sys.stderr)
            return 2

    base_vram = vram_mib()
    print(f"baseline VRAM (no model): {base_vram} MiB", flush=True)
    results = []
    for ctx in CTX_VALUES:
        print(f"\n=== n_ctx = {ctx} ===", flush=True)
        unload()
        v0 = vram_mib()
        load(ctx)
        time.sleep(2)
        v1 = vram_mib()  # pre-generation VRAM (llama.cpp allocates GPU buffers lazily)
        # warm-up: fill OS page cache so the measured run is steady-state
        # (also triggers the lazy subprocess spawn — verified afterwards)
        print("  warm-up…", flush=True)
        stream_measure()
        props = verify_backend()
        print(f"  backend: {props.get('model_path','?').replace(chr(92),'/')[-46:]!r} "
              f"n_gl={props.get('n_gpu_layers')} ctx={props.get('n_ctx')}")
        time.sleep(1)
        n, per_tok, elapsed, raw_tok_s = stream_measure()
        time.sleep(1)
        v2 = vram_mib()  # post-generation VRAM (KV cache + compute buffers live here)
        stats, model_blk = server_stats()
        sv_tok_s = stats.get("tokens_per_sec")
        sv_elapsed = stats.get("elapsed")
        p = p95(per_tok) if per_tok else None
        med = statistics.median(per_tok) if per_tok else None
        avg = statistics.mean(per_tok) if per_tok else None
        print(f"  tokens={n}  SSE tok/s={raw_tok_s:.1f}  server tok/s={sv_tok_s:.1f}  "
              f"elapsed={elapsed:.2f}s")
        print(f"  VRAM: before_load={v0} MiB  after_load={v1} MiB  after_gen={v2} MiB  "
              f"kv_delta={v2 - v1 if v1 and v2 else None} MiB")
        if per_tok:
            print(f"  per-token ms: avg={avg:.1f}  median={med:.1f}  p95={p:.1f}  "
                  f"max={max(per_tok):.1f}")
        results.append({
            "n_ctx": ctx, "tokens": n, "raw_tok_s": round(raw_tok_s, 2),
            "server_tok_s": sv_tok_s, "elapsed": round(elapsed, 2),
            "server_elapsed": sv_elapsed,
            "vram_before_mib": v0, "vram_after_load_mib": v1,
            "vram_after_gen_mib": v2,
            "kv_cache_delta_mib": (v2 - v1) if (v1 and v2) else None,
            "per_token_ms_avg": round(avg, 1) if avg else None,
            "per_token_ms_median": round(med, 1) if med else None,
            "per_token_ms_p95": round(p, 1) if p else None,
            "per_token_ms_max": round(max(per_tok), 1) if per_tok else None,
        })
        unload()
        v3 = vram_mib()
        print(f"  after unload VRAM: {v3} MiB (baseline {base_vram})")
        results[-1]["vram_after_unload_mib"] = v3

    print("\n\n=== SUMMARY ===")
    print(json.dumps(results, indent=2))
    with open("scripts/.ctx_scaling_out.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print("saved scripts/.ctx_scaling_out.json")


if __name__ == "__main__":
    sys.exit(main())

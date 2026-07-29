"""End-to-end verification for TASKS items 4-5 with a real GGUF + SPA server.

Checks (acceptance criteria from docs/HANDOFF_STREAMING_RELIABILITY.md):
1. While generating a long response, GET /health and GET /v1/stats return promptly.
2. Stop/cancel leaves the model lock free; a new generation works afterwards.
3. /v1/stats changes during/after generation and reflects the wrapper's real
   measurements (tok/s, token_count, page cache).
4. Streaming chat produces a coherent native-template response.

Usage: python scripts/verify_items_45.py
Prints a JSON summary at the end.
"""

import json
import socket
import sys
import threading
import time
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8765"
MODEL_PATH = "research/models/Qwen1.5-MoE-A2.7B_Q2_k.gguf"
MODEL_ID = "qwen-e2e"
RESULTS = {"checks": {}}


def http_json(path, method="GET", body=None, timeout=30):
    url = BASE + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={"Content-Type": "application/json"} if data else {},
    )
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        payload = json.loads(resp.read().decode())
    return payload, time.perf_counter() - t0


def wait_for_server(deadline_s=60):
    start = time.time()
    while time.time() - start < deadline_s:
        try:
            http_json("/health", timeout=2)
            return True
        except Exception:
            time.sleep(0.5)
    return False


def load_model():
    print(f"[load] POST /v1/models/load {MODEL_PATH} (this can take a while)")
    t0 = time.time()
    payload, _ = http_json(
        "/v1/models/load",
        method="POST",
        body={
            "model_id": MODEL_ID,
            "model_path": MODEL_PATH,
            "buffer_mb": 256,
            "n_ctx": 2048,
            "force": True,
        },
        timeout=600,
    )
    elapsed = time.time() - t0
    print(f"[load] done in {elapsed:.1f}s: {payload}")
    RESULTS["model_load_seconds"] = round(elapsed, 2)
    return payload


def stream_chat(messages, max_tokens, on_token=None, stop_after=None):
    """Open an SSE chat stream. Returns (text, n_chunks, first_token_latency, total_seconds)."""
    body = json.dumps({
        "model": MODEL_ID,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0.4,
        "top_p": 0.9,
        "stream": True,
    }).encode()
    req = urllib.request.Request(
        BASE + "/v1/chat/completions", data=body, method="POST",
        headers={"Content-Type": "application/json"},
    )
    text_parts = []
    n_chunks = 0
    t0 = time.perf_counter()
    first_token = None
    with urllib.request.urlopen(req, timeout=600) as resp:
        buf = b""
        while True:
            piece = resp.read(256)
            if not piece:
                break
            buf += piece
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                line = line.decode(errors="replace").strip()
                if not line.startswith("data: "):
                    continue
                data = line[6:]
                if data == "[DONE]":
                    continue
                try:
                    chunk = json.loads(data)
                except json.JSONDecodeError:
                    continue
                delta = chunk["choices"][0].get("delta", {}).get("content", "")
                if delta:
                    if first_token is None:
                        first_token = time.perf_counter() - t0
                    n_chunks += 1
                    text_parts.append(delta)
                    if on_token:
                        on_token(delta)
                    if stop_after and n_chunks >= stop_after:
                        return "".join(text_parts), n_chunks, first_token, time.perf_counter() - t0, resp
    return "".join(text_parts), n_chunks, first_token, time.perf_counter() - t0, None


def check_responsiveness_during_generation():
    """Item 4 core check: /health + /v1/stats stay fast while tokens stream."""
    health_latencies = []
    stats_latencies = []
    stop_flag = threading.Event()

    def poller():
        while not stop_flag.is_set():
            try:
                _, lat = http_json("/health", timeout=5)
                health_latencies.append(lat)
            except Exception as ex:
                health_latencies.append(f"ERROR:{ex}")
            try:
                _, lat = http_json("/v1/stats", timeout=5)
                stats_latencies.append(lat)
            except Exception as ex:
                stats_latencies.append(f"ERROR:{ex}")
            time.sleep(0.2)

    poll_thread = threading.Thread(target=poller, daemon=True)
    poll_thread.start()

    text, n_chunks, first_token, total, _ = stream_chat(
        [{"role": "user", "content": "Write a detailed 300-word essay about the history of the printing press."}],
        max_tokens=220,
    )
    stop_flag.set()
    poll_thread.join(timeout=5)

    numeric_health = [x for x in health_latencies if isinstance(x, float)]
    numeric_stats = [x for x in stats_latencies if isinstance(x, float)]
    errors = [x for x in health_latencies + stats_latencies if not isinstance(x, float)]

    result = {
        "tokens_streamed": n_chunks,
        "first_token_latency_s": round(first_token, 3) if first_token else None,
        "generation_seconds": round(total, 3),
        "client_toks_per_s": round(n_chunks / total, 2) if total else 0,
        "health_polls": len(numeric_health),
        "health_max_latency_ms": round(max(numeric_health) * 1000, 1) if numeric_health else None,
        "health_avg_latency_ms": round(sum(numeric_health) / len(numeric_health) * 1000, 1) if numeric_health else None,
        "stats_polls": len(numeric_stats),
        "stats_max_latency_ms": round(max(numeric_stats) * 1000, 1) if numeric_stats else None,
        "poll_errors": errors[:3],
        "response_preview": text[:160],
    }
    ok = (
        n_chunks > 20
        and len(errors) == 0
        and numeric_health
        and max(numeric_health) < 1.0
        and numeric_stats
        and max(numeric_stats) < 2.0
    )
    RESULTS["checks"]["responsiveness_during_generation"] = "PASS" if ok else "FAIL"
    RESULTS["responsiveness"] = result
    print(f"[check1] responsiveness: {'PASS' if ok else 'FAIL'} -> {json.dumps(result, ensure_ascii=False)}")


def check_telemetry_is_real():
    """Item 5: /v1/stats reflects the wrapper's real measurements after a chat run."""
    stats, _ = http_json("/v1/stats")
    model_stats = stats.get("models", {}).get(MODEL_ID, {})
    gen = model_stats.get("generation", {})
    page = model_stats.get("page_cache", {})
    model = model_stats.get("model", {})

    result = {
        "generation": gen,
        "page_cache": page,
        "model": model,
        "buffer": {k: model_stats.get("buffer", {}).get(k) for k in ("hit_rate", "total_accesses", "hits", "misses")},
    }
    ok = (
        gen.get("token_count", 0) > 20
        and gen.get("tokens_per_sec", 0) > 0
        and "prompt" in gen
    )
    RESULTS["checks"]["real_telemetry_in_stats"] = "PASS" if ok else "FAIL"
    RESULTS["telemetry"] = result
    print(f"[check2] telemetry: {'PASS' if ok else 'FAIL'} -> {json.dumps(result, ensure_ascii=False)}")


def check_cancellation():
    """Item 4: aborting a stream releases the lock; the next request works."""
    text, n_chunks, _, partial_seconds, resp = stream_chat(
        [{"role": "user", "content": "Count from 1 to 200 slowly, one number per line."}],
        max_tokens=300,
        stop_after=8,
    )
    if resp is not None:
        resp.close()  # simulate client disconnect / Stop button
    time.sleep(1.0)  # give the server a moment to process the disconnect

    health_ok = False
    try:
        payload, lat = http_json("/health", timeout=5)
        health_ok = payload.get("status") == "ok"
    except Exception:
        pass

    # A fresh generation must succeed: proves the per-model lock was released
    # and _generating was reset.
    text2, n2, ft2, total2, _ = stream_chat(
        [{"role": "user", "content": "Say exactly: cancellation verified."}],
        max_tokens=24,
    )
    regen_ok = n2 > 0

    result = {
        "cancelled_after_tokens": n_chunks,
        "cancelled_stream_seconds": round(partial_seconds, 3),
        "health_after_cancel_ok": health_ok,
        "regeneration_tokens": n2,
        "regeneration_response": text2[:120],
    }
    ok = health_ok and regen_ok
    RESULTS["checks"]["cancellation_releases_lock"] = "PASS" if ok else "FAIL"
    RESULTS["cancellation"] = result
    print(f"[check3] cancellation: {'PASS' if ok else 'FAIL'} -> {json.dumps(result, ensure_ascii=False)}")


def main():
    # Windows console codecs (cp874 etc.) choke on model output; force UTF-8.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    if not wait_for_server():
        print("FATAL: server did not come up on :8765")
        sys.exit(2)
    print("[server] healthy")

    load_model()

    check_responsiveness_during_generation()
    check_telemetry_is_real()
    check_cancellation()

    passed = sum(1 for v in RESULTS["checks"].values() if v == "PASS")
    total = len(RESULTS["checks"])
    RESULTS["summary"] = f"{passed}/{total} checks passed"
    print("\n=== SUMMARY ===")
    print(json.dumps(RESULTS, indent=2, ensure_ascii=False))
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()

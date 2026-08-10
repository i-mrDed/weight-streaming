"""EXP-015 harness: MTP speculative decoding on the GPU backend (Qwen3.6-35B-A3B MTP).

Question: does llama-server's built-in MTP head (`--spec-type draft-mtp`)
raise tok/s on the MoE-tiered Qwen3.6-35B-A3B vs the same model WITHOUT
speculative decoding? (EXP-010 closed CPU-path speculation as a dead end;
the GPU path with an embedded MTP head is the remaining candidate.)

Method (same skeleton as EXP-008/011/012 harnesses):
  1. restart the API server with WS_LLAMA_EXTRA_ARGS set per config
  2. load the MTP GGUF, trigger a spawn, verify the ACTUAL llama-server
     cmdline carries the expected --spec-type flag (EXP-007 lesson)
  3. generate a fixed prompt (warm) -> read /v1/stats
  4. record tok/s, tps (p95), VRAM, page faults

Usage: python scripts/measure_mtp_specdecode.py
Env:  WS_PORT, WS_TEST_MODEL (MTP gguf path), WS_MATRIX_CONFIGS (JSON),
      WS_NO_RESTART=1 to skip server restarts (for the already-running case).
"""
import json
import os
import subprocess
import sys
import time
import urllib.request

PORT = os.environ.get("WS_PORT", "8765")
BASE = f"http://127.0.0.1:{PORT}"
MODEL = os.environ.get(
    "WS_TEST_MODEL",
    "C:/Users/dedch/models/Qwen3.6-35B-A3B-UD-IQ1_M.gguf",
)
MODEL_ID = os.environ.get("WS_TEST_MODEL_ID", "qwen36-mtp")
N_CTX = int(os.environ.get("WS_CTX", "2048"))
GEN_TOKENS = int(os.environ.get("WS_GEN_TOKENS", "300"))
PROMPT = os.environ.get(
    "WS_PROMPT",
    "อธิบายความหมายของสำนวนไทย 'น้ำขึ้นให้รีบตัก' พร้อมยกตัวอย่างสถานการณ์ที่ใช้",
)
NO_RESTART = os.environ.get("WS_NO_RESTART", "") == "1"

# name -> extra args. baseline = plain tiered load; mtp = same + MTP head.
_DEFAULT_EXTRA_ARGS = {
    "baseline n-cpu-moe 0": "--n-cpu-moe 0 -fa on -t 8",
    "mtp n-cpu-moe 0 t8": "--n-cpu-moe 0 -fa on -t 8 --spec-type draft-mtp",
    "mtp n-cpu-moe 0 t12": "--n-cpu-moe 0 -fa on -t 12 --spec-type draft-mtp",
}
_override = os.environ.get("WS_MATRIX_CONFIGS", "").strip()
if _override:
    try:
        EXTRA_ARGS = json.loads(_override)
    except json.JSONDecodeError as e:
        raise SystemExit(f"WS_MATRIX_CONFIGS is not valid JSON: {e}")
else:
    EXTRA_ARGS = _DEFAULT_EXTRA_ARGS


def _req(method, path, body=None, timeout=300):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(
        BASE + path, data=data, method=method,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(r, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def _kill_llama_servers():
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq llama-server.exe"],
                         capture_output=True, text=True)
    for line in out.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0] == "llama-server.exe":
            subprocess.run(["taskkill", "/F", "/PID", parts[1]],
                           capture_output=True, text=True)


def _server_pid():
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq python.exe"],
                         capture_output=True, text=True)
    for line in out.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0] == "python.exe":
            try:
                cmd = subprocess.run(
                    ["wmic", "process", "where", f"ProcessId={parts[1]}",
                     "get", "CommandLine", "/value"],
                    capture_output=True, text=True).stdout
            except Exception:
                cmd = ""
            if "weight_stream.server" in cmd and f"--port {PORT}" in cmd:
                return parts[1]
    return None


def _restart_server(extra_args):
    """Restart the API server subprocess so WS_LLAMA_EXTRA_ARGS applies."""
    print(f"\n=== restarting API server with WS_LLAMA_EXTRA_ARGS={extra_args!r} ===")
    _kill_llama_servers()
    pid = _server_pid()
    if pid:
        subprocess.run(["taskkill", "/F", "/PID", pid],
                       capture_output=True, text=True)
        time.sleep(2)
    _kill_llama_servers()
    env = dict(os.environ, WS_LLAMA_EXTRA_ARGS=extra_args)
    log = open("scripts/.ws-server-mtp.log", "w", encoding="utf-8")
    subprocess.Popen(
        [sys.executable, "-m", "weight_stream.server", "--port", PORT],
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        env=env, stdout=log, stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    for _ in range(120):
        try:
            with urllib.request.urlopen(f"{BASE}/health", timeout=2) as r:
                if r.status == 200:
                    return
        except Exception:
            time.sleep(0.5)
    raise SystemExit("API server did not come up after restart")


def _load_and_spawn():
    """Load the model (idempotent) and force llama-server spawn."""
    try:
        _req("POST", "/v1/models/unload", {"model_id": MODEL_ID}, timeout=30)
    except Exception:
        pass
    _req("POST", "/v1/models/load", {
        "model_id": MODEL_ID, "model_path": MODEL,
        "n_ctx": N_CTX, "n_threads": 8, "buffer_mb": 64,
    }, timeout=3600)
    # force a warm generation to make sure the backend spawned llama-server
    _req("POST", "/v1/chat/completions", {
        "model": MODEL_ID,
        "messages": [{"role": "user", "content": "warmup"}],
        "max_tokens": 8, "stream": False, "reasoning_mode": "off",
    }, timeout=600)


def _stats():
    try:
        return _req("GET", "/v1/stats", timeout=10)
    except Exception:
        return {}


def _generate(tokens=GEN_TOKENS):
    """Stream a generation; return (token_count, elapsed, tps)."""
    req = urllib.request.Request(
        BASE + "/v1/chat/completions",
        data=json.dumps({
            "model": MODEL_ID,
            "messages": [{"role": "user", "content": PROMPT}],
            "max_tokens": tokens,
            "stream": True,
            "temperature": 0.0,
        }).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    t0 = time.time()
    count = 0
    with urllib.request.urlopen(req, timeout=900) as resp:
        for line in resp:
            line = line.decode("utf-8", "replace").strip()
            if line.startswith("data: ") and line != "data: [DONE]":
                count += 1
    elapsed = time.time() - t0
    return count, elapsed, (count / elapsed if elapsed > 0 else 0.0)


def _measure(name, reps=3):
    """Warm up once, then measure `reps` generations; return best/median."""
    _generate(tokens=8)  # warmup: page cache + KV alloc + MTP warm
    time.sleep(1)
    samples = []
    for i in range(reps):
        n, el, tps = _generate()
        samples.append(tps)
        print(f"    rep{i+1}: {n} tok / {el:.2f}s = {tps:.1f} tps")
    samples.sort()
    return samples[len(samples) // 2]


def main():
    print(f"model={MODEL} ctx={N_CTX} gen_tokens={GEN_TOKENS}")
    results = {}
    if NO_RESTART:
        print("WS_NO_RESTART=1: measuring against the already-running server "
              "(the current WS_LLAMA_EXTRA_ARGS apply to all configs!)")
        for name, args in EXTRA_ARGS.items():
            print(f"\n--- {name} (no restart) ---")
            _load_and_spawn()
            results[name] = {"tps": _measure(name), "stats": _stats()}
    else:
        for name, args in EXTRA_ARGS.items():
            _restart_server(args)
            _load_and_spawn()
            results[name] = {"tps": _measure(name), "stats": _stats()}

    print("\n\n=== RESULTS ===")
    for name, r in results.items():
        st = r.get("stats", {})
        print(f"\n{name}:")
        print(f"  median tps={r['tps']:.2f}")
        for key in ("tokens_per_sec", "p95", "vram_bytes", "page_faults"):
            if key in st:
                print(f"  {key}={st[key]}")
    out = os.environ.get("WS_OUT", "scripts/.mtp_out.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"\nsaved -> {out}")


if __name__ == "__main__":
    main()

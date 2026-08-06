"""Controlled --n-cpu-moe sweep (EXP-008).

For each config in EXTRA_ARGS (a dict name → llama-server extra args):
  1. kill the API server on WS_PORT
  2. restart it with WS_LLAMA_EXTRA_ARGS set
  3. load the model, trigger a generation, read the ACTUAL llama-server
     cmdline and verify the flag is really there (the EXP-007 lesson: a
     stale/mismatched server silently answers on the fixed port)
  4. run the ctx harness (single 2048 ctx) for the measured numbers

Usage: python scripts/measure_ncmoe_matrix.py
Env: WS_PORT, WS_LLAMA_EXTRA_ARGS handled per-config below.
"""
import json
import os
import re
import subprocess
import sys
import time
import urllib.request

PORT = os.environ.get("WS_PORT", "8765")
BASE = f"http://127.0.0.1:{PORT}"
MODEL = os.environ.get(
    "WS_TEST_MODEL",
    "D:/models/Qwen3.6-35B-A3B-GGUF/Qwen3.6-35B-A3B-UD-IQ2_M.gguf",
)
MODEL_ID = os.environ.get("WS_TEST_MODEL_ID", "qwen36a3b")

# name → extra args (the FULL WS_LLAMA_EXTRA_ARGS value for each config).
# NOTE: keep the first entry a --cpu-moe baseline so the same-server
# apples-to-apples comparison is explicit.
EXTRA_ARGS = {
    "cpu-moe (all experts CPU)": "--cpu-moe -fa on",
    "n-cpu-moe 10": "--n-cpu-moe 10 -fa on",
    "n-cpu-moe 20": "--n-cpu-moe 20 -fa on",
    "n-cpu-moe 0 (all experts GPU)": "--n-cpu-moe 0 -fa on",
}


def req(method, path, body=None, timeout=600):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(f"{BASE}{path}", data=data, method=method,
                               headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(r, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def server_pid():
    out = subprocess.run(
        ["netstat", "-ano"], capture_output=True, text=True, timeout=15
    ).stdout
    for line in out.splitlines():
        if f":{PORT}" in line and "LISTENING" in line:
            return line.split()[-1]
    return None


def kill_llama_servers():
    """Kill EVERY llama-server.exe except ollama's (different image name).

    On Windows, taskkill of the API server does NOT kill its llama-server
    child — orphans keep squatting on port 8805 and answer /health with the
    SAME model path (different flags), which defeats _verify_model_path.
    The EXP-008 matrix restarts the server per config, so any leftover
    subprocess must be killed first or the measurement hits the orphan.
    """
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq llama-server.exe"],
                         capture_output=True, text=True, timeout=15).stdout
    pids = []
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0].lower() == "llama-server.exe":
            pids.append(parts[1])
    for p in pids:
        subprocess.run(["taskkill", "/F", "/PID", p],
                       capture_output=True, text=True)
    if pids:
        time.sleep(2)


def restart_server(extra):
    # Kill the API server AND any orphaned llama-server subprocess.
    kill_llama_servers()
    pid = server_pid()
    if pid:
        subprocess.run(["taskkill", "/F", "/PID", pid],
                       capture_output=True, text=True)
        time.sleep(2)
    kill_llama_servers()
    env = dict(os.environ, WS_LLAMA_EXTRA_ARGS=extra)
    log = open("scripts/.ws-server-matrix.log", "w", encoding="utf-8")
    subprocess.Popen(
        [sys.executable, "-m", "weight_stream.server", "--port", PORT],
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        env=env, stdout=log, stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    # Wait for /health.
    for _ in range(40):
        try:
            with urllib.request.urlopen(f"{BASE}/health", timeout=2) as r:
                if r.status == 200:
                    return
        except Exception:
            time.sleep(0.5)
    raise RuntimeError("server did not come up")


def llama_cmdline():
    out = subprocess.run(
        ["wmic", "process", "where", "name='llama-server.exe'",
         "get", "ProcessId,CommandLine"],
        capture_output=True, text=True, timeout=20,
    ).stdout
    for line in out.splitlines():
        if "llama-server.exe" in line:
            return line.strip()
    return ""


def measure_one(extra):
    """Load, trigger spawn, verify cmdline, run the ctx harness once."""
    # Ensure clean: unload if loaded.
    try:
        req("POST", "/v1/models/unload", {"model_id": MODEL_ID}, timeout=30)
    except Exception:
        pass
    req("POST", "/v1/models/load", {
        "model_id": MODEL_ID, "model_path": MODEL,
        "n_ctx": 2048, "n_threads": 8, "buffer_mb": 64,
    }, timeout=900)
    # Trigger lazy spawn + warm.
    req("POST", "/v1/chat/completions", {
        "model": MODEL_ID,
        "messages": [{"role": "user", "content": "warmup"}],
        "max_tokens": 8, "stream": False,
    }, timeout=120)
    time.sleep(1)
    cmd = llama_cmdline()
    # Verify the ACTUAL flags on the spawned server (not just the model).
    expected = [t for t in extra.split() if t.startswith("-")]
    if expected and not all(e in cmd for e in expected):
        raise RuntimeError(
            f"spawned llama-server missing expected flags {expected}:\n{cmd}"
        )
    # Run the ctx harness for the real numbers.
    harness = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "measure_ctx_scaling.py")
    env = dict(os.environ, WS_CTX="2048")
    subprocess.run([sys.executable, harness], cwd=os.getcwd(), env=env,
                   timeout=600, capture_output=True)
    with open("scripts/.ctx_scaling_out.json", encoding="utf-8") as f:
        r = json.load(f)[0]
    try:
        req("POST", "/v1/models/unload", {"model_id": MODEL_ID}, timeout=30)
    except Exception:
        pass
    return cmd, r


def main():
    # EXP-009 clean-room gate: abort when the environment is contaminated
    # (legacy server, orphan llama-server, port squatting). Read-only check
    # BEFORE the matrix restarts anything — the same process blindness that
    # invalidated EXP-005/006 must never gate a sweep again.
    checker = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "check_clean_environment.py")
    p = subprocess.run([sys.executable, checker], capture_output=True, text=True)
    print(p.stdout, end="", flush=True)
    if p.returncode >= 2:
        print("ABORTING: environment check FAILED - fix the findings and re-run.",
              file=sys.stderr)
        return 2

    results = []
    for name, extra in EXTRA_ARGS.items():
        print(f"\n=== {name}: {extra} ===", flush=True)
        restart_server(extra)
        cmd, r = measure_one(extra)
        has_flag = extra.split()[0] in cmd
        print(f"  cmdline has '{extra.split()[0]}': {has_flag}")
        print(f"  tok_s={r['server_tok_s']:.1f}  vram_after_gen={r['vram_after_gen_mib']} MiB"
              f"  p95={r['per_token_ms_p95']} ms")
        results.append({
            "config": name, "extra_args": extra, "flag_in_cmdline": has_flag,
            "server_tok_s": r["server_tok_s"], "raw_tok_s": r["raw_tok_s"],
            "vram_after_gen_mib": r["vram_after_gen_mib"],
            "p95_ms": r["per_token_ms_p95"],
        })
    print("\n\n=== MATRIX ===")
    print(json.dumps(results, indent=2))
    with open("scripts/.ncmoe_matrix_out.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print("saved scripts/.ncmoe_matrix_out.json")


if __name__ == "__main__":
    sys.exit(main())

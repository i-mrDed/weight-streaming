"""EXP-012 harness: config matrix for models BIGGER than RAM (DS V4 Flash).

The DS V4 Flash 0731 file is 103 GB while this machine has 64 GB RAM — so
the OS page cache cannot hold it all and tok/s depends on how much of the
weights stay resident. The EXP-008/011 harnesses measured tok/s only; this
one ALSO records cold vs warm paging per config, because for a >RAM model
"fast on paper" can mean "thrashing the disk every token".

For each config (llama-server extra args):
  1. restart the API server with WS_LLAMA_EXTRA_ARGS set
  2. load the model, trigger a spawn, verify the ACTUAL llama-server
     cmdline has the expected flags (EXP-007 lesson: a stale/orphan server
     silently answers on the fixed port)
  3. generation #1 (cold — fresh load, page cache empty) → read /v1/stats
  4. generation #2 (warm — weights now in OS page cache) → read /v1/stats
  5. record tok/s, VRAM, and paging (faults_per_token, disk_mb_per_token)

Usage: python scripts/measure_dsv4flash.py
Env:  WS_PORT, WS_TEST_MODEL (gguf path), WS_TEST_MODEL_ID,
      WS_MATRIX_CONFIGS (JSON dict name -> extra args; default below),
      WS_NO_RESTART=1 to measure against the ALREADY-RUNNING server
      (quick validation of the measurement path without restarting).
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
    "D:/models/DeepSeek-V4-Flash-0731-GGUF/"
    "DeepSeek-V4-Flash-0731-UD-IQ3_XXS.gguf",
)
MODEL_ID = os.environ.get("WS_TEST_MODEL_ID", "dsv4flash")
N_CTX = int(os.environ.get("WS_CTX", "2048"))
GEN_TOKENS = int(os.environ.get("WS_GEN_TOKENS", "120"))
NO_RESTART = os.environ.get("WS_NO_RESTART", "") == "1"

# name -> extra args (the FULL WS_LLAMA_EXTRA_ARGS value for each config).
# First entry is the --cpu-moe baseline (all experts on CPU) so the
# same-server comparison is explicit. Override via WS_MATRIX_CONFIGS JSON.
_DEFAULT_EXTRA_ARGS = {
    "cpu-moe t8": "--cpu-moe -fa on -t 8",
    "n-cpu-moe 10 t8": "--n-cpu-moe 10 -fa on -t 8",
    "n-cpu-moe 5 t8": "--n-cpu-moe 5 -fa on -t 8",
    "n-cpu-moe 0 t8": "--n-cpu-moe 0 -fa on -t 8",
    "cpu-moe t16": "--cpu-moe -fa on -t 16",
}
_override = os.environ.get("WS_MATRIX_CONFIGS", "").strip()
if _override:
    try:
        EXTRA_ARGS = json.loads(_override)
    except json.JSONDecodeError as e:
        raise SystemExit(f"WS_MATRIX_CONFIGS is not valid JSON: {e}")
else:
    EXTRA_ARGS = _DEFAULT_EXTRA_ARGS


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

    Same rationale as measure_ncmoe_matrix.py: on Windows, taskkill of the
    API server does NOT kill its llama-server child — orphans keep squatting
    on the backend port and answer with the SAME model path (different
    flags), which silently contaminates the measurement.
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
    kill_llama_servers()
    pid = server_pid()
    if pid:
        subprocess.run(["taskkill", "/F", "/PID", pid],
                       capture_output=True, text=True)
        time.sleep(2)
    kill_llama_servers()
    env = dict(os.environ, WS_LLAMA_EXTRA_ARGS=extra)
    log = open("scripts/.ws-server-dsv4flash.log", "w", encoding="utf-8")
    subprocess.Popen(
        [sys.executable, "-m", "weight_stream.server", "--port", PORT],
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        env=env, stdout=log, stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    for _ in range(60):
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


def _read_model_stats():
    """Pull this model's block from /v1/stats — tok/s + paging + VRAM.

    NOTE the response shape differs by query: with ``?model=<id>`` the
    server returns the model's stats dict DIRECTLY under ``models``
    (keys: generation/model/gpu) instead of ``{model_id: stats}`` — the
    first harness run read ``models[model_id]`` and got all-None.
    """
    d = req("GET", f"/v1/stats?model={MODEL_ID}", timeout=30)
    models = d.get("models", {}) or {}
    m = models.get(MODEL_ID, models)  # keyed shape OR direct shape
    gen = m.get("generation") or {}
    gpu = m.get("gpu") or {}
    paging = gen.get("paging") or {}
    return {
        "tok_s": gen.get("tokens_per_sec"),
        "elapsed_s": gen.get("elapsed"),
        "token_count": gen.get("token_count"),
        "faults_per_token": paging.get("faults_per_token"),
        "fault_mb_per_token": paging.get("fault_mb_per_token"),
        "disk_mb_per_token": paging.get("disk_mb_per_token"),
        "n_gpu_layers": gpu.get("n_gpu_layers"),
        "used_vram_mb": gpu.get("used_vram_mb"),
        "total_vram_mb": gpu.get("total_vram_mb"),
    }


def _generate(prompt, tokens):
    req("POST", "/v1/chat/completions", {
        "model": MODEL_ID,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": tokens, "stream": False, "reasoning_mode": "off",
    }, timeout=1800)
    time.sleep(1)
    return _read_model_stats()


def measure_one(extra):
    """Load, verify cmdline, generate cold + warm, return both stat blocks."""
    try:
        req("POST", "/v1/models/unload", {"model_id": MODEL_ID}, timeout=30)
    except Exception:
        pass
    req("POST", "/v1/models/load", {
        "model_id": MODEL_ID, "model_path": MODEL,
        "n_ctx": N_CTX, "n_threads": 8, "buffer_mb": 64,
    }, timeout=3600)
    # Trigger lazy spawn + warm the model weights once (this populates the
    # page cache — the cold run below measures the FIRST real workload gen).
    req("POST", "/v1/chat/completions", {
        "model": MODEL_ID,
        "messages": [{"role": "user", "content": "warmup"}],
        "max_tokens": 8, "stream": False, "reasoning_mode": "off",
    }, timeout=600)
    time.sleep(1)
    cmd = llama_cmdline()
    cmd_toks = cmd.split()
    expected = [t for t in extra.split() if t.startswith("-")]
    if expected and not all(e in cmd_toks for e in expected):
        raise RuntimeError(
            f"spawned llama-server missing expected flags {expected}:\n{cmd}"
        )
    # Cold: page cache has only the warmup's touch — the real weights are
    # being faulted in WHILE generating, so this is the disk-bound number.
    cold = _generate("Summarize the plot of Dune in 3 sentences.", GEN_TOKENS)
    # Warm: weights now resident in the OS page cache (if they fit — for a
    # 103 GB file on 64 GB RAM the cache can only hold ~60 GB, so this is
    # the honest "best case on THIS machine" number, not a fake full-RAM one).
    warm = _generate("What are the first 10 digits of pi, reversed?", GEN_TOKENS)
    try:
        req("POST", "/v1/models/unload", {"model_id": MODEL_ID}, timeout=30)
    except Exception:
        pass
    return cmd, cold, warm


def main():
    if not NO_RESTART:
        checker = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "check_clean_environment.py")
        p = subprocess.run([sys.executable, checker],
                           capture_output=True, text=True)
        print(p.stdout, end="", flush=True)
        if p.returncode >= 2:
            print("ABORTING: environment check FAILED - fix and re-run.",
                  file=sys.stderr)
            return 2

    results = []
    for name, extra in EXTRA_ARGS.items():
        print(f"\n=== {name}: {extra} ===", flush=True)
        if NO_RESTART:
            print("  (WS_NO_RESTART=1 — measuring against running server)")
        else:
            restart_server(extra)
        cmd, cold, warm = measure_one(extra)
        has_flag = extra.split()[0] in cmd.split()
        print(f"  cmdline has '{extra.split()[0]}': {has_flag}")
        print(f"  cold: tok_s={cold['tok_s']}  "
              f"faults/tok={cold['faults_per_token']}  "
              f"disk MB/tok={cold['disk_mb_per_token']}")
        print(f"  warm: tok_s={warm['tok_s']}  "
              f"faults/tok={warm['faults_per_token']}  "
              f"disk MB/tok={warm['disk_mb_per_token']}"
              f"  vram={warm['used_vram_mb']} MiB")
        results.append({
            "config": name, "extra_args": extra, "flag_in_cmdline": has_flag,
            "cold": cold, "warm": warm,
        })
    print("\n\n=== MATRIX ===")
    print(json.dumps(results, indent=2))
    with open("scripts/.dsv4flash_matrix_out.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print("saved scripts/.dsv4flash_matrix_out.json")


if __name__ == "__main__":
    sys.exit(main())

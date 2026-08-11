"""EXP-016 harness: layer-group expert tiering census on the GPU backend.

llama.cpp exposes per-LAYER (not per-expert) placement: expert tensors are
fused per layer (`blk.N.ffn_gate_exps.weight` packs all 256 experts), and
`--n-cpu-moe N` keeps the first N layers' MoE on CPU. So the actionable
question for auto tiering is: WHICH layer groups give the most tok/s per
MB of VRAM when pinned to the GPU?

Method (same skeleton as EXP-008/011/012/015 harnesses):
  1. restart the API server with WS_LLAMA_EXTRA_ARGS per config
  2. load the model, spawn, verify cmdline flags
  3. warmup gen + 3 x 300-token Thai idiom generations -> median tps
  4. read VRAM used after load (nvidia-smi) per config
  5. report tok/s per VRAM for each layer group

Configs (all with -ngl 99 -fa on -t 8):
  - exp_cpu:     all conditional experts on CPU (lower bound)
  - gpu_0_9:     experts of layers  0-9 on GPU, 10-39 CPU
  - gpu_10_19:   experts of layers 10-19 on GPU, others CPU
  - gpu_20_29:   experts of layers 20-29 on GPU, others CPU
  - gpu_30_39:   experts of layers 30-39 on GPU, others CPU
  - exp_gpu:     all experts on GPU (upper bound, if it fits)

Usage: python scripts/measure_expert_census.py
Env:  WS_PORT, WS_TEST_MODEL, WS_MATRIX_CONFIGS, WS_OUT, WS_NO_RESTART
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
# ~ expands to THIS machine's home (hermetic default — no dev-machine
# path baked in); override with WS_TEST_MODEL for any other model.
MODEL = os.path.expanduser(os.environ.get(
    "WS_TEST_MODEL",
    "~/models/Qwen3.6-35B-A3B-GGUF/Qwen3.6-35B-A3B-UD-IQ2_M.gguf",
))
MODEL_ID = os.environ.get("WS_TEST_MODEL_ID", "qwen36-census")
N_CTX = int(os.environ.get("WS_CTX", "2048"))
GEN_TOKENS = int(os.environ.get("WS_GEN_TOKENS", "300"))
PROMPT = os.environ.get(
    "WS_PROMPT",
    "อธิบายความหมายของสำนวนไทย 'น้ำขึ้นให้รีบตัก' พร้อมยกตัวอย่างสถานการณ์ที่ใช้",
)
NO_RESTART = os.environ.get("WS_NO_RESTART", "") == "1"

# Layer -> which experts stay on GPU. Each config overrides the OTHERS to
# CPU, leaving exactly one 10-layer band on the GPU.
_EXPS_RE = r"blk\.([0-9]+)\.ffn_.*_exps.*"
# Layer band -> regex of blk.N prefix for N in [lo, hi)
def _band_re(lo, hi):
    nums = "|".join(str(n) for n in range(lo, hi))
    return rf"blk\.({nums})\.ffn_.*_exps.*"

# Order matters: LAST matching override wins. Band CUDA0 must come BEFORE
# the catch-all CPU rule (verified: VRAM 5341 MiB vs 2898 MiB for band 0-9).
_DEFAULT_EXTRA_ARGS = {
    "exp_cpu":   f"-ngl 99 -fa on -t 8 -ot \"{_EXPS_RE}=CPU\"",
    "gpu_0_9":   (f"-ngl 99 -fa on -t 8 "
                  f"-ot \"{_band_re(0, 10)}=CUDA0\" "
                  f"-ot \"{_EXPS_RE}=CPU\""),
    "gpu_10_19": (f"-ngl 99 -fa on -t 8 "
                  f"-ot \"{_band_re(10, 20)}=CUDA0\" "
                  f"-ot \"{_EXPS_RE}=CPU\""),
    "gpu_20_29": (f"-ngl 99 -fa on -t 8 "
                  f"-ot \"{_band_re(20, 30)}=CUDA0\" "
                  f"-ot \"{_EXPS_RE}=CPU\""),
    "gpu_30_39": (f"-ngl 99 -fa on -t 8 "
                  f"-ot \"{_band_re(30, 40)}=CUDA0\" "
                  f"-ot \"{_EXPS_RE}=CPU\""),
    "exp_gpu":   "-ngl 99 -fa on -t 8",
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
    print(f"\n=== restarting API server: {extra_args} ===")
    _kill_llama_servers()
    pid = _server_pid()
    if pid:
        subprocess.run(["taskkill", "/F", "/PID", pid],
                       capture_output=True, text=True)
        time.sleep(2)
    _kill_llama_servers()
    env = dict(os.environ, WS_LLAMA_EXTRA_ARGS=extra_args)
    log = open("scripts/.ws-server-census.log", "w", encoding="utf-8")
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
    try:
        _req("POST", "/v1/models/unload", {"model_id": MODEL_ID}, timeout=30)
    except Exception:
        pass
    _req("POST", "/v1/models/load", {
        "model_id": MODEL_ID, "model_path": MODEL,
        "n_ctx": N_CTX, "n_threads": 8, "buffer_mb": 64,
    }, timeout=3600)
    _req("POST", "/v1/chat/completions", {
        "model": MODEL_ID,
        "messages": [{"role": "user", "content": "warmup"}],
        "max_tokens": 8, "stream": False, "reasoning_mode": "off",
    }, timeout=600)


def _generate(tokens=GEN_TOKENS):
    req = urllib.request.Request(
        BASE + "/v1/chat/completions",
        data=json.dumps({
            "model": MODEL_ID,
            "messages": [{"role": "user", "content": PROMPT}],
            "max_tokens": tokens, "stream": True, "temperature": 0.0,
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
    _generate(tokens=8)
    time.sleep(1)
    samples = []
    for i in range(reps):
        n, el, tps = _generate()
        samples.append(tps)
        print(f"    rep{i+1}: {n} tok / {el:.2f}s = {tps:.1f} tps")
    samples.sort()
    return samples[len(samples) // 2]


def _vram_mb():
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=15).stdout.strip()
        m = re.search(r"(\d+)", out)
        return int(m.group(1)) if m else None
    except Exception:
        return None


def main():
    print(f"model={MODEL} ctx={N_CTX} gen_tokens={GEN_TOKENS}")
    results = {}
    if NO_RESTART:
        print("WS_NO_RESTART=1: measuring against already-running server!")
        for name, args in EXTRA_ARGS.items():
            print(f"\n--- {name} (no restart) ---")
            _load_and_spawn()
            results[name] = {"tps": _measure(name), "vram_mb": _vram_mb()}
    else:
        for name, args in EXTRA_ARGS.items():
            _restart_server(args)
            _load_and_spawn()
            time.sleep(2)
            vram = _vram_mb()
            print(f"    VRAM after load: {vram} MiB")
            results[name] = {"tps": _measure(name), "vram_mb": vram}

    print("\n\n=== RESULTS ===")
    for name, r in results.items():
        v = r.get("vram_mb") or 0
        t = r.get("tps") or 0
        print(f"{name:12s}  tps={t:6.2f}  vram={v:6d} MiB  "
              f"tps/GB={(t / (v / 1024)) if v else 0:.3f}")
    out = os.environ.get("WS_OUT", "scripts/.expert_census_out.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"\nsaved -> {out}")


if __name__ == "__main__":
    main()

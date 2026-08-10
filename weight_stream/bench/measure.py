"""Clean-room measurement — the honest-telemetry core of the harness.

Port of the EXP-008/011/012 harness discipline into a reusable module so
ANY model can be measured reproducibly through the REAL engine (llama-server
via the API server), never a simulation:

1. **Clean room** — kill every stale llama-server (Windows orphans squat on
   the backend port and answer with the same model path but different flags,
   silently contaminating measurements) and restart the API server with the
   exact extra args under test.
2. **Verify, don't trust** — after load, inspect the ACTUAL spawned
   llama-server cmdline: expected flags present AND value-aware checks for
   -t / -fa / -ctk / -ctv (a silent override would invalidate the sweep).
3. **Cold + warm** — generation #1 faults the weights in from disk (the
   honest "first real workload" number); generation #2 runs with weights in
   the OS page cache (the honest "best case on THIS machine" number).
4. **Record paging** — faults/token and disk MB/token from /v1/stats, so
   "fast on paper" can't hide "thrashing the disk every token".
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any, Optional

# Flags whose VALUE on the spawned process must match the requested config.
# (llama.cpp keeps the final occurrence; the load request always emits
# `-t 8` BEFORE extra args are appended.)
VALUE_CHECKS = ("-t", "-fa", "-ctk", "-ctv")


def req(base: str, method: str, path: str, body: Optional[dict] = None,
        timeout: int = 600) -> Any:
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(
        f"{base}{path}", data=data, method=method,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(r, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


# ── pure helpers (unit-testable offline) ───────────────────────────────

def normalize_stats(raw: dict, model_id: str) -> dict[str, Any]:
    """Flatten the (shape-varying) /v1/stats response into one dict.

    NOTE the response shape differs by query: with ``?model=<id>`` the
    server returns the model's stats dict DIRECTLY under ``models`` (keys:
    generation/model/gpu) instead of ``{model_id: stats}``.
    """
    models = raw.get("models", {}) or {}
    m = models.get(model_id, models)  # keyed shape OR direct shape
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


def _flag_value(toks: list[str], flag: str) -> Optional[str]:
    # LAST occurrence wins — llama.cpp keeps the final value.
    idx = [i for i, t in enumerate(toks) if t == flag]
    if not idx:
        return None
    i = idx[-1]
    return toks[i + 1] if i + 1 < len(toks) else None


def verify_extra_args(cmd: str, extra_args: str) -> list[str]:
    """Return the list of problems between requested extra args and the
    ACTUAL spawned llama-server cmdline. Empty list == verified OK.

    Covers both presence (a flag the sweep depends on must exist) and
    value-awareness for the flags in VALUE_CHECKS (presence-only would let
    a silent override, e.g. -t 16 dropped back to 8, invalidate the sweep).
    """
    problems: list[str] = []
    cmd_toks = cmd.split()
    extra_toks = extra_args.split()
    expected = [t for t in extra_toks if t.startswith("-")]
    missing = [e for e in expected if e not in cmd_toks]
    if missing:
        problems.append(f"missing flags {missing}")
    for flag in VALUE_CHECKS:
        if flag in extra_toks:
            want = _flag_value(extra_toks, flag)
            got = _flag_value(cmd_toks, flag)
            if got != want:
                problems.append(f"{flag}={got}, expected {flag}={want}")
    return problems


# ── Windows process control (the clean room) ───────────────────────────

def _win() -> bool:
    return os.name == "nt"


def server_pid(port: int) -> Optional[str]:
    if not _win():
        return None
    out = subprocess.run(["netstat", "-ano"], capture_output=True,
                         text=True, timeout=15).stdout
    for line in out.splitlines():
        if f":{port}" in line and "LISTENING" in line:
            return line.split()[-1]
    return None


def kill_llama_servers() -> None:
    """Kill EVERY llama-server.exe (not just ours). On Windows, taskkill of
    the API server does NOT kill its llama-server child — orphans keep
    squatting on the backend port and answer with the SAME model path
    (different flags), which silently contaminates measurement."""
    if not _win():
        return
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


def restart_server(port: int, extra_args: str, project_root: Path,
                   log_path: Optional[Path] = None) -> None:
    """Kill stale servers and start a fresh API server with WS_LLAMA_EXTRA_ARGS
    set — the clean room for a config sweep."""
    kill_llama_servers()
    pid = server_pid(port)
    if pid:
        subprocess.run(["taskkill", "/F", "/PID", pid],
                       capture_output=True, text=True)
        time.sleep(2)
    kill_llama_servers()
    env = dict(os.environ, WS_LLAMA_EXTRA_ARGS=extra_args)
    log = open(log_path or (project_root / "scripts" / ".ws-bench-server.log"),
               "w", encoding="utf-8")
    subprocess.Popen(
        [sys.executable, "-m", "weight_stream.server", "--port", str(port)],
        cwd=str(project_root), env=env, stdout=log, stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NO_WINDOW if _win() else 0,
    )
    base = f"http://127.0.0.1:{port}"
    for _ in range(60):
        try:
            with urllib.request.urlopen(f"{base}/health", timeout=2) as r:
                if r.status == 200:
                    return
        except Exception:
            time.sleep(0.5)
    raise RuntimeError("server did not come up")


def llama_cmdline() -> str:
    if not _win():
        return ""
    out = subprocess.run(
        ["wmic", "process", "where", "name='llama-server.exe'",
         "get", "ProcessId,CommandLine"],
        capture_output=True, text=True, timeout=20,
    ).stdout
    for line in out.splitlines():
        if "llama-server.exe" in line:
            return line.strip()
    return ""


# ── measurement ────────────────────────────────────────────────────────

def read_model_stats(base: str, model_id: str) -> dict[str, Any]:
    return normalize_stats(
        req(base, "GET", f"/v1/stats?model={model_id}", timeout=30), model_id)


def _generate(base: str, model_id: str, prompt: str, tokens: int,
              timeout: int = 1800) -> dict[str, Any]:
    req(base, "POST", "/v1/chat/completions", {
        "model": model_id,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": tokens, "stream": False, "reasoning_mode": "off",
    }, timeout=timeout)
    time.sleep(1)
    return read_model_stats(base, model_id)


def measure_model(
    base: str,
    model_path: str,
    model_id: str,
    *,
    n_ctx: int = 2048,
    n_threads: int = 8,
    buffer_mb: int = 64,
    gen_tokens: int = 120,
    extra_args: str = "",
    verify: bool = True,
    load_timeout: int = 3600,
) -> dict[str, Any]:
    """Load a model on the (already-restarted) server and measure cold + warm.

    Returns {cmd, cold, warm} where cold/warm are the flattened /v1/stats
    blocks (see read_model_stats). Raises RuntimeError if the spawned
    llama-server cmdline does not match the requested extra args.
    """
    try:
        req(base, "POST", "/v1/models/unload", {"model_id": model_id},
            timeout=30)
    except Exception:
        pass
    req(base, "POST", "/v1/models/load", {
        "model_id": model_id, "model_path": model_path,
        "n_ctx": n_ctx, "n_threads": n_threads, "buffer_mb": buffer_mb,
    }, timeout=load_timeout)
    # Trigger lazy spawn + warm the weights once (populates the page cache;
    # the cold run below measures the FIRST real workload generation).
    req(base, "POST", "/v1/chat/completions", {
        "model": model_id,
        "messages": [{"role": "user", "content": "warmup"}],
        "max_tokens": 8, "stream": False, "reasoning_mode": "off",
    }, timeout=600)
    time.sleep(1)

    cmd = llama_cmdline()
    if verify and extra_args:
        problems = verify_extra_args(cmd, extra_args)
        if problems:
            raise RuntimeError(
                f"spawned llama-server does not match requested config "
                f"({'; '.join(problems)}):\n{cmd}"
            )

    # Cold: page cache has only the warmup's touch — weights are faulted in
    # WHILE generating, so this is the disk-bound number.
    cold = _generate(base, model_id,
                     "Summarize the plot of Dune in 3 sentences.", gen_tokens)
    # Warm: weights now resident in the OS page cache (if they fit — honest
    # "best case on THIS machine", not a fake full-RAM number).
    warm = _generate(base, model_id,
                     "What are the first 10 digits of pi, reversed?", gen_tokens)
    try:
        req(base, "POST", "/v1/models/unload", {"model_id": model_id},
            timeout=30)
    except Exception:
        pass
    return {"cmd": cmd, "cold": cold, "warm": warm}


def run_matrix(
    base: str,
    model_path: str,
    model_id: str,
    configs: dict[str, str],
    project_root: Path,
    *,
    port: int = 8765,
    n_ctx: int = 2048,
    n_threads: int = 8,
    buffer_mb: int = 64,
    gen_tokens: int = 120,
    restart: bool = True,
    verify: bool = True,
) -> list[dict[str, Any]]:
    """Measure every config (name -> llama-server extra args).

    Each config runs in a clean room (fresh API server with its own
    WS_LLAMA_EXTRA_ARGS). A failing config is recorded honestly and does NOT
    wipe the rest of the matrix (e.g. --n-cpu-moe 0 on a >VRAM model → OOM).
    """
    results: list[dict[str, Any]] = []
    for name, extra in configs.items():
        if restart:
            try:
                restart_server(port, extra, project_root)
            except Exception as e:
                results.append({
                    "config": name, "extra_args": extra,
                    "flag_in_cmdline": False, "error": f"restart failed: {e}",
                })
                continue
        try:
            measured = measure_model(
                base, model_path, model_id, n_ctx=n_ctx, n_threads=n_threads,
                buffer_mb=buffer_mb, gen_tokens=gen_tokens,
                extra_args=extra, verify=verify,
            )
        except Exception as e:
            results.append({
                "config": name, "extra_args": extra,
                "flag_in_cmdline": False, "error": str(e),
            })
            continue
        results.append({
            "config": name, "extra_args": extra,
            "flag_in_cmdline": bool(measured["cmd"] and extra.split()[0] in measured["cmd"]),
            "cold": measured["cold"], "warm": measured["warm"],
        })
    return results

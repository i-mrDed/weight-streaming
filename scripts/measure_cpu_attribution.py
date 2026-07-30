"""
CPU attribution measurement for weight-streaming (verification artifact).

Measures, with Win32 counters (GetSystemTimes / GetProcessTimes via ctypes):
  - total system CPU busy %
  - our server process CPU % (share of the whole machine)
  - extra PIDs (e.g. ollama) CPU %
in three phases:
  A) idle baseline
  B) while the server streams a /v1/generate request
  C) cool-down baseline

Usage:
    python scripts/measure_cpu_attribution.py --pid 54980 --extra-pids 7344,2284
Saves: docs/verification/cpu_attribution_<date>.json
"""
from __future__ import annotations

import argparse
import ctypes
import json
import os
import sys
import threading
import time
import urllib.request
from ctypes import wintypes
from datetime import datetime, timezone

if sys.platform != "win32":
    print("This script currently supports Windows only (GetSystemTimes).")
    raise SystemExit(2)

k32 = ctypes.WinDLL("kernel32", use_last_error=True)

k32.GetSystemTimes.argtypes = [
    ctypes.POINTER(ctypes.c_ulonglong),  # idle
    ctypes.POINTER(ctypes.c_ulonglong),  # kernel
    ctypes.POINTER(ctypes.c_ulonglong),  # user
]
k32.GetSystemTimes.restype = wintypes.BOOL

k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
k32.OpenProcess.restype = wintypes.HANDLE
k32.CloseHandle.argtypes = [wintypes.HANDLE]
k32.CloseHandle.restype = wintypes.BOOL

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

k32.GetProcessTimes.argtypes = [
    wintypes.HANDLE,
    ctypes.POINTER(ctypes.c_ulonglong),  # creation
    ctypes.POINTER(ctypes.c_ulonglong),  # exit
    ctypes.POINTER(ctypes.c_ulonglong),  # kernel
    ctypes.POINTER(ctypes.c_ulonglong),  # user
]
k32.GetProcessTimes.restype = wintypes.BOOL


def _sys_times() -> tuple[int, int, int]:
    idle, kernel, user = (ctypes.c_ulonglong() for _ in range(3))
    if not k32.GetSystemTimes(idle, kernel, user):
        raise OSError("GetSystemTimes failed")
    return idle.value, kernel.value, user.value


def _proc_times(handle: int) -> tuple[int, int]:
    creation, exit_, kernel, user = (ctypes.c_ulonglong() for _ in range(4))
    if not k32.GetProcessTimes(handle, creation, exit_, kernel, user):
        raise OSError("GetProcessTimes failed")
    return kernel.value, user.value


def _open(pid: int) -> int:
    h = k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        raise OSError(f"OpenProcess({pid}) failed, error {ctypes.get_last_error()}")
    return h


def sample_phase(
    duration: float, handles: dict[int, int], interval: float = 0.5
) -> dict:
    """Sample CPU shares over `duration` seconds; returns averaged %."""
    s_idle0, s_kern0, s_user0 = _sys_times()
    p0 = {pid: _proc_times(h) for pid, h in handles.items()}
    time.sleep(duration)
    s_idle1, s_kern1, s_user1 = _sys_times()
    p1 = {pid: _proc_times(h) for pid, h in handles.items()}

    d_kern = s_kern1 - s_kern0
    d_user = s_user1 - s_user0
    d_idle = s_idle1 - s_idle0
    total = d_kern + d_user  # kernel includes idle time
    busy_pct = 100.0 * (total - d_idle) / total if total else 0.0

    per_pid = {}
    for pid in handles:
        dk = p1[pid][0] - p0[pid][0]
        du = p1[pid][1] - p0[pid][1]
        per_pid[pid] = round(100.0 * (dk + du) / total, 2) if total else 0.0

    return {"system_busy_pct": round(busy_pct, 2), "procs_pct": per_pid}


def drive_generation(
    port: int, model: str, prompt: str, max_tokens: int, done: threading.Event
):
    """POST /v1/generate (stream) and consume it fully."""
    url = f"http://localhost:{port}/v1/generate"
    body = json.dumps(
        {"model": model, "prompt": prompt, "max_tokens": max_tokens, "stream": True}
    ).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"}
    )
    tokens = 0
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            for raw in resp:
                line = raw.decode("utf-8", "replace").strip()
                if not line.startswith("data:"):
                    continue
                try:
                    ev = json.loads(line[5:].strip())
                except json.JSONDecodeError:
                    continue
                if ev.get("done"):
                    break
                if "token" in ev:
                    tokens += 1
    except Exception as e:
        print(f"  generation error: {e}")
    finally:
        done.set()
    elapsed = time.time() - t0
    print(
        f"  generation: {tokens} tokens in {elapsed:.1f}s "
        f"({tokens / elapsed:.1f} tok/s)"
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pid", type=int, required=True, help="server python PID")
    ap.add_argument("--extra-pids", default="", help="comma-separated extra PIDs")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--prompt", default="Count from 1 to 30, one number per line.")
    ap.add_argument("--max-tokens", type=int, default=80)
    args = ap.parse_args()

    pids = [args.pid] + [int(x) for x in args.extra_pids.split(",") if x.strip()]
    handles: dict[int, int] = {}
    for pid in pids:
        try:
            handles[pid] = _open(pid)
        except OSError as e:
            print(f"  cannot open PID {pid}: {e}")

    print(f"PIDs: server={args.pid} extra={[p for p in pids if p != args.pid]}")
    print(f"logical CPUs: {os.cpu_count()}")

    print("[A] idle baseline (4s)...")
    phase_a = sample_phase(4.0, handles)
    print(f"    system busy {phase_a['system_busy_pct']}% | per-pid {phase_a['procs_pct']}")

    # Discover the loaded model id from the running server.
    try:
        with urllib.request.urlopen(
            f"http://localhost:{args.port}/v1/models", timeout=5
        ) as resp:
            models = json.load(resp)
        model_id = models[0]["id"] if models else "default"
    except Exception as e:
        print(f"  /v1/models unavailable ({e}); using id 'default'")
        model_id = "default"

    print(f"[B] during /v1/generate (model={model_id}, max_tokens={args.max_tokens})...")
    done = threading.Event()
    gen_thread = threading.Thread(
        target=drive_generation,
        args=(args.port, model_id, args.prompt, args.max_tokens, done),
        daemon=True,
    )
    gen_thread.start()
    phase_b = sample_phase(10.0, handles)
    done.wait(timeout=120)
    gen_thread.join(timeout=5)
    print(f"    system busy {phase_b['system_busy_pct']}% | per-pid {phase_b['procs_pct']}")

    print("[C] cool-down (3s)...")
    phase_c = sample_phase(3.0, handles)
    print(f"    system busy {phase_c['system_busy_pct']}% | per-pid {phase_c['procs_pct']}")

    for h in handles.values():
        k32.CloseHandle(h)

    result = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "model_id": model_id,
        "machine": {
            "logical_cpus": os.cpu_count(),
            "processor": __import__("platform").processor(),
        },
        "pids": {"server": args.pid,
                 "extra": [p for p in pids if p != args.pid]},
        "idle": phase_a,
        "generating": phase_b,
        "cooldown": phase_c,
    }
    out_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "docs", "verification",
    )
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "cpu_attribution_2026-07-30.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    print(f"\nsaved: {out_path}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()

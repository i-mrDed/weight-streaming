#!/usr/bin/env python3
"""Clean-environment gate for benchmark runs (EXP-009+).

WHY: EXP-005/006 were invalidated by processes nobody noticed — an old
`weight_stream.server` on :8804 that had spawned a llama-server onto OUR
:8805, plus an even older Jan llama-server answering /health for days.
Every benchmark since (EXP-007/008) had to hand-check the same things.
This script makes that check one command, and the measure harnesses call
it automatically before starting.

Read-only: it NEVER kills anything. Run it before a measurement session
(or let measure_*.py call it) and act on the verdict.

Usage:
    python scripts/check_clean_environment.py            # normal
    python scripts/check_clean_environment.py --strict   # any warning → fail

Exit codes:
    0  CLEAN — safe to measure
    1  WARN  — informational findings (continue if you accept them)
    2  FAIL  — contamination risk: do NOT measure until resolved
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import urllib.request

API_PORT = int(os.environ.get("WS_PORT", "8765"))
BACKEND_PORT = 8805
LEGACY_PORT = 8804
# Dedupe: when WS_PORT happens to be the legacy port, that port is checked
# once (as the API port) instead of twice with a spurious legacy WARN.
WATCH = tuple(dict.fromkeys((API_PORT, LEGACY_PORT, BACKEND_PORT)))
DATA_HISTORY = os.path.join("data", "usage_history.jsonl")


def _run(cmd: list[str]) -> str:
    try:
        p = subprocess.run(
            cmd, capture_output=True, text=True, timeout=20,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        return p.stdout or ""
    except Exception:
        return ""


# ── process discovery ───────────────────────────────────────────────
def _ws_servers() -> list[dict]:
    """Every python process running `-m weight_stream.server`.

    wmic output columns are alphabetical (NOT request order), so rows are
    parsed from the END: last token = PID, second-to-last = CreationDate,
    the rest = CommandLine (which may contain spaces).
    """
    out = []
    if os.name == "nt":
        raw = _run(["wmic", "process", "where", "name='python.exe'",
                    "get", "ProcessId,CreationDate,CommandLine"])
        for line in raw.splitlines():
            line = line.strip()
            if (not line or line.startswith("CommandLine")
                    or "weight_stream" not in line):
                continue
            toks = line.split()
            if len(toks) < 3:
                continue
            out.append({"pid": toks[-1], "created": toks[-2],
                        "cmd": " ".join(toks[:-2])})
    else:
        raw = _run(["ps", "-eo", "pid,lstart,args"])
        for line in raw.splitlines():
            if "weight_stream" not in line or "check_clean_environment" in line:
                continue
            parts = line.split(None, 5)
            if len(parts) >= 6:
                out.append({"pid": parts[0], "created": " ".join(parts[1:5]),
                            "cmd": parts[5]})
    return out


def _llama_servers() -> list[dict]:
    """Every llama-server.exe running (any of them = contamination risk)."""
    out = []
    if os.name == "nt":
        raw = _run(["wmic", "process", "where", "name='llama-server.exe'",
                    "get", "ProcessId,ParentProcessId,CreationDate,CommandLine"])
        for line in raw.splitlines():
            line = line.strip()
            if not line or line.startswith("CommandLine"):
                continue
            toks = line.split()
            if len(toks) < 4:
                continue
            out.append({"pid": toks[-1], "ppid": toks[-2], "created": toks[-3],
                        "cmd": " ".join(toks[:-3])})
    else:
        raw = _run(["ps", "-eo", "pid,ppid,lstart,args"])
        for line in raw.splitlines():
            if "llama-server" not in line or "check_clean_environment" in line:
                continue
            parts = line.split(None, 5)
            if len(parts) >= 6:
                out.append({"pid": parts[0], "ppid": parts[1],
                            "created": " ".join(parts[2:5]), "cmd": parts[5]})
    return out


def _listeners() -> dict[int, str]:
    """{port: pid} of TCP LISTENING sockets."""
    result: dict[int, str] = {}
    if os.name == "nt":
        raw = _run(["netstat", "-ano", "-p", "tcp"])
        for line in raw.splitlines():
            parts = line.split()
            if len(parts) >= 5 and parts[0] == "TCP" and parts[3] == "LISTENING":
                port = parts[1].rsplit(":", 1)[-1]
                if port.isdigit() and parts[-1].isdigit():
                    result[int(port)] = parts[-1]
    else:
        raw = _run(["netstat", "-tlnp"])
        for line in raw.splitlines():
            m = re.match(
                r"\s*tcp\s+\d+\s+\d+\s+(\S+):(\d+)\s+\S+\s+LISTEN\s+(\S+)", line)
            if m:
                result[int(m.group(2))] = m.group(3)
    return result


def _server_port(cmd: str) -> int:
    m = re.search(r"--port\s+(\d+)", cmd)
    return int(m.group(1)) if m else 8765


def _vram() -> tuple[int | None, int | None]:
    out = _run(["nvidia-smi", "--query-gpu=memory.used,memory.total",
                "--format=csv,noheader"])
    for line in out.splitlines():
        m = re.match(r"\s*([\d.]+)\s*MiB,\s*([\d.]+)\s*MiB", line)
        if m:
            return int(float(m.group(1))), int(float(m.group(2)))
    return None, None


def _http_json(url: str, timeout: int = 3):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8", errors="replace"))
    except Exception:
        return None


def _jan_has_llama_server() -> bool:
    """True when a real llama-server executable exists in Jan's backends.

    Mirrors the backend's ``_find_llama_server()`` (recursive scan for the
    exe) instead of trusting the backends dir to exist — the dir can be
    present with only CUDA support libs and no server binary.
    """
    jan = os.path.join(os.environ.get("APPDATA", ""),
                       "Jan", "data", "llamacpp", "backends")
    if not os.path.isdir(jan):
        return False
    for base, _, files in os.walk(jan):
        for f in files:
            if f in ("llama-server.exe", "llama-server"):
                return True
    return False


def _usage_tail(n: int = 3):
    rows = []
    try:
        with open(DATA_HISTORY, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        rows.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
    except OSError:
        return None, []
    return len(rows), rows[-n:]


def _fmt_ts(created: str) -> str:
    """wmic CreationDate '20260806191801.488913+420' → '2026-08-06 19:18:01'."""
    m = re.match(r"(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})", created or "")
    if m:
        return (f"{m.group(1)}-{m.group(2)}-{m.group(3)} "
                f"{m.group(4)}:{m.group(5)}:{m.group(6)}")
    return created or "?"


def main() -> int:
    strict = "--strict" in sys.argv
    problems: list[str] = []
    warnings: list[str] = []
    notes: list[str] = []

    print("=" * 62)
    print("CLEAN-ROOM ENVIRONMENT CHECK (EXP-009)")
    print("=" * 62)

    # 1. weight_stream.server python processes
    servers = _ws_servers()
    api_owner = None
    for s in servers:
        port = _server_port(s["cmd"])
        notes.append(f"server: PID {s['pid']} port {port} "
                     f"(started {_fmt_ts(s['created'])})")
        if port == API_PORT:
            api_owner = s["pid"]
        else:
            problems.append(
                f"weight_stream.server on port {port} (PID {s['pid']}, started "
                f"{_fmt_ts(s['created'])}) - a legacy instance like the :8804 "
                f"server from EXP-005/006 that spawned onto :{BACKEND_PORT}. "
                "Kill it before measuring."
            )
    if not servers:
        warnings.append(f"no weight_stream.server running on :{API_PORT} - "
                        "start one first (the n-cpu-moe matrix restarts its own)")
    elif len(servers) > 1:
        warnings.append(f"{len(servers)} weight_stream.server instances running "
                        "- confirm only the intended one")

    # 2. llama-server processes (any → contamination risk)
    for l in _llama_servers():
        model = ""
        if " -m " in l["cmd"]:
            model = " -m " + l["cmd"].split(" -m ")[-1].split(" --")[0]
        problems.append(
            f"llama-server.exe running (PID {l['pid']}, ppid {l['ppid']}, "
            f"            started {_fmt_ts(l['created'])}){model} - a benchmark must own "
            "every spawn; kill it (an orphan from a force-killed parent is "
            "the exact EXP-005/006 contamination)"
        )

    # 3. watched ports
    listeners = _listeners()
    for port in WATCH:
        pid = listeners.get(port)
        if pid is None:
            notes.append(f"port {port}: free")
            continue
        if port == API_PORT:
            if pid != api_owner:
                problems.append(
                    f"port {API_PORT} is owned by PID {pid} - NOT a "
                    "weight_stream.server. Something squatted the API port."
                )
            else:
                notes.append(f"port {API_PORT}: our API server (PID {pid})")
        elif port == LEGACY_PORT:
            warnings.append(f"port {LEGACY_PORT} is occupied by PID {pid} - "
                            "legacy port, likely an old server. Verify/kill it.")
        elif port == BACKEND_PORT:
            problems.append(
                f"port {BACKEND_PORT} is occupied by PID {pid} - the backend "
                "llama-server port must be FREE before the first load"
            )

    # 4. VRAM baseline
    used, total = _vram()
    if used is not None:
        notes.append(f"VRAM: {used} MiB / {total} MiB")
        if used > 1500:
            warnings.append(f"VRAM already {used} MiB with no model loaded - "
                            "something else is on the GPU; record this as "
                            "your baseline (measure as delta)")
    else:
        warnings.append("nvidia-smi not available — cannot check VRAM baseline")

    # 5. API server health + loaded models
    health = _http_json(f"http://127.0.0.1:{API_PORT}/health")
    if health is None:
        warnings.append(f"GET /health on :{API_PORT} failed - server not "
                        "answering (start it or let the matrix restart it)")
    else:
        notes.append(f"API :{API_PORT} healthy (v{health.get('version', '?')})")
        stats = _http_json(f"http://127.0.0.1:{API_PORT}/v1/stats")
        if stats and stats.get("models"):
            loaded = list(stats["models"].keys())
            notes.append(f"loaded models: {loaded}")
            if loaded:
                warnings.append(f"{loaded} still loaded - a measurement should "
                                "start from no loaded model")
        else:
            notes.append("loaded models: none")

    # 6. backend binary + extra args + usage history
    binary = shutil.which("llama-server") or ""
    jan_ok = _jan_has_llama_server()
    if not binary and not jan_ok:
        warnings.append("no llama-server binary found (PATH or Jan backends) - "
                        "GPU backend will fall back to CPU")
    else:
        notes.append("llama-server binary available "
                     f"(Jan backends: {jan_ok}, PATH: {bool(binary)})")
    extra = os.environ.get("WS_LLAMA_EXTRA_ARGS", "").strip()
    if extra:
        notes.append(f"WS_LLAMA_EXTRA_ARGS in THIS shell: {extra!r} - confirm "
                     "it matches what the server was spawned with")
    count, tail = _usage_tail()
    if count:
        notes.append(f"usage_history: {count} rows; last {len(tail)}:")
        for row in tail:
            notes.append(f"  {row.get('ts', '?')} {row.get('model', '?')} "
                         f"tok_s={row.get('tok_s')}")
    else:
        notes.append("usage_history: none")

    # ── verdict ─────────────────────────────────────────────────────
    # Promote BEFORE printing so a --strict failure shows its reason.
    if strict and warnings and not problems:
        problems.append("--strict: warnings promoted to failures")

    print("\n--- findings ---")
    for n in notes:
        print(f"  - {n}")
    for w in warnings:
        print(f"  ! {w}")
    for p in problems:
        print(f"  x {p}")

    print("\n" + "=" * 62)
    if problems:
        print("VERDICT: x FAIL - do NOT measure until resolved")
        print("=" * 62)
        return 2
    if warnings:
        print("VERDICT: ! WARN - safe to measure, but review the warnings")
        print("=" * 62)
        return 1
    print("VERDICT: OK CLEAN - safe to measure")
    print("=" * 62)
    return 0


if __name__ == "__main__":
    sys.exit(main())

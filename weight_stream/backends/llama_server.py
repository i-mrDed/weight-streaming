"""
llama-server backend adapter (P7.1b).

Runs the official llama.cpp `llama-server` executable as a subprocess and
talks to it over its OpenAI-compatible HTTP API. This is the same approach
Jan uses, and it gives us three things the Python binding (llama-cpp-python
0.3.34) cannot:

1. **Native reasoning control** — `--reasoning on|off|auto` + `--reasoning-budget N`
   (the binding has no reasoning fields in its C API).
2. **GPU offload** — binaries built with CUDA/Vulkan offload layers to the GPU
   (the CPU-only binding explains the 2–4 vs 35–40 tok/s gap vs Jan).
3. **A foundation for P7.3/P7.4** — tool calling + MCP need the server's
   OpenAI-compatible /v1/chat/completions with tools support.

Design:
- Lazily spawns llama-server on the first request (or explicitly via `start()`).
- Uses a dedicated port, never colliding with the API server.
- `stream_chat()` consumes the server's SSE stream and yields text deltas.
- `get_stats()` reports real generation timing + token usage.
- `get_capabilities()` reuses the same heuristic detector.
- Falls back gracefully: if the server binary is missing, `is_available()`
  is False and the caller keeps using the binding backend.
"""
from __future__ import annotations

import json
import logging
import os
import shlex
import shutil
import subprocess
import time
import urllib.request
import urllib.error
from typing import Any, Dict, Iterator, List, Optional

from ._base import WeightStreamBackend
from ..core.exceptions import ModelError, GenerationError
from ..io.page_faults import page_fault_count, paging_demand
from ..io.process_priority import lower_pid as _lower_child_priority

logger = logging.getLogger(__name__)

# Where llama-server binaries live (Jan ships CUDA builds alongside this app).
_JAN_BACKENDS = os.path.join(
    os.environ.get("APPDATA", ""),
    "Jan", "data", "llamacpp", "backends",
)

# Fixed port for the server subprocess (API server uses 8765/8804/...).
DEFAULT_SERVER_PORT = 8805
DEFAULT_HOST = "127.0.0.1"

# KV cache data types llama-server accepts (-ctk/-ctv). Keep it explicit so
# the backend never forwards garbage to the binary — unknown types are
# refused with a clear error instead of silently passing through.
KV_CACHE_TYPES = {
    "f32", "f16", "bf16",
    "q8_0", "q4_0", "q4_1", "q5_0", "q5_1", "q6_k", "q8_1",
    "iq4_nl", "iq4_xs", "iq3_s", "iq2_s",
}


def _find_llama_server() -> Optional[str]:
    """Locate a llama-server executable (newest version preferred)."""
    # 1) Explicit env override
    env = os.environ.get("WS_LLAMA_SERVER")
    if env and os.path.isfile(env):
        return env
    # 2) Jan's bundled backends
    if os.path.isdir(_JAN_BACKENDS):
        candidates = []
        for base, _, files in os.walk(_JAN_BACKENDS):
            for f in files:
                if f == "llama-server.exe" or f == "llama-server":
                    candidates.append(os.path.join(base, f))
        if candidates:
            # Prefer newest (sort by modification time desc)
            candidates.sort(key=lambda p: os.path.getmtime(p), reverse=True)
            return candidates[0]
    # 3) PATH
    found = shutil.which("llama-server")
    return found


# ── Windows orphan guard (EXP-009) ──────────────────────────────────
# Windows never reaps orphaned children: when a parent dies without
# terminating them (taskkill /F, a crash, a closed console), the child keeps
# running forever — exactly how the stale llama-server on port 8805 survived
# for days and corrupted EXP-005/006. The canonical fix is a Job Object with
# JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE: the OS force-kills every process in the
# job the moment the LAST job handle closes, i.e. when this process dies by
# ANY means. Every helper below is defensive — on any failure the backend
# behaves exactly as before (graceful close() still terminates the child;
# only the force-kill orphan case degrades).
_JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
_JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9

# PIDs of llama-server subprocesses THIS process spawned (EXP-009). The
# stale-owner sweep must never kill one of our own children: with
# max_loaded_models > 1 two backends share the fixed port, and killing a
# sibling's server would silently reroute that model's traffic to the
# other model — the exact contamination class being eliminated. A stale
# orphan from a DEAD parent is never in this set, so it is still swept.
_OWNED_PIDS: set[int] = set()


def _create_win32_kill_on_close_job() -> Optional[int]:
    """Create a KILL_ON_JOB_CLOSE Job Object; None when unsupported.

    On POSIX children are reparented and reaped by init, so there are no
    orphans and the guard is unnecessary. On Windows this returns the job
    handle (opaque int) or None if the platform refuses (best-effort).
    """
    if os.name != "nt":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateJobObjectW.restype = wintypes.HANDLE
        kernel32.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
        kernel32.SetInformationJobObject.restype = wintypes.BOOL
        kernel32.SetInformationJobObject.argtypes = [
            wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD,
        ]
        kernel32.CloseHandle.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

        class _BasicLimit(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", ctypes.c_longlong),
                ("PerJobUserTimeLimit", ctypes.c_longlong),
                ("LimitFlags", wintypes.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD),
            ]

        class _IoCounters(ctypes.Structure):
            _fields_ = [
                ("ReadOperationCount", ctypes.c_ulonglong),
                ("WriteOperationCount", ctypes.c_ulonglong),
                ("OtherOperationCount", ctypes.c_ulonglong),
                ("ReadTransferCount", ctypes.c_ulonglong),
                ("WriteTransferCount", ctypes.c_ulonglong),
                ("OtherTransferCount", ctypes.c_ulonglong),
            ]

        class _ExtendedLimit(ctypes.Structure):
            _fields_ = [
                ("BasicLimitInformation", _BasicLimit),
                ("IoInfo", _IoCounters),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t),
            ]

        job = kernel32.CreateJobObjectW(None, None)
        if not job:
            return None
        info = _ExtendedLimit()
        info.BasicLimitInformation.LimitFlags = _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not kernel32.SetInformationJobObject(
            job,
            _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
            ctypes.byref(info),
            ctypes.sizeof(info),
        ):
            kernel32.CloseHandle(job)
            return None
        return int(job)
    except Exception:
        logger.warning(
            "KILL_ON_JOB_CLOSE job creation failed — orphan guard inactive",
            exc_info=True,
        )
        return None


def _assign_process_to_job(job_handle: int, proc: Any) -> bool:
    """Assign a spawned subprocess to the kill-on-close job (best-effort).

    Some sandboxes (e.g. this process already inside a non-nestable job)
    make the assignment fail with ERROR_ACCESS_DENIED. On failure we log
    and continue — graceful close() still works; only the force-kill
    orphan protection is lost for that spawn.
    """
    if os.name != "nt":
        return False
    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
        kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        proc_handle = getattr(proc, "_handle", None)
        if proc_handle is None:
            return False
        if not kernel32.AssignProcessToJobObject(job_handle, int(proc_handle)):
            logger.warning(
                "AssignProcessToJobObject failed (%d) — orphan guard "
                "inactive for this spawn",
                ctypes.get_last_error(),
            )
            return False
        return True
    except Exception:
        logger.warning(
            "could not assign llama-server to kill-on-close job",
            exc_info=True,
        )
        return False


def _close_win32_job(job_handle: int) -> None:
    """Close a job handle — releasing the last one triggers KILL_ON_JOB_CLOSE."""
    if os.name != "nt":
        return
    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CloseHandle.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle(job_handle)
    except Exception:
        pass


def _parse_netstat_listener(output: str, port: int) -> Optional[int]:
    """PID of the process LISTENING on ``port`` from ``netstat -ano`` text.

    Line shape: ``TCP    127.0.0.1:8805    0.0.0.0:0    LISTENING    48920``
    (IPv6 ``[::]:8805`` rows and rows owned by pid 0 / our own pid are
    excluded — those are never the stale server we are allowed to kill).
    """
    suffix = f":{port}"
    for line in output.splitlines():
        parts = line.split()
        if (
            len(parts) >= 5
            and parts[0] == "TCP"
            and parts[3] == "LISTENING"
            and parts[1].endswith(suffix)
        ):
            pid = parts[-1]
            if pid.isdigit() and int(pid) > 0 and int(pid) != os.getpid():
                return int(pid)
    return None


def _find_port_pid(port: int) -> Optional[int]:
    """PID of the process LISTENING on ``port``; None when unresolvable.

    Windows: ``netstat -ano -p tcp``. POSIX: ``lsof -ti :port``. Both are
    best-effort — any failure returns None and the caller falls back to the
    port-collision guard raising (the safe current behavior).
    """
    try:
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        if os.name == "nt":
            netstat_out = subprocess.run(
                ["netstat", "-ano", "-p", "tcp"],
                capture_output=True, text=True, timeout=10, creationflags=flags,
            ).stdout or ""
            return _parse_netstat_listener(netstat_out, port)
        out = subprocess.run(
            ["lsof", "-ti", f":{port}"],
            capture_output=True, text=True, timeout=10,
        )
        if out.returncode == 0 and out.stdout.strip():
            pid = out.stdout.strip().splitlines()[0].strip()
            if pid.isdigit() and int(pid) != os.getpid():
                return int(pid)
    except Exception:
        pass
    return None


def _kill_pid(pid: int) -> bool:
    """Force-kill a process: ``taskkill /F /PID`` (Windows) or ``kill -9``."""
    try:
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/F", "/PID", str(pid)],
                capture_output=True, timeout=10, creationflags=flags,
            )
        else:
            subprocess.run(["kill", "-9", str(pid)], capture_output=True, timeout=10)
        return True
    except Exception:
        return False


class LlamaServerBackend(WeightStreamBackend):
    """Backend that runs llama-server as a subprocess and uses its HTTP API."""

    def __init__(
        self,
        model_path: str,
        n_ctx: int = 2048,
        n_threads: Optional[int] = None,
        gpu_layers: int = -1,  # -1 = auto (use all available)
        server_binary: Optional[str] = None,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_SERVER_PORT,
        kv_cache_type: Optional[str] = None,
        extra_args: Optional[str] = None,
        **kwargs,
    ):
        self._model_path = model_path
        self._n_ctx = n_ctx
        self._n_threads = n_threads
        self._gpu_layers = gpu_layers
        self._extra_args = (extra_args or "").strip()
        self._kv_cache_type = (kv_cache_type or "").strip().lower()
        if self._kv_cache_type and self._kv_cache_type not in KV_CACHE_TYPES:
            raise ModelError(
                f"Unsupported KV cache type: {kv_cache_type!r}",
                details={
                    "supported": sorted(KV_CACHE_TYPES),
                    "hint": "Use f16 (default) or a quantized type like q8_0.",
                },
            )
        self._server_binary = server_binary or _find_llama_server()
        self._host = host
        self._port = port
        self._proc: Optional[subprocess.Popen] = None
        # Windows orphan guard (EXP-009): handle of the KILL_ON_JOB_CLOSE
        # Job Object the spawned llama-server is assigned to. While this
        # handle stays open the child lives; the moment it closes (we die by
        # any means, or close() releases it) the OS force-kills the child.
        # None on POSIX or when job creation failed (graceful close() still
        # terminates the child normally).
        self._job_handle: Optional[int] = None
        self._base_url = f"http://{host}:{port}"
        self._last_gen_stats: Dict[str, Any] = {}
        self._metadata: Dict[str, Any] = {}
        self._ready = False
        self._started = False
        # Real VRAM / offload telemetry from llama-server's GET /props
        # (refreshed at most every 30s — stats polls every 2s must stay cheap).
        self._gpu_cache: Optional[Dict[str, Any]] = None
        self._gpu_cache_ts: float = 0.0

        # Detect capabilities from the GGUF metadata (arch + name).
        try:
            from weight_stream.gguf.parser import GGUFParser
            with GGUFParser(model_path) as parser:
                self._metadata = parser.metadata or {}
        except Exception:
            self._metadata = {}
        # Parity with the CPU binding (model_manager.list_models reads
        # ``getattr(model, "n_experts", 0)`` for the MoE badge in the UI).
        arch = self._get_arch()
        self.n_experts = int(
            self._metadata.get(
                f"{arch}.expert_count",
                self._metadata.get("expert_count", 0)
            )
        )

    # ── Availability ────────────────────────────────────────────────
    @classmethod
    def is_available(cls) -> bool:
        return _find_llama_server() is not None

    @property
    def is_loaded(self) -> bool:
        return self._ready and self._proc is not None and self._proc.poll() is None

    # ── Lifecycle ───────────────────────────────────────────────────
    def start(self):
        """Spawn llama-server subprocess (idempotent)."""
        if self._started:
            return
        if not self._server_binary:
            raise ModelError(
                "llama-server not found",
                details={"hint": "Set WS_LLAMA_SERVER or install Jan"},
            )
        cmd = [
            self._server_binary,
            "-m", self._model_path,
            "-c", str(self._n_ctx),
            "--host", self._host,
            "--port", str(self._port),
            "--reasoning", "auto",
            "--reasoning-budget", "-1",
        ]
        if self._n_threads:
            cmd += ["-t", str(self._n_threads)]
        if self._gpu_layers != -1:
            cmd += ["-ngl", str(self._gpu_layers)]
        # KV cache data type (P7.5): -1/auto leaves it unset; a type is
        # validated in __init__ so the subprocess always gets a real one.
        if self._kv_cache_type:
            cmd += ["-ctk", self._kv_cache_type, "-ctv", self._kv_cache_type]
        # Quiet: don't spam logs
        cmd += ["--log-disable"]
        # Optional extra args — lets us experiment with llama-server flags
        # without code changes, e.g. MoE tiering for the GPU proof:
        #   WS_LLAMA_EXTRA_ARGS="--cpu-moe -fa on -ctk q8_0 -ctv q8_0"
        # Split on whitespace (shlex handles quotes); invalid input is
        # ignored rather than crashing the backend.
        # NOTE (Windows): posix=True strips quotes correctly but treats `\`
        # as an escape — pass any paths in extra args with FORWARD slashes
        # (e.g. `-md C:/models/draft.gguf`), which Windows APIs accept.
        # Per-model extra_args (auto-tiering) take precedence over the
        # process-wide WS_LLAMA_EXTRA_ARGS — the env var stays as the
        # global fallback (the harness clean-room path).
        extra = self._extra_args or os.environ.get(
            "WS_LLAMA_EXTRA_ARGS", "").strip()
        if extra:
            try:
                cmd += shlex.split(extra)
            except ValueError:
                logger.warning("WS_LLAMA_EXTRA_ARGS unparsable, ignoring: %r", extra)

        logger.info(f"Starting llama-server: port={self._port} model={os.path.basename(self._model_path)}")
        # EXP-009 recovery: if an orphaned llama-server from a force-killed
        # parent (or an old session) still squats on our fixed port serving a
        # DIFFERENT model, kill it now so the spawn below binds cleanly. The
        # _wait_ready guard would otherwise refuse to serve it. Only a
        # responder that proves via /props to be a different model is ever
        # touched — never our own server or an empty port.
        self._sweep_stale_owner()
        self._proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        self._started = True
        # Register the child as OURS before anything else can look at the
        # port: the stale-owner sweep on a sibling backend must refuse to
        # kill it (shared fixed port, max_loaded_models > 1).
        _OWNED_PIDS.add(getattr(self._proc, "pid", None))
        # Subprocess restarted → any cached /props (VRAM, layers) may belong
        # to a previous process/model. Drop it; the next get_stats() re-reads.
        self._gpu_cache = None
        self._gpu_cache_ts = 0.0
        # EXP-009 (Windows): assign the child to a KILL_ON_JOB_CLOSE Job
        # Object so the OS terminates it whenever THIS process dies — by any
        # means (taskkill /F, crash, console close, normal exit). Windows
        # never reaps orphaned children, which is exactly how the stale 8805
        # server from the Aug-4 session survived for days. Created AFTER
        # Popen so a spawn failure cannot leak an unassigned job handle.
        self._job_handle = _create_win32_kill_on_close_job()
        if self._job_handle is not None:
            _assign_process_to_job(self._job_handle, self._proc)
        # CPU etiquette (same gate as ServerConfig.lower_process_priority):
        # the inference itself runs in THIS child, so lowering only the API
        # server would leave the actual CPU hog at normal priority and the
        # desktop still starves during generation (the user-reported
        # sluggishness with --cpu-moe). Drop the child below-normal too —
        # the desktop/browser/IDE stay responsive while a >RAM model
        # thrashes CPU+disk, with near-zero throughput cost on an idle
        # machine. Best-effort; Windows-only (POSIX cannot retarget another
        # process from an unprivileged token).
        if os.environ.get("WS_LOWER_PRIORITY", "1").strip().lower() not in (
            "0", "false", "no", "off",
        ):
            _lower_child_priority(getattr(self._proc, "pid", None))
        try:
            # 60 s was a false-negative source for >RAM models: a 104 GB
            # sharded GGUF on a cold page cache takes ~70 s+ to finish
            # loading before /health answers (measured EXP-012: cpu-moe t16
            # loaded cleanly in 69 s but the 60 s cap failed it every time).
            # Crashes are still caught fast — _wait_ready raises on process
            # exit within one poll (0.5 s), so only a slow-but-alive load
            # waits the full budget.
            self._wait_ready(timeout=300)
        except Exception:
            # Never leak the just-spawned subprocess when the port guard
            # fails (a collision the sweep could not clear, a timeout, an
            # early exit): the caller falls back to the CPU binding and drops
            # this backend — close() terminates the child first.
            self.close()
            raise

    def _wait_ready(self, timeout: float = 60.0):
        """Poll /health until the server is up.

        Port-collision guard (EXP-007): llama-server binds a FIXED default
        port (8805). If any OTHER llama-server already listens there it
        answers /health, and this backend would silently talk to the WRONG
        model (a stale Jan server was measured at 46 tok/s instead of the
        real 18). Once /health is 200 we therefore verify the responder's
        /props model_path matches the model we loaded, raising ModelError on
        mismatch. Builds that expose no /props are accepted with a warning.
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self._proc is not None and self._proc.poll() is not None:
                raise ModelError(
                    "llama-server exited early",
                    details={"returncode": self._proc.returncode},
                )
            try:
                with urllib.request.urlopen(f"{self._base_url}/health", timeout=2) as r:
                    if r.status != 200:
                        raise OSError(f"health status {r.status}")
            except Exception:
                time.sleep(0.5)
                continue
            # Health is up — but is it OUR server? (see docstring)
            self._verify_model_path()
            self._ready = True
            return
        raise ModelError("llama-server not ready (timeout)", details={"port": self._port})

    def _verify_model_path(self) -> None:
        """Strict port-ownership check via GET /props.

        llama-server exposes the loaded model path as ``model_path``. When
        present it MUST match the model we asked for — a mismatch means a
        stale server owns our fixed port. When absent (older builds) we
        cannot verify and accept with a warning rather than break them.
        """
        data = self._read_props()
        if data is None:
            logger.warning(
                "llama-server /props unavailable — cannot verify port "
                "ownership for %s; a stale server could be answering",
                os.path.basename(self._model_path),
            )
            return
        live = data.get("model_path") or data.get("model_name") or ""
        if not live:
            logger.warning(
                "llama-server /props has no model_path — cannot verify "
                "port ownership for %s",
                os.path.basename(self._model_path),
            )
            return
        if not self._same_model_path(live, self._model_path):
            raise ModelError(
                "llama-server on our port serves a DIFFERENT model — port "
                "collision with a stale server",
                details={
                    "expected": self._model_path,
                    "found": live,
                    "hint": f"kill the stale llama-server on port {self._port}",
                },
            )

    @staticmethod
    def _same_model_path(a: str, b: str) -> bool:
        """Path equality tolerant of / vs \\ and case (Windows).

        Both sides are made absolute so a relative request path still
        matches llama-server's canonicalized /props path — avoiding a
        false-positive collision on our OWN server (which would otherwise
        degrade the load to the CPU binding via the backend fallback).
        """
        def norm(p: str) -> str:
            p = p.strip().replace("\\", "/")
            try:
                p = os.path.abspath(p)
            except Exception:
                pass
            return p.lower()
        return norm(a) == norm(b)

    def _read_props(self) -> Optional[Dict[str, Any]]:
        """GET /props → dict; None on any failure (never raises)."""
        try:
            with urllib.request.urlopen(f"{self._base_url}/props", timeout=3) as r:
                return json.loads(r.read().decode("utf-8", errors="replace"))
        except Exception:
            return None

    def _sweep_stale_owner(self) -> None:
        """Best-effort: clear a stale llama-server squatting on our fixed port.

        EXP-009 recovery. If /props on our port already answers with the
        model we are about to load, it is our own server (idempotent start)
        — keep it. If it answers with a DIFFERENT model, it is an orphan
        (a force-killed parent left it behind); resolve its PID and kill it
        so the spawn below binds cleanly. Any failure degrades to the
        _wait_ready guard raising — we never guess at a PID or kill blindly.
        """
        data = self._read_props()
        if data is None:
            return  # nothing listening, or not a llama-server → port is free
        live = data.get("model_path") or data.get("model_name") or ""
        if live and self._same_model_path(live, self._model_path):
            return  # our own server already bound — nothing to clean
        pid = _find_port_pid(self._port)
        if pid is None:
            logger.warning(
                "port %s answered /props with a different model (%r) but its "
                "PID could not be resolved — the load will fail with a "
                "collision error",
                self._port, live or "?",
            )
            return
        if pid in _OWNED_PIDS:
            # A sibling backend's llama-server on the shared fixed port
            # (max_loaded_models > 1). Never kill our own child — killing
            # it would silently reroute its model's traffic to ours. Let
            # the _wait_ready guard raise (the pre-sweep safe behavior).
            logger.warning(
                "port %s serves model %r from one of OUR own backends — "
                "refusing to sweep it; this load will fail with a collision "
                "error",
                self._port, live or "?",
            )
            return
        logger.warning(
            "killing stale llama-server on port %s (PID %s, model %r)",
            self._port, pid, live or "?",
        )
        _kill_pid(pid)
        time.sleep(0.5)  # let the port actually free before we spawn

    # ── OpenAI-compatible request helper ────────────────────────────
    def _request(
        self,
        path: str,
        payload: Dict[str, Any],
        timeout: float = 300.0,
    ) -> Iterator[Dict[str, Any]]:
        """POST to the server, yielding parsed SSE events (streaming)."""
        if not self.is_loaded:
            self.start()
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self._base_url}{path}",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                for raw in resp:
                    line = raw.decode("utf-8", errors="replace").strip()
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        yield json.loads(data)
                    except json.JSONDecodeError:
                        continue
        except urllib.error.HTTPError as e:
            msg = e.read().decode("utf-8", errors="replace")
            raise GenerationError(f"llama-server HTTP {e.code}: {msg[:300]}")
        except Exception as e:
            raise GenerationError(f"llama-server request failed: {e}")

    # ── Public API (matches WeightStreamBackend) ────────────────────
    @staticmethod
    def _inject_current_date(messages: List[dict]) -> List[dict]:
        """Inject the current date into the system message.

        Models don't know today's date — without it they hallucinate
        (e.g. answering "June" in August). Jan does the same via the
        `{{current_date}}` placeholder. We inject at the backend so every
        client (console, IDE, API) gets the correct date.
        """
        import datetime
        now = datetime.datetime.now()
        date_str = now.strftime("%B %d, %Y")  # e.g. "August 04, 2026"
        out = list(messages)
        # Prepend a system message with the current date (keep existing).
        out.insert(0, {
            "role": "system",
            "content": f"Current date: {date_str}.",
        })
        return out

    def generate(
        self,
        prompt: str,
        max_tokens: int = 128,
        temperature: float = 0.7,
        top_p: float = 0.9,
        **kwargs,
    ) -> str:
        return "".join(self.stream_chat(
            [{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
            **kwargs,
        ))

    def stream_chat(
        self,
        messages: List[dict],
        max_tokens: int = 128,
        temperature: float = 0.7,
        top_p: float = 0.9,
        reasoning_mode: str = "auto",
        tools: Optional[List[dict]] = None,
        tool_choice: Optional[Any] = None,
        **kwargs,
    ) -> Iterator[str]:
        """Stream chat via llama-server's OpenAI-compatible API.

        reasoning_mode: auto|on|off → passed to the server as `reasoning`.
        The server itself handles thinking extraction (message.reasoning_content),
        so content deltas are the final answer only.

        tools/tool_choice (P7.3): passed through to llama-server, which
        natively supports tool calling. tool_calls are returned via the
        ``tool_calls`` attribute on this instance after generation.
        """
        if not self.is_loaded:
            self.start()

        mode = (reasoning_mode or "auto").lower()
        if mode not in ("on", "off"):
            mode = "auto"

        # Inject current date so the model doesn't hallucinate the date.
        messages = self._inject_current_date(messages)

        payload = {
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": top_p,
            "stream": True,
            "reasoning": mode,
            # Keep everything in `content` (no reasoning_content split). We
            # manage thinking ourselves with parseThinks (prose + tags) so
            # qwen35-family models (Qwythos/Ornith) that don't close their
            # reasoning tags still return their answer in content.
            "reasoning_format": "none",
        }
        if tools:
            payload["tools"] = tools
        if tool_choice is not None:
            payload["tool_choice"] = tool_choice

        # Reset accumulated tool_calls from any previous generation.
        self._tool_calls: List[dict] = []

        start_time = time.time()
        token_count = 0
        reasoning_chunks: List[str] = []
        # OS page-fault sampling of the llama-server SUBPROCESS (Windows):
        # llama-server mmaps the GGUF itself, so its process-wide fault
        # counter is the same honest "paging demand" signal the CPU binding
        # reports for its own process. None on POSIX (no per-child rusage).
        faults_before = page_fault_count(pid=self._proc.pid if self._proc else None)
        try:
            for event in self._request("/v1/chat/completions", payload):
                choices = event.get("choices") or []
                if not choices:
                    continue
                delta = (choices[0].get("delta") or {})
                # llama-server (--reasoning-format deepseek) separates the
                # chain-of-thought into `reasoning_content` and the final
                # answer into `content`. We yield only the answer; the
                # reasoning trace is captured for stats/UI.
                rtext = delta.get("reasoning_content") or ""
                if rtext:
                    reasoning_chunks.append(rtext)
                text = delta.get("content") or ""
                if text:
                    token_count += 1
                    yield text
                # Tool calls (P7.3): accumulate across delta chunks.
                tc = delta.get("tool_calls")
                if tc:
                    self._accumulate_tool_calls(tc)
        except GeneratorExit:
            raise
        finally:
            elapsed = time.time() - start_time
            self._last_gen_stats = {
                "token_count": token_count,
                "elapsed": elapsed,
                "tokens_per_sec": token_count / max(elapsed, 1e-9),
                "prompt": self._summarize_messages(messages),
                "backend": "llama-server",
                "reasoning_chars": sum(len(c) for c in reasoning_chunks),
                "tool_calls": len(self._tool_calls),
            }
            # Real subprocess paging demand (Windows); None elsewhere → the
            # paging key is simply absent, never fabricated.
            paging = paging_demand(
                faults_before,
                page_fault_count(pid=self._proc.pid if self._proc else None),
                token_count,
            )
            if paging is not None:
                self._last_gen_stats["paging"] = paging

    def stream_prompt(
        self,
        prompt: str,
        max_tokens: int = 128,
        temperature: float = 0.7,
        top_p: float = 0.9,
        **kwargs,
    ) -> Iterator[str]:
        return self.stream_chat(
            [{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
            **kwargs,
        )

    def close(self):
        """Stop the llama-server subprocess. Safe to call multiple times."""
        if self._proc is not None:
            # getattr: tests and edge cases may hand close() a proc stub
            # without a pid; discarding None is a harmless no-op.
            _OWNED_PIDS.discard(getattr(self._proc, "pid", None))
            try:
                self._proc.terminate()
                try:
                    self._proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self._proc.kill()
            except Exception:
                pass
            self._proc = None
        self._ready = False
        self._started = False
        # Releasing the last job handle triggers KILL_ON_JOB_CLOSE — a second
        # kill mechanism that also catches any child which survived
        # terminate(). (A raw int handle has no GC finalizer; the hard
        # guarantee is that process EXIT closes every kernel handle, which
        # fires KILL_ON_JOB_CLOSE even if close() never ran.)
        if self._job_handle is not None:
            _close_win32_job(self._job_handle)
            self._job_handle = None

    def get_stats(self) -> Dict[str, Any]:
        """Stats for /v1/stats — honest about what llama-server cannot see.

        Explicit ``buffer: None`` / ``prefetcher: None`` / ``page_cache: None``
        (never accidentally missing): llama-server manages the weights inside
        its own process (GPU offload + its own mmap), so the weight-streaming
        LRU shard buffer, the predictor/prefetcher, and the server-side page-
        cache residency tracker have no equivalent here. ``gpu`` carries REAL
        telemetry llama-server does expose (VRAM usage, layers offloaded).
        """
        return {
            "generation": self._last_gen_stats,
            "model": {
                "path": self._model_path,
                "arch": self._get_arch(),
                "backend": "llama-server",
                "n_experts": self.n_experts,
            },
            "buffer": None,        # no shard-level streaming buffer in llama-server
            "prefetcher": None,   # no predictor/prefetcher inside llama-server
            "page_cache": None,   # weights are managed inside llama-server itself
            "gpu": self._gpu_props(),
        }

    def _gpu_props(self) -> Optional[Dict[str, Any]]:
        """Real GPU telemetry from llama-server's GET /props (cached 30s).

        Returns None honestly when the server is not running, the endpoint
        is absent (older builds), or the values are not exposed (CPU-only
        builds report no VRAM). Never fabricates numbers.
        """
        if not self.is_loaded:
            return None
        now = time.time()
        if self._gpu_cache is not None and now - self._gpu_cache_ts < 30:
            return self._gpu_cache
        data = self._read_props()
        if data is None:
            return None
        total = data.get("total_vram") or 0
        used = data.get("used_vram") or 0
        self._gpu_cache = {
            "n_gpu_layers": data.get("n_gpu_layers"),
            "total_vram_mb": round(total / 1024 / 1024) if total else None,
            "used_vram_mb": round(used / 1024 / 1024) if used else None,
        }
        self._gpu_cache_ts = now
        return self._gpu_cache

    def get_capabilities(self) -> dict:
        from ..server.capabilities import detect_capabilities
        arch = self._get_arch()
        name = str(self._metadata.get("general.name", ""))
        caps = detect_capabilities(arch=arch, name=name)
        caps.tools = True  # llama-server supports tool calling
        return caps.to_dict()

    def _get_arch(self) -> str:
        return str(self._metadata.get("general.architecture", "unknown"))

    @staticmethod
    def _summarize_messages(messages: List[dict]) -> str:
        last = ""
        for msg in messages:
            if msg.get("role") == "user" and msg.get("content"):
                last = msg["content"]
        if not last and messages:
            last = messages[-1].get("content") or ""
        return str(last)[:50] + ("..." if len(str(last)) > 50 else "")

    # ── Tool calling (P7.3) ─────────────────────────────────────────
    def _accumulate_tool_calls(self, tool_calls: List[dict]) -> None:
        """Accumulate streaming tool-call deltas into complete calls.

        OpenAI streaming sends tool_calls as incremental fragments:
          [{"index":0,"id":"call_x","function":{"name":"f","arguments":""}}]
          [{"index":0,"function":{"arguments":"{\"a\":"}}]
          [{"index":0,"function":{"arguments":"1}"}}]
        We merge fragments by index into ``self._tool_calls``.
        """
        if not hasattr(self, "_tool_calls"):
            self._tool_calls = []
        for frag in tool_calls:
            idx = frag.get("index", 0)
            while len(self._tool_calls) <= idx:
                self._tool_calls.append({"id": "", "type": "function", "function": {"name": "", "arguments": ""}})
            target = self._tool_calls[idx]
            if frag.get("id"):
                target["id"] = frag["id"]
            fn = frag.get("function") or {}
            if fn.get("name"):
                target["function"]["name"] = fn["name"]
            if fn.get("arguments"):
                target["function"]["arguments"] += fn["arguments"]

    @property
    def tool_calls(self) -> List[dict]:
        """Completed tool calls from the last generation (P7.3)."""
        return list(getattr(self, "_tool_calls", []))
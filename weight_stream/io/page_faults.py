"""Process-level page-fault counters (cross-platform).

Measures the cumulative page faults of a process:

- Windows: ``psapi.GetProcessMemoryInfo().PageFaultCount`` (hard + soft)
  for the current process, or for a child process by PID (``OpenProcess``)
  — used to sample the llama-server subprocess on the GPU backend.
- POSIX:   ``resource.getrusage(RUSAGE_SELF)`` minor + major faults for the
  current process only; there is no portable per-child rusage, so asking
  for a specific PID honestly returns None.

Why this exists: during real inference llama.cpp reads the GGUF through its
own internal mmap, so ``StreamingBuffer`` never observes accesses
(``total_accesses`` stays 0 — see ADR-003 addendum). OS page-fault counters
give an honest, cheap "paging demand" channel without touching llama.cpp.
Validated by the 2026-07-30 spike: cold generation demanded ~175 MB/token
of paging, warm generation ~0.55 MB/token (300x drop — the OS working set
holds the hot set). Raw: docs/verification/spike_page_faults_2026-07-30.json
"""
import sys
from typing import Any, Dict, Optional

# Common page size on Windows/Linux x86-64 (used only for the MB estimate).
ASSUMED_PAGE_SIZE = 4096


def is_supported() -> bool:
    """True if this platform exposes a process page-fault counter."""
    if sys.platform == "win32":
        return True
    try:
        import resource  # noqa: F401
        return True
    except ImportError:
        return False


def page_fault_count(pid: Optional[int] = None) -> Optional[int]:
    """Cumulative page-fault count for a process.

    ``pid=None`` (default) measures the current process — the CPU-binding
    path. ``pid=<subprocess pid>`` measures that child process on Windows
    (used by LlamaServerBackend for the llama-server subprocess); on POSIX
    there is no portable per-child rusage, so a non-None pid honestly
    returns None.

    Returns None when the platform/counter is unavailable (callers should
    treat telemetry as unavailable rather than zero).
    """
    if sys.platform == "win32":
        return _windows_page_fault_count(pid)
    if pid is not None:
        # getrusage is RUSAGE_SELF only — no portable child sampling.
        return None
    try:
        import resource
        usage = resource.getrusage(resource.RUSAGE_SELF)
        return int(usage.ru_minflt) + int(usage.ru_majflt)
    except (ImportError, AttributeError):
        return None


def hard_fault_count() -> Optional[int]:
    """Cumulative *hard* (major) faults — faults that hit the disk.

    POSIX only (``ru_majflt``). Windows exposes no per-process hard-fault
    counter without ETW/PDH; there callers estimate disk demand from the
    model file's residency growth instead (see ``paging_demand``).
    """
    if sys.platform == "win32":
        return None
    try:
        import resource
        return int(resource.getrusage(resource.RUSAGE_SELF).ru_majflt)
    except (ImportError, AttributeError):
        return None


def _windows_page_fault_count(pid: Optional[int] = None) -> Optional[int]:
    import ctypes
    from ctypes import wintypes

    class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD),
            ("PageFaultCount", wintypes.DWORD),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t),
            ("PeakPagefileUsage", ctypes.c_size_t),
        ]

    # PROCESS_QUERY_INFORMATION — enough for GetProcessMemoryInfo on a child.
    PROCESS_QUERY_INFORMATION = 0x0400

    try:
        pmc = PROCESS_MEMORY_COUNTERS()
        pmc.cb = ctypes.sizeof(pmc)
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        psapi.GetProcessMemoryInfo.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(PROCESS_MEMORY_COUNTERS),
            wintypes.DWORD,
        ]
        psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.GetCurrentProcess.restype = wintypes.HANDLE

        if pid is None:
            handle = k32.GetCurrentProcess()
            close_handle = False
        else:
            k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
            k32.OpenProcess.restype = wintypes.HANDLE
            k32.CloseHandle.argtypes = [wintypes.HANDLE]
            k32.CloseHandle.restype = wintypes.BOOL
            handle = k32.OpenProcess(PROCESS_QUERY_INFORMATION, False, int(pid))
            close_handle = True
            if not handle:
                # Child not openable (gone / access denied) — honest None.
                return None
        try:
            if not psapi.GetProcessMemoryInfo(
                handle, ctypes.byref(pmc), pmc.cb
            ):
                return None
            return int(pmc.PageFaultCount)
        finally:
            if close_handle:
                k32.CloseHandle(handle)
    except OSError:
        return None


def paging_demand(before: Optional[int], after: Optional[int],
                  token_count: int,
                  hard_before: Optional[int] = None,
                  hard_after: Optional[int] = None,
                  residency_before_bytes: Optional[int] = None,
                  residency_after_bytes: Optional[int] = None
                  ) -> Optional[Dict[str, Any]]:
    """Build a paging-demand stats block from counter samples.

    Returns None if the total-fault samples are unavailable. Total counts
    are process-wide (hard + soft); during generation they are dominated
    by the model mmap.

    Disk demand (hard faults — bytes actually read from disk) is reported
    when measurable:
    - POSIX: directly from major-fault deltas (``hard_before/hard_after``)
    - Windows: estimated from the model file's residency growth
      (``residency_*_bytes``) — newly resident bytes ≈ bytes the OS had
      to fault in from disk; the pre-sample may be cached/stale, so this
      is a conservative lower-ish estimate, labeled as such.
    """
    if before is None or after is None:
        return None
    faults = max(0, after - before)
    stats: Dict[str, Any] = {
        "faults": faults,
        "faults_per_token": round(faults / token_count, 1) if token_count else 0.0,
        "fault_mb_per_token": round(
            faults * ASSUMED_PAGE_SIZE / token_count / 1e6, 3
        ) if token_count else 0.0,
        "note": "process-wide soft+hard faults; dominated by model mmap "
                "during generation",
    }

    if hard_before is not None and hard_after is not None:
        hard = max(0, hard_after - hard_before)
        stats["hard_faults"] = hard
        stats["disk_demand_mb"] = round(hard * ASSUMED_PAGE_SIZE / 1e6, 3)
        stats["disk_demand_source"] = "major_faults"
    elif residency_before_bytes is not None and residency_after_bytes is not None:
        delta = max(0, residency_after_bytes - residency_before_bytes)
        stats["disk_demand_mb"] = round(delta / 1e6, 3)
        stats["disk_demand_source"] = "residency_growth_estimate"
        stats["note"] += "; disk_demand estimated from model-file residency " \
                         "growth (newly resident bytes)"

    if token_count and "disk_demand_mb" in stats:
        stats["disk_mb_per_token"] = round(stats["disk_demand_mb"] / token_count, 3)
    return stats

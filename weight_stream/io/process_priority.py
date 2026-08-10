"""
Best-effort OS process priority management for the inference server.

Why this exists
---------------
CPU inference legitimately saturates whatever compute cores it is given:
decoding a token reads gigabytes of weights per second, and the compute
threads spin at full tilt. On a single-purpose box that is fine; on the
user's daily-driver PC it starves the desktop, browser, and IDE, making
the machine feel locked up during generation.

Running the server process one priority class *below* normal lets every
normal-priority process (OS shell, browser, IDE) preempt it, so the PC
stays responsive while a model generates — with essentially zero
throughput cost on an otherwise idle machine (the scheduler still hands
us every core nobody else wants).

Platforms
---------
- Windows: ``SetPriorityClass(BELOW_NORMAL_PRIORITY_CLASS)`` — fully
  reversible from an ordinary user token.
- POSIX: ``os.nice(+5)`` — best effort. Lowering the nice value again
  (restoring) requires privileges on most Unices, so ``restore`` is
  attempted and failures are reported honestly, not hidden.

Everything is idempotent and thread-safe; unsupported platforms are
reported via ``describe()`` instead of faking success.
"""

from __future__ import annotations

import logging
import os
import sys
import threading
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Win32 priority classes (processthreadsapi.h)
_IDLE_PRIORITY_CLASS = 0x00000040
_BELOW_NORMAL_PRIORITY_CLASS = 0x00004000
_NORMAL_PRIORITY_CLASS = 0x00000020
_ABOVE_NORMAL_PRIORITY_CLASS = 0x00008000
_HIGH_PRIORITY_CLASS = 0x00000080
_REALTIME_PRIORITY_CLASS = 0x00000100

_WIN_CLASS_NAMES = {
    _IDLE_PRIORITY_CLASS: "idle",
    _BELOW_NORMAL_PRIORITY_CLASS: "below_normal",
    _NORMAL_PRIORITY_CLASS: "normal",
    _ABOVE_NORMAL_PRIORITY_CLASS: "above_normal",
    _HIGH_PRIORITY_CLASS: "high",
    _REALTIME_PRIORITY_CLASS: "realtime",
}

# ── Win32 plumbing (lazy, with explicit prototypes — the ctypes restype/
#    argtypes lesson from io/page_faults.py applies here too) ──────────

_k32: Any = None


def _win_k32() -> Optional[Any]:
    """Load kernel32 with correct prototypes once; None off Windows."""
    global _k32
    if _k32 is not None:
        return _k32
    if sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.GetCurrentProcess.restype = wintypes.HANDLE
    k32.GetPriorityClass.argtypes = [wintypes.HANDLE]
    k32.GetPriorityClass.restype = wintypes.DWORD
    k32.SetPriorityClass.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    k32.SetPriorityClass.restype = wintypes.BOOL
    k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    k32.OpenProcess.restype = wintypes.HANDLE
    k32.CloseHandle.argtypes = [wintypes.HANDLE]
    k32.CloseHandle.restype = wintypes.BOOL
    _k32 = k32
    return k32


def _win_get_class() -> Optional[int]:
    k32 = _win_k32()
    if k32 is None:
        return None
    import ctypes

    cls = k32.GetPriorityClass(k32.GetCurrentProcess())
    if cls == 0 and ctypes.get_last_error() != 0:
        return None
    return int(cls)


def _win_set_class(priority_class: int) -> bool:
    k32 = _win_k32()
    if k32 is None:
        return False
    return bool(k32.SetPriorityClass(k32.GetCurrentProcess(), priority_class))


# PROCESS_SET_INFORMATION (processthreadsapi.h) — required to change another
# process's priority class from an ordinary user token.
_PROCESS_SET_INFORMATION = 0x0200


def lower_pid(pid: Optional[int]) -> bool:
    """Lower a CHILD process (the real CPU hog) below normal priority.

    The inference itself runs in the llama-server subprocess — lowering only
    the API server (ProcessPriority.lower) leaves the actual compute at
    normal priority and the desktop still starves during generation. This
    targets the child by PID.

    Windows-only: ``os.nice`` cannot change another process from an
    unprivileged token on POSIX, so this returns False there (the server
    process lowering still applies via ProcessPriority). Best-effort and
    idempotent — failures are logged, never raised.
    """
    k32 = _win_k32()
    if k32 is None or not pid or pid <= 0:
        return False
    import ctypes

    handle = k32.OpenProcess(_PROCESS_SET_INFORMATION, False, pid)
    if not handle:
        logger.warning(
            "OpenProcess(%s) failed — child priority not lowered", pid
        )
        return False
    try:
        ok = bool(k32.SetPriorityClass(handle, _BELOW_NORMAL_PRIORITY_CLASS))
        if not ok:
            logger.warning(
                "SetPriorityClass(child %s) failed — not lowered", pid
            )
        return ok
    finally:
        k32.CloseHandle(handle)


def _posix_nice(delta: int) -> Optional[int]:
    """Wrap os.nice so tests can substitute it.

    ``os.nice`` does not exist on Windows, so resolve it via getattr
    (keeps mypy honest without a platform-conditional import).
    """
    nice = getattr(os, "nice", None)
    if nice is None:
        raise OSError("os.nice unavailable on this platform")
    return nice(delta)


class ProcessPriority:
    """
    Stateful process-priority controller.

    Args:
        backend: force ``"windows"`` / ``"posix"`` / ``"none"``; default
            autodetects. Tests inject a backend to exercise both paths.
    """

    def __init__(self, backend: Optional[str] = None):
        self._lock = threading.Lock()
        self._lowered = False
        self._saved_class: Optional[int] = None
        self._nice_added = 0
        if backend is None:
            backend = self._detect_backend()
        self._backend = backend

    @staticmethod
    def _detect_backend() -> str:
        if sys.platform == "win32" and _win_k32() is not None:
            return "windows"
        if hasattr(os, "nice"):
            return "posix"
        return "none"

    @property
    def is_lowered(self) -> bool:
        with self._lock:
            return self._lowered

    def lower(self) -> bool:
        """Lower process priority below normal. Idempotent. True on success."""
        with self._lock:
            if self._lowered:
                return True
            if self._backend == "windows":
                saved = _win_get_class()
                if saved == _BELOW_NORMAL_PRIORITY_CLASS:
                    self._lowered = True
                    self._saved_class = saved
                    return True
                if not _win_set_class(_BELOW_NORMAL_PRIORITY_CLASS):
                    logger.warning(
                        "SetPriorityClass(BELOW_NORMAL) failed — priority not lowered"
                    )
                    return False
                self._saved_class = saved
                self._lowered = True
                logger.info(
                    "Process priority lowered: %s → below_normal",
                    _WIN_CLASS_NAMES.get(saved or 0, str(saved)),
                )
                return True
            if self._backend == "posix":
                try:
                    _posix_nice(5)
                except (PermissionError, OSError) as e:
                    logger.warning("os.nice(+5) failed — priority not lowered: %s", e)
                    return False
                self._nice_added = 5
                self._lowered = True
                logger.info("Process niceness raised by 5 (below-normal equivalent)")
                return True
            return False

    def restore(self) -> bool:
        """Restore the priority saved by ``lower()``. Idempotent."""
        with self._lock:
            if not self._lowered:
                return True
            if self._backend == "windows":
                target = self._saved_class or _NORMAL_PRIORITY_CLASS
                if not _win_set_class(target):
                    logger.warning(
                        "SetPriorityClass(restore) failed — still below_normal"
                    )
                    return False
                self._lowered = False
                self._saved_class = None
                logger.info("Process priority restored")
                return True
            if self._backend == "posix":
                try:
                    _posix_nice(-self._nice_added)
                except (PermissionError, OSError) as e:
                    # Honest: un-nicing usually needs privileges.
                    logger.warning(
                        "Cannot restore niceness (needs privileges): %s", e
                    )
                    return False
                self._lowered = False
                self._nice_added = 0
                logger.info("Process niceness restored")
                return True
            return False

    def describe(self) -> Dict[str, Any]:
        """Honest status for /v1/stats — no fabricated state."""
        info: Dict[str, Any] = {
            "platform": sys.platform,
            "backend": self._backend,
            "lowered": self.is_lowered,
        }
        if self._backend == "windows":
            cls = _win_get_class()
            info["priority_class"] = _WIN_CLASS_NAMES.get(cls or 0, str(cls))
            info["mechanism"] = "SetPriorityClass(BELOW_NORMAL_PRIORITY_CLASS)"
        elif self._backend == "posix":
            info["mechanism"] = "os.nice(+5)"
            info["nice_added"] = self._nice_added
        else:
            info["mechanism"] = "none (unsupported platform)"
        return info


# ── Module-level singleton + convenience API ─────────────────────────

_default: Optional[ProcessPriority] = None
_default_lock = threading.Lock()


def _get_default() -> ProcessPriority:
    global _default
    if _default is None:
        with _default_lock:
            if _default is None:
                _default = ProcessPriority()
    return _default


def lower_process_priority() -> bool:
    return _get_default().lower()


def restore_process_priority() -> bool:
    return _get_default().restore()


def is_process_priority_lowered() -> bool:
    return _get_default().is_lowered


def describe_process_priority() -> Dict[str, Any]:
    return _get_default().describe()

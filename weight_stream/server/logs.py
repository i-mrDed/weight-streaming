"""Server logging rewire for the API server (P4).

Before P4 the server only ever called ``logging.basicConfig`` (console), so:

- ``recent_errors`` in ``api_server.create_app`` was never written → the
  ``log_tail`` in ``/v1/debug/context`` was always empty (dead telemetry);
- ``WS_LOG_LEVEL`` / ``ServerConfig.log_level`` was read but never applied
  (dead env var);
- there was no ``data/server.log`` to tail or persist across restarts.

This module fixes all three honestly:

- ``RecentLogsHandler`` keeps the last ``LOG_TAIL_CAP`` (1000) formatted
  records in a ring buffer (source of ``GET /v1/logs/tail``) and mirrors the
  last ``RECENT_ERRORS_CAP`` (200) into the app's ``recent_errors`` list, so
  ``/v1/debug/context`` ``log_tail`` becomes real.
- ``attach_server_logging`` additionally adds a ``FileHandler`` to
  ``data/server.log`` (created if missing) and applies ``config.log_level``
  to the root logger (``WS_LOG_LEVEL``). It is ADDITIVE: existing console
  handlers (basicConfig / uvicorn) are left intact, and uvicorn's own
  loggers are never disabled. Handlers are attached on app-lifespan startup
  and removed on shutdown, so importing the app or building many test apps
  does not accumulate global handlers.
"""

from __future__ import annotations

import collections
import logging
import threading
from pathlib import Path
from typing import Optional

from .config import ServerConfig

LOG_LINE_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
LOG_TAIL_CAP = 1000          # max lines held for /v1/logs/tail
RECENT_ERRORS_CAP = 200      # max lines mirrored into recent_errors
DEFAULT_TAIL_LINES = 100     # /v1/logs/tail default


def resolve_log_level(name: Optional[str]) -> int:
    """Map a config log-level name ('info', 'DEBUG', …) to a logging level.

    Unknown/empty values fall back to INFO rather than raising.
    """
    if not name:
        return logging.INFO
    level = logging.getLevelName(str(name).strip().upper())
    return level if isinstance(level, int) else logging.INFO


class RecentLogsHandler(logging.Handler):
    """Ring-buffer handler: keeps the last N formatted records in memory.

    Optionally mirrors into an external list (``mirror``) capped at
    ``mirror_cap`` — used to keep the app's legacy ``recent_errors`` live.
    """

    def __init__(
        self,
        capacity: int = LOG_TAIL_CAP,
        mirror: Optional[list] = None,
        mirror_cap: int = RECENT_ERRORS_CAP,
    ) -> None:
        super().__init__()
        self._capacity = max(1, int(capacity))
        self._buffer: collections.deque = collections.deque(maxlen=self._capacity)
        self._mirror = mirror
        self._mirror_cap = max(1, int(mirror_cap))
        # Own lock for the buffer/mirror (independent of the handler lock,
        # whose type is Optional in the stdlib stubs).
        self._buflock = threading.RLock()

    def emit(self, record: logging.LogRecord) -> None:  # noqa: D401
        try:
            msg = self.format(record)
        except Exception:  # formatting must never raise into the app
            self.handleError(record)
            return
        # logging.Handler creates self.lock (RLock) in __init__; we use our own
        # buffer lock here (the stdlib stub types self.lock as Optional).
        with self._buflock:
            self._buffer.append(msg)
            if self._mirror is not None:
                self._mirror.append(msg)
                if len(self._mirror) > self._mirror_cap:
                    del self._mirror[: len(self._mirror) - self._mirror_cap]

    def tail(self, lines: int = DEFAULT_TAIL_LINES) -> list[str]:
        """Return the newest ``lines`` records (clamped to the ring cap)."""
        try:
            n = int(lines)
        except (TypeError, ValueError):
            n = DEFAULT_TAIL_LINES
        n = max(0, min(n, self._capacity))
        with self._buflock:
            items = list(self._buffer)
        return items[-n:] if n else []


def attach_server_logging(
    config: ServerConfig,
    ring_handler: RecentLogsHandler,
    log_file: str | Path,
) -> Optional[logging.FileHandler]:
    """Attach the ring + file handlers to the root logger; wire WS_LOG_LEVEL.

    Additive — never removes existing (console/uvicorn) handlers. Returns the
    file handler so the caller can detach it on shutdown (``None`` if the file
    could not be opened; logging still works via the ring + console).
    """
    root = logging.getLogger()
    formatter = logging.Formatter(LOG_LINE_FORMAT)

    if ring_handler not in root.handlers:
        root.addHandler(ring_handler)

    file_handler: Optional[logging.FileHandler] = None
    try:
        path = Path(log_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(path, encoding="utf-8")
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)
    except OSError:
        file_handler = None  # a missing/unwritable log file must not break boot

    # Wire WS_LOG_LEVEL (previously read into ServerConfig but never applied).
    # Remember the prior level so detach can restore it (avoids one app's
    # WS_LOG_LEVEL leaking into the rest of the process / other test apps).
    ring_handler._prior_root_level = root.level  # type: ignore[attr-defined]
    root.setLevel(resolve_log_level(config.log_level))
    return file_handler


def detach_server_logging(
    ring_handler: RecentLogsHandler,
    file_handler: Optional[logging.FileHandler],
) -> None:
    """Remove the handlers added by ``attach_server_logging`` (app shutdown)."""
    root = logging.getLogger()
    try:
        root.removeHandler(ring_handler)
    except Exception:
        pass
    if file_handler is not None:
        try:
            root.removeHandler(file_handler)
            file_handler.close()
        except Exception:
            pass
    prior = getattr(ring_handler, "_prior_root_level", None)
    if isinstance(prior, int):
        root.setLevel(prior)

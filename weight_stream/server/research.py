"""Serve in-app experiment evidence — the ``research/experiments/`` folder.

The Hub "Proven on this rig" cards link their Evidence button to a
repo-relative experiment path (e.g. ``research/experiments/EXP-019-gemma4-qat``).
This module serves that folder's markdown record through the API so the
evidence opens INSIDE the app (the repo may be private — no GitHub link
needed) while the path stays validated the same way the Hub's download
targets are: realpath containment under ``research/experiments/``.

Security: the server has no auth and CORS ``*``, and this endpoint reads
files from disk. Path traversal (``..``, absolute paths, symlink escapes)
is rejected with 400; a non-directory or an experiment with no markdown
files is 404. Only ``*.md`` files are ever read, and reads are
best-effort (a failed read is skipped, never an error leak).
"""

from __future__ import annotations

import os
from typing import List, NoReturn

_EXPERIMENTS_SUB = os.path.join("research", "experiments")
# Canonical reading order for an experiment record: why → numbers → verdict.
_ORDER = {"setup.md": 0, "results.md": 1, "analysis.md": 2}


class ResearchValidationError(Exception):
    """Bad experiment path (→ 400 traversal / 404 not found / no markdown)."""

    def __init__(self, message: str, status: int = 404) -> None:
        super().__init__(message)
        self.status = status


def _fail(message: str, status: int) -> NoReturn:
    raise ResearchValidationError(message, status)


def experiments_root() -> str:
    """Realpath of ``research/experiments/`` under the server's cwd.

    The server is always launched from the project root (same convention as
    the model dirs in config.py) — a missing folder fails the containment
    check naturally (404), never reads an unrelated directory.
    """
    return os.path.realpath(os.path.join(os.getcwd(), _EXPERIMENTS_SUB))


def experiment(rel_path: str) -> dict:
    """Return the markdown record of one experiment folder as a payload.

    ``rel_path`` is the repo-relative path the Hub served, e.g.
    ``EXP-019-gemma4-qat`` or ``research/experiments/EXP-019-gemma4-qat``
    (both accepted; the full prefix is stripped before containment). The
    payload is ``{path, files: [{name, markdown}]}`` with files ordered
    setup → results → analysis, then any others alphabetically.
    """
    base = experiments_root()
    if not isinstance(rel_path, str) or not rel_path.strip():
        _fail("experiment path is required", 400)

    # Absolute paths (leading separator or Windows drive) are ALWAYS bad —
    # checked on the raw string before normalisation strips any prefix.
    if rel_path.startswith("/") or rel_path.startswith("\\") \
            or ":\\" in rel_path[:3] or ":/" in rel_path[:3]:
        _fail("invalid experiment path", 400)

    # Normalise: accept both the bare folder name and the full repo path.
    p = rel_path.replace("\\", "/").strip("/")
    for prefix in ("research/experiments/", "experiments/"):
        if p.startswith(prefix):
            p = p[len(prefix):]
            break
    if not p or p == "." or ".." in p.split("/"):
        _fail("invalid experiment path", 400)

    # realpath containment (symlink escapes resolved before the check).
    real = os.path.realpath(os.path.join(base, *p.split("/")))
    if not (real == base or real.startswith(base + os.sep)):
        _fail("experiment path outside research/experiments", 400)
    if not os.path.isdir(real):
        _fail("experiment not found", 404)

    names: List[str] = [n for n in os.listdir(real) if n.lower().endswith(".md")]
    names.sort(key=lambda n: (_ORDER.get(n.lower(), 3), n.lower()))

    files: List[dict] = []
    for name in names:
        fpath = os.path.join(real, name)
        if not os.path.isfile(fpath):
            continue
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                files.append({"name": name, "markdown": f.read()})
        except OSError:
            continue  # honest: a file we cannot read is skipped, not faked
    if not files:
        _fail("no markdown files in this experiment", 404)

    rel_display = os.path.relpath(real, base).replace(os.sep, "/")
    return {"path": f"research/experiments/{rel_display}", "files": files}

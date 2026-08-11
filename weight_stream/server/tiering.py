"""Auto-tiering — pick the right model for the job.

Config-driven routing between a "fast" and a "quality" model. The pair is
NOT hardcoded to any two models: the user configures it (Settings →
Auto-tiering, or PUT /v1/tiering/config). The shipped default is the pair
proven on this rig (EXP-022/EXP-019):

- fast    → Gemma 4 12B QAT+MTP (75.7 tok/s, Thai-safe, fits VRAM)
- quality → Gemma 4 26B-A4B QAT+MTP (49–51 tok/s, Thai-safe, stronger)

Design (matches the project's honest-telemetry + local-first rules):

- **Local-first**: config lives in ``data/tiering.json`` (same convention as
  ``data/mcp/servers.json`` and ``data/assistants/``). No network.
- **Pure decision**: ``decide_tier()`` is a pure function (messages +
  options → "fast" | "quality") so the routing rule is unit-testable
  offline and the endpoint is a thin wrapper.
- **Model-agnostic**: the router knows nothing about Gemma/Qwen — it only
  needs ``enabled`` + the fast/quality model paths. Any two GGUFs work.
- **Honest state**: ``GET /v1/tiering/config`` reports which configured
  files actually resolve on disk, so a broken pair is visible, not silent.

The decision rule (configurable in the JSON):

- prompt length > ``max_prompt_chars`` (default 2000) → quality
- ``reasoning`` requested (reasoning_mode/effort above a threshold) → quality
- otherwise → fast
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

def _tiering_file() -> str:
    """Resolve the config path at CALL time so tests can point WS_TIERING_FILE
    at a temp file (the constant-at-import pattern would freeze it)."""
    return os.environ.get("WS_TIERING_FILE", "data/tiering.json")

# Default rule thresholds — the measured sweet spot on the reference rig.
DEFAULT_MAX_PROMPT_CHARS = 2000
DEFAULT_REASONING_QUALITY = "high"  # reasoning effort >= this → quality tier

# Shipped default pair (EXP-022 / EXP-019 — proven on this rig).
DEFAULT_FAST = {
    "model_id": "gemma-4-12b-qat-mtp",
    "model_path": os.path.expanduser(
        r"~/models/Gemma4-12B-QAT/gemma-4-12B-it-qat-UD-Q4_K_XL.gguf"),
    "extra_args": ("--spec-type draft-mtp --spec-draft-model "
                   r"~/models/Gemma4-12B-QAT/MTP/mtp-gemma-4-12B-it-Q8_0.gguf "
                   "--spec-draft-n-max 2"),
    "n_threads": 8,
}
DEFAULT_QUALITY = {
    "model_id": "gemma-4-26b-qat-mtp",
    "model_path": os.path.expanduser(
        r"~/models/Gemma4-26B-A4B-QAT/gemma-4-26B-A4B-it-qat-UD-Q4_K_XL.gguf"),
    "extra_args": ("--spec-type draft-mtp --spec-draft-model "
                   r"~/models/Gemma4-26B-A4B-QAT/MTP/mtp-gemma-4-26B-A4B-it-Q8_0.gguf "
                   "--spec-draft-n-max 2"),
    "n_threads": 12,  # EXP-020: -t 12 is the measured optimum for the 26B
}

REASONING_LEVELS = {"off": 0, "low": 1, "medium": 2, "high": 3}


# ── config shape ────────────────────────────────────────────────────────


def default_config() -> dict[str, Any]:
    """The shipped default pair — Gemma 4 12B (fast) + 26B (quality)."""
    return {
        "enabled": True,
        "max_prompt_chars": DEFAULT_MAX_PROMPT_CHARS,
        "reasoning_quality": DEFAULT_REASONING_QUALITY,
        "fast": dict(DEFAULT_FAST),
        "quality": dict(DEFAULT_QUALITY),
    }


def _expand(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        **entry,
        "model_path": os.path.expanduser(str(entry.get("model_path", ""))),
        "extra_args": str(entry.get("extra_args", "")).replace(
            "~/", os.path.expanduser("~").replace("\\", "/") + "/"),
    }


def _validate_entry(entry: Any, label: str) -> list[str]:
    problems: list[str] = []
    if not isinstance(entry, dict):
        return [f"{label}: must be an object with model_id/model_path"]
    model_id = str(entry.get("model_id", "")).strip()
    model_path = os.path.expanduser(str(entry.get("model_path", "")).strip())
    if not model_id:
        problems.append(f"{label}: model_id is required")
    if not model_path:
        problems.append(f"{label}: model_path is required")
    elif not Path(model_path).is_file():
        problems.append(f"{label}: file not found: {model_path}")
    return problems


def validate_config(cfg: Any) -> list[str]:
    """Return the list of config problems ([] == valid). Raises on a
    non-object payload — the endpoint maps that to HTTP 400."""
    if not isinstance(cfg, dict):
        raise ValueError("config must be a JSON object")
    problems: list[str] = []
    enabled = cfg.get("enabled", True)
    if not isinstance(enabled, bool):
        problems.append("enabled must be a boolean")
    mpc = cfg.get("max_prompt_chars", DEFAULT_MAX_PROMPT_CHARS)
    if not isinstance(mpc, int) or isinstance(mpc, bool) or mpc < 1:
        problems.append("max_prompt_chars must be a positive integer")
    rq = cfg.get("reasoning_quality", DEFAULT_REASONING_QUALITY)
    if rq not in REASONING_LEVELS:
        problems.append(
            f"reasoning_quality must be one of {sorted(REASONING_LEVELS)}")
    problems += _validate_entry(cfg.get("fast"), "fast")
    problems += _validate_entry(cfg.get("quality"), "quality")
    return problems


def normalize_config(cfg: dict[str, Any]) -> dict[str, Any]:
    """Fill defaults + expand ~ so the stored/returned config is complete."""
    base = default_config()
    for k in ("enabled", "max_prompt_chars", "reasoning_quality"):
        if k in cfg:
            base[k] = cfg[k]
    for tier in ("fast", "quality"):
        if isinstance(cfg.get(tier), dict):
            base[tier] = {**base[tier], **cfg[tier]}
    base["fast"] = _expand(base["fast"])
    base["quality"] = _expand(base["quality"])
    return base


# ── persistence ─────────────────────────────────────────────────────────


def load_config() -> dict[str, Any]:
    """Read data/tiering.json; falls back to the default pair when the file
    is missing or corrupt (honest: the default is the measured pair, not a
    fabricated one). Never raises."""
    try:
        raw = json.loads(Path(_tiering_file()).read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            return normalize_config(raw)
        logger.warning("tiering config is not an object, using defaults")
    except FileNotFoundError:
        pass
    except Exception as e:
        logger.warning("tiering config unreadable (%s), using defaults", e)
    return normalize_config({})


def save_config(cfg: dict[str, Any]) -> dict[str, Any]:
    """Validate + persist the config. Returns the normalized config;
    raises ValueError with user-readable problems when invalid."""
    problems = validate_config(cfg)
    if problems:
        raise ValueError("; ".join(problems))
    normalized = normalize_config(cfg)
    path = Path(_tiering_file())
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(normalized, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return normalized


def resolve_state(cfg: dict[str, Any]) -> dict[str, Any]:
    """Attach per-tier on-disk resolution so the UI can show a broken pair."""
    out = dict(cfg)
    for tier in ("fast", "quality"):
        entry = cfg.get(tier) or {}
        resolved = bool(entry.get("model_path")) and Path(
            entry["model_path"]).is_file()
        out[tier] = {**entry, "file_resolved": resolved}
    return out


# ── pin from model files (Hub recommended list) ────────────────────────


def find_model_file(filename: str, search_dirs: list[str]) -> Optional[str]:
    """Locate a GGUF file (by exact name, case-insensitive) under the given
    model directories. Returns the absolute path or None. Walks each dir
    lazily and stops at the first match — the Hub recommended list pins
    real downloaded files without forcing a full model scan."""
    # The Hub list carries paths like "MTP/mtp-gemma-...gguf" — match on
    # the bare basename (search walks every directory anyway).
    wanted = Path(filename).name.lower()
    for d in search_dirs:
        root = Path(d)
        if not root.is_dir():
            continue
        # Walk with a cap so a huge store (DS V4 shards) can't hang the
        # request — honest limitation, not a silent timeout.
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [x for x in dirnames if x.lower() != "node_modules"]
            for name in filenames:
                if name.lower() == wanted:
                    return str(Path(dirpath) / name)
    return None


def pin_tier(
    tier: str,
    files: list[str],
    search_dirs: list[str],
) -> dict[str, Any]:
    """Pin a tier from file names (the Hub recommended list provides the
    exact quant filenames it measured). Resolves each file on disk, wires
    MTP draft flags when a sibling draft is present, and saves.

    Raises ValueError (user-readable) when the tier or a required file is
    not found on disk.
    """
    if tier not in ("fast", "quality"):
        raise ValueError(f"tier must be 'fast' or 'quality', got {tier!r}")
    if not files:
        raise ValueError("files must be a non-empty list of filenames")

    main: Optional[str] = None
    draft: Optional[str] = None
    for f in files:
        found = find_model_file(f, search_dirs)
        if not found:
            raise ValueError(f"file not found on disk: {f}")
        low = f.lower()
        if any(x in low for x in ("mtp", "draft")) and "mtp" in Path(found).parent.name.lower():
            draft = found
        elif main is None:
            main = found
    if main is None:
        raise ValueError(
            "none of the files look like a main model (only MTP drafts given)")

    model_id = Path(main).name.replace(".gguf", "", 1)
    extra = ""
    if draft:
        extra = (f"--spec-type draft-mtp --spec-draft-model "
                 f"{draft.replace(os.sep, '/')} --spec-draft-n-max 2")

    cfg = load_config()
    cfg[tier] = {
        **cfg.get(tier, {}),
        "model_id": model_id,
        "model_path": main,
        "extra_args": extra,
    }
    return save_config(cfg)


# ── pure decision rule ──────────────────────────────────────────────────


def prompt_text(messages: list[dict[str, Any]]) -> str:
    """Concatenate message contents (system + history + latest) — the only
    signal a router should need for "how big is this job"."""
    parts: list[str] = []
    for m in messages or []:
        if not isinstance(m, dict):
            continue
        content = m.get("content")
        if isinstance(content, str):
            parts.append(content)
    return "\n".join(parts)


def decide_tier(
    cfg: dict[str, Any],
    messages: list[dict[str, Any]],
    options: Optional[dict[str, Any]] = None,
) -> tuple[str, str]:
    """Pure router: return (tier, reason). ``tier`` is "fast" or "quality".

    Rules (in order):
    1. disabled → "fast" with reason (caller should fall back to its own
       model choice; the endpoint treats disabled as 409).
    2. reasoning requested at/above the configured level → quality.
    3. prompt longer than max_prompt_chars → quality.
    4. otherwise → fast.
    """
    opts = options or {}
    if not cfg.get("enabled", False):
        return "fast", "auto-tiering disabled"

    reasoning = opts.get("reasoning_mode") or opts.get("reasoning_effort")
    threshold = REASONING_LEVELS.get(
        str(cfg.get("reasoning_quality", DEFAULT_REASONING_QUALITY)), 2)
    if reasoning is not None:
        # reasoning_mode may be a string ("off"/"low"/…) or a boolean;
        # reasoning_effort is a string level. Treat both conservatively.
        level = REASONING_LEVELS.get(str(reasoning).lower(),
                                     3 if reasoning is True else 0)
        if level >= threshold:
            return "quality", f"reasoning requested ({reasoning})"

    text = prompt_text(messages)
    mpc = int(cfg.get("max_prompt_chars", DEFAULT_MAX_PROMPT_CHARS))
    if len(text) > mpc:
        return "quality", f"prompt {len(text)} chars > {mpc}"
    return "fast", f"prompt {len(text)} chars ≤ {mpc}, no reasoning"

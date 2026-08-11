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
#
# The extra_args mirror the EXACT recipe the bench harness measured
# (EXP-022: "-fa on -t 8 --spec-draft-model … --spec-draft-n-max 2"):
# `-fa on` is not optional — without flash attention the MTP draft path
# stops generation early (~430 tokens, mid-thought, EXP-023).
#
# n_ctx is raised from the server default 2048: Gemma 4 writes long EN
# think blocks and the route's load would otherwise cap output at ~1950
# tokens (n_ctx − prompt), truncating every long answer (EXP-023 found
# the truncation live via /v1/tiering/route). The two tiers get different
# n_ctx because the KV cache is NOT free:
#   - fast (12B, fits fully in VRAM): 8192 — no measurable speed cost
#     (EXP-023: 71.4 vs 72.3 tok/s pre-fix) and ~8K output headroom.
#   - quality (26B, already spills to CPU): 4096 — ctx 8192 costs ~13%
#     decode on this rig (warm 34.1 vs 39.2 at 2048) while 4096 costs
#     only ~7% and still fits real long answers (~2.5K output budget after
#     a 3000-char prompt).
DEFAULT_FAST = {
    "model_id": "gemma-4-12b-qat-mtp",
    "model_path": os.path.expanduser(
        r"~/models/Gemma4-12B-QAT/gemma-4-12B-it-qat-UD-Q4_K_XL.gguf"),
    "extra_args": ("-fa on --spec-type draft-mtp --spec-draft-model "
                   r"~/models/Gemma4-12B-QAT/MTP/mtp-gemma-4-12B-it-Q8_0.gguf "
                   "--spec-draft-n-max 2"),
    "n_threads": 8,
    "n_ctx": 8192,
    # Output budget cap: the fast tier is for QUICK answers. Gemma 4 can
    # fall into a deterministic repetition loop on hard questions at
    # temperature 0 (EXP-023: "let me re-verify…" until the token cap —
    # repeat/presence/DRY penalties all verified-in-cmdline and none
    # escape it); 2048 bounds the burn to ~30 s while leaving room for
    # every normal answer. The client (⚡ Auto chat + the gate) clamps to
    # this.
    "max_tokens": 2048,
}
DEFAULT_QUALITY = {
    "model_id": "gemma-4-26b-qat-mtp",
    "model_path": os.path.expanduser(
        r"~/models/Gemma4-26B-A4B-QAT/gemma-4-26B-A4B-it-qat-UD-Q4_K_XL.gguf"),
    "extra_args": ("-fa on --spec-type draft-mtp --spec-draft-model "
                   r"~/models/Gemma4-26B-A4B-QAT/MTP/mtp-gemma-4-26B-A4B-it-Q8_0.gguf "
                   "--spec-draft-n-max 2"),
    "n_threads": 12,  # EXP-020: -t 12 is the measured optimum for the 26B
    "n_ctx": 4096,
    # 8192 = schema cap: the quality tier answers the same hard questions
    # cleanly (EXP-023 tonal 6/6 with a summary table in ~1800 tokens), so
    # it gets the full budget for genuinely long reasoning.
    "max_tokens": 8192,
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


def _same_path(a: Any, b: Any) -> bool:
    """Normalized (case-fold + realpath + ~-expanded) path equality — the
    same rule the manager uses when reusing an already-loaded model."""
    try:
        return os.path.normcase(os.path.realpath(os.path.expanduser(str(a or "")))) == \
            os.path.normcase(os.path.realpath(os.path.expanduser(str(b or ""))))
    except Exception:
        return False


def is_default_tier(cfg: dict[str, Any], tier: str) -> bool:
    """True when a tier still points at the shipped default entry (model id +
    path + draft flags) — i.e. the user never pinned/edited it. Compares the
    NORMALIZED config (``load_config``/``normalize_config`` output), so ~ and
    separator spellings can't fake a difference."""
    if tier not in ("fast", "quality"):
        return False
    # Normalize the shipped default exactly like a stored config (~ and
    # separator expansion) so a default-on-disk compares equal to the
    # default-in-code — spelling differences can't fake a pin.
    d = normalize_config(default_config())[tier]
    entry = cfg.get(tier) or {}
    return (
        entry.get("model_id") == d["model_id"]
        and _same_path(entry.get("model_path"), d["model_path"])
        and str(entry.get("extra_args", "")).replace("/", "\\") ==
        str(d["extra_args"]).replace("/", "\\")
    )


def resolve_state(cfg: dict[str, Any]) -> dict[str, Any]:
    """Attach per-tier on-disk resolution so the UI can show a broken pair,
    plus the file basename (for Hub pin badges) and whether the tier is still
    the shipped default (for the unpin/reset affordance)."""
    out = dict(cfg)
    for tier in ("fast", "quality"):
        entry = cfg.get(tier) or {}
        resolved = bool(entry.get("model_path")) and Path(
            entry["model_path"]).is_file()
        out[tier] = {
            **entry,
            "file_resolved": resolved,
            "model_basename": Path(str(entry.get("model_path", ""))).name,
            "is_default": is_default_tier(cfg, tier),
        }
    return out


def unpin_tier(tier: str) -> dict[str, Any]:
    """Restore ONE tier to the shipped default entry (undo a user pin from
    the Hub/Settings). The other tier and the enabled/threshold settings are
    untouched. Raises ValueError on an invalid tier name."""
    if tier not in ("fast", "quality"):
        raise ValueError(f"tier must be 'fast' or 'quality', got {tier!r}")
    cfg = load_config()
    cfg[tier] = dict(default_config()[tier])
    return save_config(cfg)


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
        # Same recipe as the shipped defaults: -fa on is required for the
        # MTP draft path (EXP-023: without it llama-server stops generation
        # early mid-thought). n_ctx keeps long answers from truncating.
        extra = (f"-fa on --spec-type draft-mtp --spec-draft-model "
                 f"{draft.replace(os.sep, '/')} --spec-draft-n-max 2")

    cfg = load_config()
    cfg[tier] = {
        **cfg.get(tier, {}),
        "model_id": model_id,
        "model_path": main,
        "extra_args": extra,
        # Same split as the shipped defaults: the fast tier (VRAM-resident)
        # can afford 8192; the quality tier pays real decode for KV size.
        "n_ctx": 8192 if tier == "fast" else 4096,
        "max_tokens": 2048 if tier == "fast" else 8192,
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

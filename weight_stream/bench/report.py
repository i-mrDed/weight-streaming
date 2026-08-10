"""Report output for the bench harness — JSON + Markdown.

The markdown table is deliberately readable as-is on GitHub / in a PR
review: one row per config with the honest cold + warm numbers side by
side, including paging (faults/token, disk MB/token) so a fast tok/s
cannot hide disk thrashing, and any failed config recorded as FAILED with
its error (never silently dropped).
"""

from __future__ import annotations

import json
import platform
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _fmt(v: Any, digits: int = 2) -> str:
    if v is None:
        return "n/a"
    try:
        return f"{float(v):.{digits}f}"
    except (TypeError, ValueError):
        return str(v)


def _fmt_vram(v: Any) -> str:
    if v is None:
        return "n/a"
    return f"{float(v):.0f} MiB"


def _row(config: dict[str, Any]) -> list[str]:
    if "error" in config:
        return [
            f"**{config['config']}**",
            f"`{config['extra_args']}`",
            "—",
            "—",
            "—",
            "—",
            f"❌ {config['error']}",
        ]
    c = config.get("cold") or {}
    w = config.get("warm") or {}
    return [
        f"**{config['config']}**",
        f"`{config['extra_args']}`",
        _fmt(c.get("tok_s")),
        f"{_fmt(c.get('faults_per_token'), 0)} / {_fmt(c.get('disk_mb_per_token'))}",
        _fmt(w.get("tok_s")),
        f"{_fmt(w.get('faults_per_token'), 0)} / {_fmt(w.get('disk_mb_per_token'))}",
        _fmt_vram(w.get("used_vram_mb")),
    ]


def matrix_to_markdown(results: list[dict[str, Any]],
                       model_path: str = "") -> str:
    """One markdown table for a full matrix run (see measure.run_matrix)."""
    lines = [
        "# 📊 Bench Matrix — honest measurement (real engine, clean room)",
        "",
        f"- **Model:** `{model_path or '(see config rows)'}`",
        f"- **Platform:** {platform.platform()}",
        f"- **Generated:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        f"- **Method:** fresh API server per config, llama-server cmdline "
        f"verified, cold = first workload gen (disk-bound), warm = second "
        f"gen (page-cache resident)",
        "",
        "| config | extra args | cold tok/s | cold faults / disk MB/tok | "
        "warm tok/s | warm faults / disk MB/tok | warm VRAM |",
        "| :--- | :--- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for r in results:
        lines.append("| " + " | ".join(_row(r)) + " |")
    lines.append("")
    return "\n".join(lines)


def matrix_to_json(results: list[dict[str, Any]], model_path: str = "") -> str:
    return json.dumps({
        "harness": "weight_stream.bench",
        "model": model_path,
        "method": ("fresh API server per config; llama-server cmdline "
                   "verified; cold = first gen, warm = second gen"),
        "results": results,
    }, ensure_ascii=False, indent=2)


def quality_to_markdown(gate: dict[str, Any]) -> str:
    """Markdown for a Thai quality-gate run (see thai.run_quality_gate)."""
    lines = [
        "# 🎯 Thai Quality Gate",
        "",
        f"- **Model:** `{gate.get('model', '')}`",
        f"- **tok/s (measured):** {_fmt(gate.get('tok_s'))}",
        f"- **Wall time (9 questions):** {_fmt(gate.get('wall_s'), 1)} s",
        "",
        "| qid | final answer (first 220 chars) |",
        "| :--- | :--- |",
    ]
    for qid, a in (gate.get("answers") or {}).items():
        final = (a.get("final") or "").replace("\n", " ").strip()
        lines.append(f"| `{qid}` | {final[:220]} |")
    lines.append("")
    return "\n".join(lines)


def write_matrix(results: list[dict[str, Any]], model_path: str,
                 json_path: Path, md_path: Path) -> None:
    """Write both JSON and markdown artifacts for a matrix run."""
    json_path.write_text(matrix_to_json(results, model_path),
                         encoding="utf-8")
    md_path.write_text(matrix_to_markdown(results, model_path),
                       encoding="utf-8")

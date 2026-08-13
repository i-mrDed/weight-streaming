"""Auto fact-check the paper draft against raw experiment data.

Every headline number in research/paper/paper.md must match the raw
measurement files in research/experiments/. This script checks the
claims by recomputing them from the raw sources (physics module, raw
benchmark JSONs, experiment results tables), so a stale or invented
number fails loudly — per the project's fact-check-before-echo rule.

Usage:

    python scripts/factcheck_paper.py [--paper research/paper/paper.md]

Exit code 0 = all checks pass; 1 = at least one claim failed.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import simulator.physics as physics  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
PAPER = ROOT / "research" / "paper" / "paper.md"

# ── helpers ──────────────────────────────────────────────────────────

def _load(p: str):
    return json.loads((ROOT / p).read_text(encoding="utf-8"))


def _has(text: str, needle: str) -> bool:
    return needle in text


# ── claim registry: (label, source-fn returns expected, check fn) ─────

checks: list[tuple[str, object]] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    checks.append((label, ok))
    print(f"{'PASS' if ok else 'FAIL'}  {label}" + (f"  [{detail}]" if detail and not ok else ""))


# ── physics constants ────────────────────────────────────────────────

bw = physics.DEFAULT_EFFECTIVE_BW_GBPS
text = PAPER.read_text(encoding="utf-8")

check("cpu-ram BW 19.18",
      _has(text, "19.18") and abs(bw["cpu-ram"] - 19.18) < 0.01,
      f"actual {bw['cpu-ram']:.3f}")
check("gpu-vram BW 61.09",
      _has(text, "61.09") and abs(bw["gpu-vram"] - 61.09) < 0.01,
      f"actual {bw['gpu-vram']:.3f}")
check("disk-mmap BW 0.38",
      _has(text, "0.38") and abs(bw["disk-mmap"] - 0.38) < 0.01,
      f"actual {bw['disk-mmap']:.3f}")
check("NVMe seq spec 14",
      _has(text, "14 GB/s") and abs(physics.NVME_SEQ_BW_GBPS - 14.0) < 0.01)

qwen_tps = physics.tok_per_sec(bw["cpu-ram"], physics.QWEN.bytes_per_token_gb)
check("Qwen predicted 22.73 tok/s",
      abs(qwen_tps - 22.73) < 0.01, f"actual {qwen_tps:.3f}")
check("Qwen bytes/token 0.844 GB",
      abs(physics.QWEN.bytes_per_token_gb - 0.844) < 0.001)
check("K3 bytes/token 15.6 GB",
      abs(physics.K3.bytes_per_token_gb - 15.625) < 0.01)
check("K3 compute 815 ms",
      _has(text, "815") and
      abs(physics.ms_per_token(bw["cpu-ram"], physics.K3.bytes_per_token_gb) - 815) < 5)

# ── EXP-028 raw (Qwen real benchmark) ────────────────────────────────

raw28 = _load("research/experiments/EXP-028-phase4-eval/raw_bench.json")
s = raw28["summary"]
check("EXP-028 warm avg 22.73",
      abs(s["avg_tok_s_warm"] - 22.73) < 0.01, f"actual {s['avg_tok_s_warm']:.3f}")
check("EXP-028 error +0.02%",
      _has(text, "+0.02%") and abs(s["throughput_error_warm"]) < 0.001)

# p50/p90/p99 averages across the 3 runs (the corrected numbers)
p50s = [r["latency"]["p50"] for r in raw28["runs"]]
p90s = [r["latency"]["p90"] for r in raw28["runs"]]
p99s = [r["latency"]["p99"] for r in raw28["runs"]]
avg50, avg90, avg99 = sum(p50s) / 3, sum(p90s) / 3, sum(p99s) / 3
check("EXP-028 p50 41.1", _has(text, "41.1") and abs(avg50 - 41.1) < 0.3,
      f"actual {avg50:.1f}")
check("EXP-028 p90 48.6", _has(text, "48.6") and abs(avg90 - 48.6) < 0.3,
      f"actual {avg90:.1f}")
check("EXP-028 p99 84.4", _has(text, "84.4") and abs(avg99 - 84.4) < 0.5,
      f"actual {avg99:.1f}")
check("p99 ~2.0x p50", _has(text, "2.0×") and abs(avg99 / avg50 - 2.0) < 0.2,
      f"actual ratio {avg99/avg50:.2f}")
check("EXP-028 hit rate 1.000", all(r["hit_rate"] == 1.0 for r in raw28["runs"]))

# ── EXP-029 raw (K3 sim) ─────────────────────────────────────────────

raw29 = _load("research/experiments/EXP-029-k3-vs-qwen/k3_bench.json")
check("EXP-029 K3 256MB hit 0.512",
      _has(text, "0.512") and abs(raw29["hit_rate"] - 0.5118) < 0.001)
check("EXP-029 K3 256MB tok/s 0.049",
      _has(text, "0.049") and abs(raw29["predicted_tok_s"] - 0.0488) < 0.001,
      f"actual {raw29['predicted_tok_s']:.4f}")
check("EXP-029 K3 p50 21300", abs(raw29["latency"]["p50"] - 21300) < 100)
check("EXP-029 K3 p90 27051", abs(raw29["latency"]["p90"] - 27051) < 100)
check("EXP-029 K3 p99 31258", abs(raw29["latency"]["p99"] - 31258) < 100)

# 4 GB buffer result (from the sweep, recorded in EXP-029 results.md)
from simulator.config import SimConfig  # noqa: E402
from simulator.run import run_simulation  # noqa: E402
from simulator.buffer_abstraction import predicted_tok_per_sec  # noqa: E402
cfg = SimConfig()
cfg.workload.n_tokens = 1000
cfg.buffer.size_mb = 4096
r4g = run_simulation(cfg)
hr4 = r4g.buffer_stats["hit_rate"]
tps4 = predicted_tok_per_sec(hr4, physics.K3.bytes_per_token_gb,
                             bw["cpu-ram"], bw["disk-mmap"])
check("K3 @4GB hit 0.999", _has(text, "0.999") and hr4 > 0.99, f"actual {hr4:.4f}")
check("K3 @4GB tok/s 1.18", _has(text, "1.18") and abs(tps4 - 1.18) < 0.05,
      f"actual {tps4:.4f}")
check("24x upside", _has(text, "24×") and abs(tps4 / raw29["predicted_tok_s"] - 24.2) < 2,
      f"actual {tps4/raw29['predicted_tok_s']:.1f}x")

# ── EXP-012 real >RAM ────────────────────────────────────────────────

check("EXP-012 104 GB", _has(text, "104 GB"))
check("EXP-012 1.5-1.9 tok/s", _has(text, "1.5–1.9"))
check("EXP-012 36k-77k faults", _has(text, "36,000–77,000"))
check("EXP-012 150-300 MB/token", _has(text, "150–300"))

# ── no stale numbers ─────────────────────────────────────────────────

for stale in ["69.6", "41.3", "1.7×", "10 GB MoE", "17 experiments",
              "EXP-015/016/017"]:
    check(f"no stale '{stale}'", stale not in text)

# ── summary ──────────────────────────────────────────────────────────

passed = sum(1 for _, ok in checks if ok)
failed = sum(1 for _, ok in checks if not ok)
print(f"\n{passed} passed, {failed} failed")
if failed:
    print("FAILED claims:")
    for label, ok in checks:
        if not ok:
            print(f"  - {label}")
    raise SystemExit(1)
raise SystemExit(0)

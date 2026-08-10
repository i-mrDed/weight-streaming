"""Benchmark harness (honest-measurement core).

The project's ground rule is honest telemetry: every number comes from a
real measurement through the REAL engine (llama-server via the API
server), never a fabricated value. This package packages that discipline
so ANY model can be measured reproducibly:

- ``thai``     — the Thai quality gate (9 fixed questions, the project's
                 quality floor from EXP-009/EXP-011: ultra-low-bit quants
                 fail Thai tonal accuracy).
- ``measure``  — clean-room measurement: kill stale servers, start a fresh
                 API server per config, load the model through the real
                 backend, verify the ACTUAL llama-server cmdline, generate,
                 and read tok/s + paging from /v1/stats (cold + warm).
- ``report``   — JSON + markdown output of a measurement/grid run.

CLI: ``python -m weight_stream bench <model.gguf> [--matrix ...] [--thai]``
"""

from .thai import QUESTIONS, run_quality_gate, split_think
from .measure import measure_model, run_matrix, verify_extra_args
from .report import matrix_to_markdown, matrix_to_json, quality_to_markdown

__all__ = [
    "QUESTIONS",
    "run_quality_gate",
    "split_think",
    "measure_model",
    "run_matrix",
    "verify_extra_args",
    "matrix_to_markdown",
    "matrix_to_json",
    "quality_to_markdown",
]

__version__ = "0.1.0"

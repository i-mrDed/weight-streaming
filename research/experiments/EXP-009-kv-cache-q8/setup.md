# EXP-009: KV Cache q8_0 vs f16 — Setup

## Goal

Measure whether quantized KV cache (`-ctk q8_0 -ctv q8_0`) frees meaningful
VRAM and/or changes tok/s on THIS machine — the lever suggested after
EXP-006 ("free VRAM ~0.1 GB per 2048 ctx").

## Hypothesis

KV cache ≈ 2 × layers × KV-heads × head_dim × n_ctx × bytes/elem. For
Qwen3.6-35B-A3B (40 layers, 8 KV heads, 128 head_dim): q8_0 halves the KV
bytes vs f16. IF the KV cache lives in VRAM, q8_0 should free VRAM and
possibly improve offload headroom. EXP-007 found the KV cache lives mostly
in HOST RAM on this setup — so the expectation is a near-no-op, but with
real numbers.

## Setup

- **Model:** Qwen3.6-35B-A3B UD-IQ2_M (~/models)
- **Backend:** llama-server (Jan b9967) via API server, `--n-cpu-moe 10 -fa on`
- **Method:** measure_ncmoe_matrix.py with WS_MATRIX_CONFIGS override
  (same-session apples-to-apples, token-exact flag verification, clean-room gate)
- **Configs:**
  1. `--n-cpu-moe 10 -fa on` (f16 KV baseline)
  2. `--n-cpu-moe 10 -fa on -ctk q8_0 -ctv q8_0`
- **Metrics:** server tok/s, SSE raw tok/s, VRAM after gen, p95 per-token
- **Clean-room:** gate CLEAN before run; flags verified on live cmdline

# EXP-010: Speculative Decoding — Setup

## Goal

Test whether speculative decoding can lift tok/s above the ~53.9-56.4
ceiling (n-cpu-moe 0) or the 44-47 sweet-spot (n-cpu-moe 10) on the
Qwen3.6-35B-A3B + 12 GB VRAM setup.

## Hypothesis

A small draft model proposes tokens cheaply; the target verifies them in a
batched forward — on a bandwidth-bound MoE the batched matmul reuses each
expert weight across the batch, potentially cutting effective bytes-per-
token read from RAM.

## Setup

- **Target:** Qwen3.6-35B-A3B UD-IQ2_M (D:/models)
- **Draft candidates:**
  1. Qwen3-0.6B-Q8_0 (639 MB, `~/models/`) — official Qwen,
     Qwen3 tokenizer (151,936 tokens)
  2. ngram-simple — no draft model (uses the target's own context)
  3. MTP variant (`unsloth/Qwen3.6-35B-A3B-MTP-GGUF`) — same model family,
     but a full 35B draft (impractical: doubles expert streaming + VRAM)
- **Backend:** llama-server (Jan b9967) — NOTE this build uses the NEW
  speculative API: `-md` alone is NOT enough, **`--spec-type` defaults to
  `none`** and must be set explicitly (e.g. `draft-simple`, `ngram-simple`)
- **Method:** measure_ncmoe_matrix.py with WS_MATRIX_CONFIGS override,
  token-exact cmdline verification, clean-room gate
- **Metrics:** server tok/s, raw tok/s, VRAM after gen, p95

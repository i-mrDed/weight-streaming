# EXP-011: Ultra-Low-Bit Quant (IQ1_M) — Setup

## Date
2026-08-07 · clean-room gate: OK CLEAN (exit 0) before AND after measurement

## Goal
Test whether a SMALLER quant (fewer expert bytes on disk → less RAM→VRAM
traffic per expert read) raises the tok/s ceiling on the 12 GB VRAM /
i9-9900KF setup, beyond the 56.4 tok/s ceiling measured with IQ2_M
(EXP-008 re-validation).

## Model
- **Target:** `unsloth/Qwen3.6-35B-A3B-GGUF/Qwen3.6-35B-A3B-UD-IQ1_M.gguf`
- **Size:** 10,047,749,088 bytes (10.05 GB) — vs IQ2_M at 11.5 GB (−1.5 GB)
- **Quant:** UD-IQ1_M (unsloth dynamic 1-bit class, ~1.75 bpw average)
- **Download:** via server Hub endpoint, resumed from a 3.8 GB `.part`
  after the mid-stream truncation bug (see `weight_stream/server/hub.py`
  integrity gate fix this session). File verified byte-exact against the
  CDN `Content-Range` total (10,047,749,088).

## Machine
RTX 3060 12 GB (360 GB/s, ~12.7 TFLOPS FP16) · i9-9900KF · 64 GB RAM

## Method
`scripts/measure_ncmoe_matrix.py` via the running API server (port 8765,
`--n-cpu-moe 10` default server flags), clean-room gate enforced:

```
WS_TEST_MODEL="~/models/Qwen3.6-35B-A3B-UD-IQ1_M.gguf"
WS_TEST_MODEL_ID="qwen36a3b_iq1m"
WS_MATRIX_CONFIGS='{"n-cpu-moe 10": "--n-cpu-moe 10 -fa on",
                    "n-cpu-moe 0 (all GPU)": "--n-cpu-moe 0 -fa on"}'
```

Same harness, same prompt, same `n_ctx` as EXP-008 — apples-to-apples.

## Environment note
First matrix run ABORTED on the clean-room gate: two orphan llama-server
processes (PID 58188, parent 70456 = **Jan.exe**; PID 14484 child of
58188) were serving a leftover model from the Jan desktop app. Killed
before measuring. Lesson: the Jan app spawns llama-server children that
the gate correctly flags — close/exit Jan (or unload its model) before
benchmark runs.

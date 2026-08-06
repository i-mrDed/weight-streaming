# EXP-007: Context Size (KV Cache) Scaling — Setup

> **⚠️ Important preamble:** this experiment's CLEAN results exposed that
> EXP-005 and EXP-006 were **contaminated by a stale Jan llama-server**
> (Qwythos-9B dense) squatting on port 8805 — the SAME port our backend
> uses. See EXP-007 analysis + the erratum appended to EXP-005/EXP-006
> results. The numbers below are the verified-clean measurements.

## Goal

Measure how `n_ctx` (KV cache reservation) affects VRAM and decode speed on
the GPU + `--cpu-moe` tiering setup — with REAL numbers on THIS machine
(i9-9900KF, 64GB DDR4, RTX 3060 12GB).

## Hypothesis (from earlier analysis, before measurement)

KV ≈ 2 × layers × KV-heads × head_dim × n_ctx × bytes/elem. For
Qwen3.6-35B-A3B (40 layers, 8 KV heads, 128 head_dim, FP16):

| n_ctx | predicted KV (FP16) | predicted KV (Q8_0) |
|-------|--------------------:|--------------------:|
| 2048  | ~0.33 GB            | ~0.16 GB            |
| 8192  | ~1.34 GB            | ~0.67 GB            |
| 32768 | ~5.37 GB            | ~2.68 GB            |

Predicted: VRAM delta should grow roughly linearly with n_ctx; decode speed
should stay flat as long as KV fits VRAM (experts stream from RAM either way).

## Hardware / software

- CPU: i9-9900KF (8C/16T), RAM: 64GB DDR4-3200 dual-channel (~45 GB/s)
- GPU: RTX 3060 12GB VRAM (driver 610.88, CUDA 13.3)
- llama-server: Jan b9967 win-cuda-13-common_cpus-x64 build (b1-bb7049f7)
- Model: Qwen3.6-35B-A3B-UD-IQ2_M.gguf (11.52 GB, 256 experts/layer, 8 active)
- Flags: `--cpu-moe -fa on` (via WS_LLAMA_EXTRA_ARGS), `-t 8`, KV default (FP16)

## Method

1. Kill any stale llama-server on port 8805 (contamination guard).
2. For each n_ctx ∈ {2048, 8192, 32768, 2048(repeat)}:
   - unload → capture baseline VRAM (nvidia-smi)
   - load with n_ctx=N via POST /v1/models/load
   - capture VRAM right after load (llama.cpp allocates GPU buffers lazily,
     so pre-generation VRAM is expected to be low)
   - warm-up generation (fills OS page cache + triggers lazy spawn)
   - **verify backend /props shows OUR model** (stale-server guard)
   - measured generation: 200 tokens via /v1/chat/completions SSE,
     per-token timestamps → avg tok/s + p95
   - capture VRAM after generation (KV + compute buffers live here)
   - unload, confirm VRAM returns to baseline
3. Also capture llama-server working set (RAM) for ctx=2048 vs 32768 to see
   where the KV cache actually lives.

## Harness

`scripts/measure_ctx_scaling.py` (WS_CTX to override the sweep).

## Date / author

2026-08-06 — local agent, user-driven experiment.

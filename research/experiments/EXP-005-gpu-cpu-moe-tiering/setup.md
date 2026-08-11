# EXP-005: GPU `--cpu-moe` Tiering Proof (Qwen3.6-35B-A3B)

## Setup

| Parameter | Value |
|-----------|-------|
| **Date** | 2026-08-06 |
| **Machine** | i9-9900KF · 64GB DDR4-3200 (dual-channel) · RTX 3060 12GB · NVMe |
| **Backend** | LlamaServerBackend (llama-server b9967, CUDA 13 build) |
| **Extra args** | `WS_LLAMA_EXTRA_ARGS="--cpu-moe -fa on"` (new injection point) |
| **Model** | Qwen3.6-35B-A3B-UD-IQ2_M (11.5 GB GGUF, ~/models/) |
| **Architecture** | qwen35moe · **256 experts/layer · 8 active · 40 layers (10,240 experts total)** |
| **Quantization** | UD-IQ2_M |
| **Context** | 2048 |
| **Prompt** | short creative + explanatory prompts |
| **Tokens** | 200 measured per run |

## Why this model

- Experts (256/layer) **cannot fit in 12 GB VRAM** — attention/shared stay on GPU,
  expert weights must live in RAM (page cache) → a *real* tiering test.
- Active working set per token ≈ 8/256 experts ≈ **~0.4 GB/token** — small enough
  that decode should be GPU-bandwidth-bound if the hot set is cached.

## Method

1. Start API server with `WS_LLAMA_EXTRA_ARGS="--cpu-moe -fa on"`.
2. `POST /v1/models/load` (GPU backend auto-selected).
3. `POST /v1/chat/completions` ×2 (cold, then warm).
4. `GET /v1/stats` → generation tok/s + subprocess paging + VRAM.

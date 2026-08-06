# EXP-006: CPU Thread Scaling on `--cpu-moe` (Qwen3.6-35B-A3B)

## Setup

| Parameter | Value |
|-----------|-------|
| **Date** | 2026-08-06 |
| **Machine** | i9-9900KF (8c/16t) · 64GB DDR4-3200 dual-channel (~45 GB/s) · RTX 3060 12GB |
| **Backend** | LlamaServerBackend (llama-server b9967, CUDA 13) + `WS_LLAMA_EXTRA_ARGS="--cpu-moe -fa on"` |
| **Model** | Qwen3.6-35B-A3B-UD-IQ2_M (11.5 GB) — 256 experts/layer, 8 active, 40 layers |
| **Context** | 2048 · n_threads = 8, 12, 16 (then 8 again = drift check) |
| **Method** | per config: unload → load → 1 warm-up gen → 1 measured gen via `/v1/chat/completions` SSE, per-delta timing |
| **Measured** | server tok/s (`/v1/stats`), raw SSE tok/s, per-token ms avg/median/p95/max |
| **Prompt** | "Write a 3-sentence story about a cat astronaut. Be concise." · 200 tokens |
| **Tooling** | `scripts/measure_threads_scaling.py` |

## Hypothesis

With `--cpu-moe`, the 8 active experts/layer run on CPU and the workload is
**memory-bound** (DDR4-3200 dual-channel ≈ 45 GB/s), not compute-bound. Threads
beyond the 8 physical cores should add nothing (hyperthreading cannot raise RAM
bandwidth); 16 may even regress slightly from contention.

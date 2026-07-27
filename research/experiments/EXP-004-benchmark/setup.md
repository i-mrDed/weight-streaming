# EXP-004: Real MoE Hardware Benchmark

## Setup

| Parameter | Value |
|-----------|-------|
| **Date** | 2026-07-27 |
| **CPU** | (RTX 3060 system, not used for inference) |
| **RAM** | 68.6 GB (41 GB available during test) |
| **Inference Engine** | llama-cpp-python 0.3.16, CPU-only (n_gpu_layers=0) |
| **Model** | Qwen1.5-MoE-A2.7B (GGUF Q2_K, 5.88 GB) |
| **Model Architecture** | 2.7B active params, 8 experts (top-2), 24 layers |
| **Quantization** | Q2_K (~2.5 bits avg) |
| **Prompt** | "The future of artificial intelligence is" |
| **Tokens** | 100 measured (10 warmup) |

## K3 Reference Values

| Parameter | Qwen Measured | K3 Estimated |
|-----------|--------------|-------------|
| Active params | 2.7B | 50B (16/896 × 2.8T) |
| Active weights/token | 0.84 GB (Q2_K) | 25 GB (MXFP4) |
| Scale factor | 1x | 18.5x |
| Compute time/token | 44ms | 815ms |
| NVMe full load | 60ms | 1786ms |

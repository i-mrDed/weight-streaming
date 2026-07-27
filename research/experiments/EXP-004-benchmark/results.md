# EXP-004: Real MoE Hardware Benchmark — Results

## Baseline (Qwen1.5-MoE-A2.7B on CPU, llama.cpp)

| Metric | Value |
|--------|-------|
| Compute time | 44.0 ms/token |
| Throughput | 22.7 tok/s |
| Prefill (16 ctx) | 261 ms |
| Prefill (32 ctx) | 196 ms |
| Prefill (64 ctx) | 351 ms |
| Prefill (128 ctx) | 679 ms |
| Prefill (256 ctx) | 1299 ms |

## K3 Scaling Estimates

| Metric | Value |
|--------|-------|
| Estimated compute | 815 ms/token (1.23 tok/s) |
| NVMe full load | 1786 ms (25 GB @ 14 GB/s) |
| **Bottleneck** | **I/O-BOUND** (NVMe > compute) |

## I/O Sensitivity (K3 with Buffer)

| Miss Rate | I/O Load | Stall | Total | t/s |
|-----------|----------|-------|-------|-----|
| 0% (perfect) | 0 ms | 0 ms | 815 ms | 1.23 |
| 10% | 179 ms | 54 ms | 869 ms | 1.15 |
| 25% | 446 ms | 134 ms | 949 ms | 1.05 |
| 50% (no buffer) | 893 ms | 268 ms | 1083 ms | 0.92 |
| 75% | 1339 ms | 402 ms | 1217 ms | 0.82 |
| 100% (worst) | 1786 ms | 536 ms | 1506 ms | 0.66 |

## Key Comparison

| Configuration | Throughput | Buffer Benefit |
|--------------|-----------|---------------|
| No streaming (all RAM) | 1.23 tok/s | — |
| LFU 512 MB (76.2% hit) | 1.06 tok/s | +88% vs no buffer |
| No buffer (0% hit) | 0.56 tok/s | baseline |

## Simulator Update

| Parameter | Old Value | New Value |
|-----------|-----------|-----------|
| compute_time_per_token_us | 350,000 (350ms) | **815,000 (815ms)** |
| Bottleneck assumption | compute-bound | **I/O-bound** |

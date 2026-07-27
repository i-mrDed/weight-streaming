# EXP-004: Real MoE Hardware Benchmark — Analysis

## Key Finding: The Bottleneck Flips

Our simulator (EXP-001, 002, 003) assumed **350ms/token compute time** for K3. This made the system compute-bound, and predictor accuracy didn't matter.

The real hardware benchmark shows **815ms/token compute time** for K3, making the system **I/O-bound** (NVMe 1786ms > compute 815ms).

**Impact on architecture:**
- Old (compute-bound): predictor accuracy irrelevant, buffer hit rate irrelevant, throughput fixed at 2.73 t/s
- New (I/O-bound): **predictor accuracy matters, buffer hit rate matters, throughput varies with miss rate**

## Buffer Value Changes Dramatically

| EXP-002 Conclusion | EXP-004 (hardware) |
|---|---|
| "Predictor accuracy doesn't matter" | **Predictor accuracy directly affects I/O overlap → throughput** |
| "LFU flat at 76.2% regardless" | **76.2% hit rate → +88% throughput over no buffer** |
| "Throughput flat at 2.73 t/s" | **Throughput varies 0.56-1.23 t/s depending on buffer** |

## Why the Simulator Was Wrong

The original timing config assumed `compute_time_per_token_us = 350,000` — an educated guess for K3 on consumer CPU. The real value is ~2.3x higher (815ms) because:

1. **Memory bandwidth bottleneck scales with model size**: CPU reads ~19 GB/s. K3's 25 GB active weights → 1.3s. Simulator assumed 350ms (too optimistic).
2. **Prefill time is expensive**: 256 tokens context → 1.3s prefill, which adds overhead in chat scenarios.

## Implications for Design

1. **Predictor IS valuable** — higher accuracy → better I/O overlap → less stall → higher throughput
2. **Buffer IS valuable** — 76.2% hit gives 1.06 tok/s, 0% gives 0.56 tok/s
3. **Priority boost might matter** — in I/O-bound regime, keeping right experts in buffer directly reduces NVMe reads
4. **Prefill optimization matters** — single context of 256 tokens takes 1.3s, which dominates for short interactions

## Updated Throughput Estimates (K3 on this HW)

| Configuration | Estimate | vs Baseline |
|--------------|----------|-------------|
| Oracle (100% hit, perfect overlap) | 1.23 tok/s | +120% |
| LFU 512 MB + perfect I/O overlap | 1.15 tok/s | +105% |
| LFU 512 MB (realistic) | 1.06 tok/s | +89% |
| LRU+priority 512 MB, 70% acc | 0.92 tok/s | +64% |
| No buffer (reactive load all) | 0.56 tok/s | baseline |

## Caveats

1. **Linear parameter scaling is an approximation.** MoE compute doesn't scale perfectly linearly with active params due to attention cost, routing overhead, etc.
2. **Single CPU test.** Different CPU/RAM speeds change the ratio.
3. **NVMe bandwidth assumed at 14 GB/s.** Real PCIe 5.0 NVMe varies.
4. **Q2_K vs MXFP4 quantization difference.** Q2_K is mixed precision (2-6 bits), MXFP4 is uniform 4-bit. The exact byte count differs.

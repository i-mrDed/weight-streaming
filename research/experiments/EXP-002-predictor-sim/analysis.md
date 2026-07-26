# EXP-002: Predictor Accuracy Simulation — Analysis

## Three Key Findings

### 1. LFU Does Not Benefit from Prediction

LFU hit rate is **flat at 76.2%** across all accuracy levels (10% to 90% to perfect). This is by design — LFU eviction uses access frequency, not prediction priority. The predictor confidence (`predict_boost`) is ignored by LFU.

**Implication**: If we use LFU for buffer eviction (best choice per EXP-001), predictor accuracy has ZERO impact on buffer hit rate. The buffer works well regardless of prediction quality.

### 2. LRU+priority Has a "Priority Clogging" Problem

Counter-intuitively, **higher accuracy makes LRU+priority WORSE**: 29.9% hit rate at 10% accuracy → 15.5% at perfect.

**Root cause**: When predictions are highly accurate, correctly-predicted experts get high priority (0.95) and NEVER get evicted. These "clog" the buffer while the ~10% of unpredicted-but-needed experts (priority 0.0) are always evicted first.

This is a known pitfall in priority-based caching: priority is only useful if it covers ALL needed items. Partial coverage makes things worse.

**Implication**: LRU+priority should NOT be used for this workload. LFU is strictly better.

### 3. Throughput is Compute-Bound, Not I/O-Bound

Despite the predictor improving I/O overlap by 7.6x (30.9ms → 233.8ms), **throughput is flat at 2.73 t/s**.

**Why**: The simulator assumes 350ms/token compute time for a 2.8T MoE on consumer hardware. At this scale, I/O (NVMe reads at 14 GB/s) is fast relative to compute. The compute completely masks the I/O cost.

Computation:
- 76.2% hit rate → 847 hits/token → 242 ms sequential I/O
- 23.8% miss rate → 264 misses/token → 15.8 ms random I/O
- Total I/O: ~258 ms per token
- Compute: 350 ms per token
- I/O can be fully overlapped with compute → compute dominates total time

**Implication**: For K3-scale models, weight streaming is about **enabling inference with limited RAM**, not about throughput improvement. The system achieves the same throughput as a fully-loaded-RAM system but uses only 512 MB for weights.

## Design Implications for the Architecture

### The Predictor's Role is Reduced

| Original Design (ADR-001) | Updated Assessment |
|--------------------------|-------------------|
| MLP predictor with 70%+ accuracy | Accuracy not critical — even 10% works |
| Predictor → improve eviction | Eviction: use LFU (no prediction needed) |
| Predictor → improve I/O overlap | Overlap helps but doesn't change throughput |
| Priority boost for predicted experts | REMOVE priority boost from LFU |

### What Actually Matters

1. **Reliable NVMe streaming**: Ensure I/O never stalls compute. Sequential NVMe reads at 14GB/s can cover ~3GB per 250ms compute window.
2. **Cold start**: First few tokens have no buffer history → predictor helps here
3. **Minimal buffer**: 512 MB is sufficient; maybe even 256 MB would work (per EXP-001: 256 MB LFU = 60.9%)
4. **LFU eviction**: Simple, no prediction needed, works well

### Where Prediction Still Adds Value

1. **Cold start**: Before frequency counts accumulate, the predictor pre-loads likely experts
2. **Turbulence resilience**: When the access pattern shifts, predictor can compensate before LFU adapts
3. **Workload with faster compute**: If compute time drops (e.g., GPU offloading, smaller model), I/O becomes the bottleneck and prediction matters more

## Updated System Design Recommendations

```
Before (ADR-001):     After (EXP-002 findings):
─────────────────     ───────────────────────
Buffer: 256 MB        Buffer: 256-512 MB (no change)
Eviction: LRU+P       Eviction: LFU (changed)
Predictor: MLP 70%    Predictor: simple heuristic (accuracy not critical)
Priority boost: on    Priority boost: off for LFU (changed)
```

## Next Question for Phase 3b

**What is the actual compute time for running K3-scale MoE on consumer hardware?**

This simulator assumes 350ms/token. If the real value is:
- **Faster** (e.g., 50ms with GPU): I/O becomes the bottleneck → prediction matters
- **Slower** (e.g., 1000ms with CPU-only): Even less need for prediction
- **The same** (~350ms): Current design stands, prediction not critical

Phase 3b should measure this on real hardware with llama.cpp or similar.

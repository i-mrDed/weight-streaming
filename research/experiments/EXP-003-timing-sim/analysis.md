# EXP-003: Timing Analysis

## Verified: Overlap ทำงานได้ดี

| Config | Total/Token | Stall | Overlap | Overlap % |
|--------|------------|-------|---------|-----------|
| 256 MB LRU + heuristic | 380.2 ms | 30.2 ms | 216.9 ms | 57.0% |
| 512 MB LRU + heuristic | 365.9 ms | 15.9 ms | 274.0 ms | 74.9% |
| **512 MB LFU + heuristic** | **364.5 ms** | **14.5 ms** | **279.5 ms** | **76.7%** |

All configs exceed 57% overlap. Best config: **76.7% overlap**.

## Verified: Stall ต่ำ

- 256 MB: 30.2 ms stall (7.9% of total) → acceptable
- 512 MB: 14.5 ms stall (4.0% of total) → excellent

Compare to mmap reactive: stall = page fault time × misses
  - mmap: ~300µs × large misses → unpredictable
  - Our system: 14.5 ms predictable → better UX

## Throughput

| Config | Tokens/sec | Words/min (est.) |
|--------|-----------|-----------------|
| 256 MB LRU | 2.63 | ~790 (at 5 words/token) |
| 512 MB LRU | 2.73 | ~820 |
| **512 MB LFU** | **2.74** | **~822** |

All >2.5 tok/s ✅ — พอใช้ได้สำหรับ offline/assisted use

## Key Insight: Predictor Accuracy = Next Lever

Current bottleneck: **predictor accuracy 6.1%**

If predictor improves to:
| Accuracy | Est. Buffer Hit | Est. Stall | Est. tok/s |
|----------|----------------|------------|-----------|
| 6% (now) | 78% | 14.5 ms | 2.74 |
| 50% | 88% | ~8 ms | ~2.85 |
| 90% | 95% | ~3 ms | ~2.92 |

🚀 **MLP predictor (PreScope-style) = biggest performance gain available**

## Update: Timing Model Validation

Assumption in ARCHITECTURE.md:
> I/O (4.6ms) << Compute (350ms) → I/O latency hidden

✅ **Confirmed.** Even at worst case (256 MB, 30.2 ms stall), I/O is only 8% of total time.

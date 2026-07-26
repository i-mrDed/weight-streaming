# EXP-002: Predictor Accuracy Simulation — Results

## Setup

| Parameter | Value |
|-----------|-------|
| Access pattern | K3-realistic (shared experts/token, 90% inter-layer similarity) |
| Experts | 896 total, 16 active/token, 80 layers |
| Tokens | 1000 (incl. 10 warmup) |
| Buffer | 512 MB (128 shards @ 4 MB) |
| Predictor window | 64 experts predicted per token |
| Sweep | Accuracy 10-90% + perfect, 2 eviction policies |

## Raw Output

```
Accuracy | Actual  | B.Hit(LFU) | t/s(LFU) | B.Hit(LRU+P) | t/s(LRU+P)
---------+---------+------------+----------+--------------+-----------
    10%  |  10.0%  |     76.2%  |    2.73  |       29.9%  |     2.52
    20%  |  20.0%  |     76.2%  |    2.73  |       22.3%  |     2.49
    30%  |  30.0%  |     76.2%  |    2.73  |       22.1%  |     2.49
    40%  |  40.0%  |     76.2%  |    2.73  |       18.3%  |     2.47
    50%  |  50.0%  |     76.2%  |    2.73  |       19.2%  |     2.48
    60%  |  60.0%  |     76.2%  |    2.73  |       19.0%  |     2.48
    70%  |  69.9%  |     76.2%  |    2.73  |       17.5%  |     2.47
    80%  |  80.0%  |     76.2%  |    2.73  |       16.2%  |     2.46
    90%  |  90.0%  |     76.2%  |    2.73  |       17.2%  |     2.47
Perfect | 100.0%  |       n/a  |     n/a  |       15.5%  |     2.46
```

## Baseline References

| Configuration | Buffer Hit | Tokens/sec |
|--------------|-----------|------------|
| LFU 512 MB, shared access | 76.2% | 2.73 |
| LFU 512 MB, independent access | 78.2% | 2.74 |
| Hot expert hit rate (LFU) | 93.6% | — |
| Cold expert hit rate (LFU) | 14.9% | — |

## Key Measurements

### Impact on Overlap Efficiency (LFU, sweep extremes)
- **10% accuracy**: 30.9 ms overlap, 15.8 ms stall, 365.8 ms total, **2.73 t/s**
- **90% accuracy**: 233.8 ms overlap, 15.8 ms stall, 365.8 ms total, **2.73 t/s**
- Overlap improved 7.6x but throughput unchanged — **compute dominates** (350 ms/token)

## Files

- `setup.md` — experiment configuration
- `results.md` — this file
- `analysis.md` — interpretation and design implications

# EXP-001: Raw Results

## Sweep: Buffer Size vs Hit Rate

### LRU

| Buffer | Hit Rate | Evictions | Note |
|--------|----------|-----------|------|
| 64 MB | 29.6% | 780,267 | buffer overload |
| 128 MB | 44.4% | 615,555 | |
| **256 MB** | **60.9%** | 433,540 | **design target** |
| 512 MB | 76.1% | 264,908 | near target |
| 1024 MB | 86.0% | 154,885 | target met |

### LFU

| Buffer | Hit Rate | Evictions |
|--------|----------|-----------|
| 64 MB | 23.1% | 851,858 |
| 128 MB | 42.6% | 635,643 |
| **256 MB** | **63.1%** | 408,448 |
| **512 MB** | **78.2%** | 241,931 | **Best overall** |
| 1024 MB | 85.2% | 164,277 |

### LRU+Priority (custom)

| Buffer | Hit Rate | Evictions |
|--------|----------|-----------|
| 64 MB | 38.9% | 676,490 |
| 128 MB | 45.8% | 600,364 |
| 256 MB | 54.6% | 503,341 |
| 512 MB | 69.2% | 341,288 |
| 1024 MB | 83.6% | 181,463 |

## Detailed: 512 MB LFU (Best Config)

| Metric | Value |
|--------|-------|
| **Buffer hit rate** | **78.2%** |
| Hot expert hit rate | 97.3% |
| Cold expert hit rate | 9.2% |
| Predictor accuracy | 6.1% (heuristic) |
| Avg latency/token | 364.5 ms |
| Stall due to miss | 14.5 ms |
| I/O overlap | 279.5 ms |
| **Tokens/sec** | **2.74** |

## Detailed: 256 MB LRU (Design Default)

| Metric | Value |
|--------|-------|
| **Buffer hit rate** | **60.9%** |
| Hot expert hit rate | ~85% |
| Predictor accuracy | 6.1% |
| Avg latency/token | ~380 ms |
| Stall due to miss | ~30 ms |
| **Tokens/sec** | ~2.63 |

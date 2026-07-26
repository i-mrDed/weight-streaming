# EXP-001: Buffer Size & Eviction Policy Simulation

**วันที่:** 2026-07-27  
**สถานะ:** ✅ Complete  
**Related ADR:** ADR-001 (3-Layer Architecture)

---

## Hypothesis

1. 256 MB buffer ก็เพียงพอสำหรับ hit rate >80%
2. LRU+priority (custom policy) > plain LRU for MoE workload
3. Hot experts จะมี hit rate สูงกว่า cold experts อย่างมีนัยสำคัญ

## Setup

| Parameter | Value |
|-----------|-------|
| Model | K3-sim (896 experts, 16 active/token, 80 layers) |
| Workload | Zipf(0.9) + temporal locality 0.3 |
| Tokens | 1000 (simulated) |
| Buffer sizes | 64, 128, 256, 512, 1024 MB |
| Eviction policies | LRU, LFU, LRU+priority |
| Predictor | heuristic (frequency + temporal, ~6% accuracy) |
| NVMe speed | 14 GB/s (PCIe 5.0) |

## Method

- Python simulator (simulator/access_pattern.py, buffer.py, predictor.py)
- Each config run: 1000 tokens × 80 layers = 80,000 expert access events
- Cold start: 10 warmup tokens discarded

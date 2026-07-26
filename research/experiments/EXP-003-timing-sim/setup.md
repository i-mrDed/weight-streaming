# EXP-003: Timing & Overlap Efficiency

**วันที่:** 2026-07-27  
**สถานะ:** ✅ Complete (partial — embedded in EXP-001)  

---

## Hypothesis

1. Overlap efficiency >70% — I/O ทำงานขนานกับ compute ได้ดี
2. Stall <20ms ต่อ token — miss penalty ไม่กระทบ user experience มาก
3. Throughput >2.5 tok/s — พอใช้ได้

## Setup

| Parameter | Value |
|-----------|-------|
| NVMe sequential | 14 GB/s (PCIe 5.0) |
| NVMe random read | 60 µs (4KB) |
| Compute per token | 350 ms (target) |
| Draft head | 3 ms |
| Predictor | 2 ms |
| Scheduler overhead | 0.5 ms |
| Shard size | 4 MB |
| Emergency miss penalty | 60 µs per random read |

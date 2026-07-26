# EXP-002: Predictor Accuracy Impact

**วันที่:** 2026-07-27  
**สถานะ:** 🟡 Partial (ต้องปรับ access model ให้สมจริงขึ้น)  

---

## Hypothesis

1. Predictor accuracy >50% → buffer hit rate >85%
2. Heuristic predictor ให้ ~60% buffer hit rate ที่ 512 MB
3. MLP predictor (90%+ accuracy) → buffer hit rate ~92-95% ที่ 256 MB

## Current Findings (from EXP-001)

| Predictor | Accuracy | Buffer Hit Rate (512 MB LFU) |
|-----------|----------|-----------------------------|
| Heuristic (frequency+temporal) | 6.1% | 78.2% |
| Random baseline (16/896) | 1.8% | ~75% (estimated) |
| Perfect (all-seeing) | N/A | simulation issue |

## Limitation

Access pattern generator สร้าง experts per-layer ที่ต่างกัน → working set ใหญ่เกินจริง
ใน K3 จริง, experts มี correlation ข้าม layers → perfect predictor น่าจะได้ hit rate >90%

## TODO

- [ ] ปรับ access pattern ให้มี per-token expert sharing (same experts across layers)
- [ ] ทดสอบ MLP predictor simulation (accuracy sweep: 50%, 70%, 90%)
- [ ] วัด: predictor accuracy → buffer hit rate curve

# EXP-001: Analysis & Conclusions

## Finding 1: 256 MB Buffer ยังไม่พอ — ต้อง 512 MB

**Assumption ใน ADR-001:** 256 MB + predictor >80% → hit rate >80%  
**Actual result:** 256 MB + heuristic predictor → hit rate 60.9%  
**Best at 256 MB:** LFU → 63.1%

**Reality check:** 256 MB = 64 shards, แต่ working set ของ 80 layers ต่อ token = ~800-1200 unique experts → buffer thrashing

**Revised recommendation:** 
- **512 MB เป็น default** — LFU 78.2% hit rate
- **256 MB เป็น minimum** — ยอมรับ hit rate ~60% ได้ถ้า RAM constraint แน่น

## Finding 2: LFU > LRU สำหรับ MoE Workload

MoE expert distribution มีความ **skewed สูง**:
- 10% hot experts → 78% of traffic
- LFU เก็บ hot experts ไว้อย่างดี (97.3% hot hit rate)
- LRU เสียเปรียบเพราะ hot experts ถูก evict เมื่อ temporary burst หายไป

**Decision:** เปลี่ยน default eviction policy จาก LRU เป็น **LFU**

## Finding 3: LRU+Priority ต้องมี Predictor ที่ดีพอ

- Heuristic predictor (6% accuracy) → priority boost = noise
- LRU+priority → worse than plain LRU at 256-512 MB
- **ต้องมี predictor accuracy >30% ก่อน priority boost มีประโยชน์**

## Finding 4: Hot Expert Caching สำเร็จ

| Policy | Hot Hit Rate |
|--------|-------------|
| LRU 512 MB | 90.9% |
| LFU 512 MB | **97.3%** |
| LRU+Priority 512 MB | ~95% |

Hot expert caching ใช้ได้ดี — หมายความว่าสำหรับ experts ที่ถูกเรียกบ่อย ระบบ pre-fetch แทบไม่ต้องทำงาน

## Finding 5: Timing — Stall ต่ำ

**ด้วย predictor accuracy แค่ 6%** (เกือบ random):
- 512 MB LFU → **14.5 ms stall** ต่อ token (จาก 365 ms total)
- Overlap efficiency: 279.5 / 365 = **76.6%**

→ Overlap ทำงานได้ดี แม้ predictor จะแย่ — เพราะ NVMe bandwidth สูง

## Implications for Design

| Design Decision | Previous (ADR-001) | Updated (After EXP-001) |
|----------------|-------------------|------------------------|
| Default buffer size | 256 MB | 512 MB |
| Eviction policy | LRU+priority | LFU (default), LRU (fallback) |
| Priority boost | on by default | off until predictor >30% |
| Expected hit rate | 80% at 256 MB | 78.2% at 512 MB (heuristic) |
| Predictor priority | medium | **high** — best leverage for hit rate improvement |

## Next Steps

- [ ] EXP-002: ทดสอบ MLP predictor (จำลอง accuracy ที่ 70-95%)
- [ ] อัปเดต ARCHITECTURE.md buffer spec
- [ ] ทดสอบด้วย per-layer expert sharing (more realistic K3)

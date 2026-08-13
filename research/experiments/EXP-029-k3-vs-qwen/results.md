# EXP-029 — Results: K3 (>RAM) vs Qwen real, Phase 4 metrics

**Date:** 2026-08-13 · **Simulator:** K3 (896 experts, 16 active, 50B
active/token = 15.6 GB/token) · **Qwen ref:** EXP-028 real (22.73 tok/s)

## Headline comparison (256 MB buffer, 1000 tokens)

| metric | Qwen real (EXP-028) | K3 sim (this run) |
|--------|--------------------:|------------------:|
| tok/s | 22.73 | **0.049** |
| hit rate | 1.000 | **0.512** |
| p50 (ms) | 41.3 | **21,300** (21.3 s) |
| p90 (ms) | 48.6 | 27,051 |
| p99 (ms) | 69.6 | 31,258 |
| max (ms) | 222.8 | 35,449 |

**Qwen พอดี RAM = 22.7 tok/s (compute-bound) แต่ K3 ที่ 51% hit rate =
0.049 tok/s — ช้ากว่า ~465 เท่า** เพราะ miss 49% × 15.6 GB/token ไหลจาก
disk-mmap 0.38 GB/s (cold-fault path ไม่ใช่ NVMe seq spec — EXP-012/025)

## Buffer sweep: hit rate → throughput

| buffer MB | hit rate | predicted tok/s | stall ms/tok |
|----------:|---------:|----------------:|-------------:|
| 64 | 0.3355 | 0.036 | 27,322 |
| 128 | 0.4556 | 0.044 | 22,384 |
| 256 | 0.5118 | 0.049 | 20,075 |
| 512 | 0.6019 | 0.059 | 16,370 |
| 1024 | 0.7785 | 0.103 | 9,108 |
| **4096** | **0.9992** | **1.180** | **33** |
| 16384 | 0.9992 | 1.180 | 33 |

## Analysis

1. **ผลลัพธ์คือ curve ที่ไม่เชิงเส้นสุดขั้ว:** buffer 256 MB (ค่าเริ่มต้น
   ของ EXP-001) → 51% hit → **0.049 tok/s** (I/O-bound เกือบเต็มที่);
   buffer 4 GB → 99.9% hit → **1.18 tok/s** (= compute ceiling ที่ EXP-004
   ประเมินไว้ 815 ms/token) — **ต้อง hit ≥ 99% ถึงจะถึง compute ceiling**
   (ตรง EXP-026 insight: "แม้ 4% miss ก็ครอง throughput")

2. **ตรงกับ EXP-027 anchor:** 5% miss → stall ≈ 2.1 s > compute 815 ms —
   ยืนยันว่า K3 เป็น I/O-bound จริงที่ miss rate ต่ำมากแล้ว; buffer
   ขนาดพอเหมาะ (≥ 4 GB สำหรับ workload นี้) คือกุญแจ ไม่ใช่ predictor
   (ตรง ADR-003/EXP-002)

3. **Latency tail คือสัญญาณของ miss:** per-token distribution มี tail
   (p99 = 31 s vs p50 = 21 s) — token ที่ miss เยอะ stall ยาว; ถ้า
   ต้องการ latency SLA ต้องควบคุม miss rate ต่อ token ไม่ใช่แค่เฉลี่ย

4. **ตัวเลข Qwen vs K3 ต่างกัน ~465 เท่า** แม้ใช้ metric + physics ชุด
   เดียวกัน — ตอกย้ำว่าโปรเจคต้องแก้โจทย์ >RAM จริง (buffer + prefetch)
   ถึงจะเปลี่ยน 0.049 → 1.18 tok/s (24×) ซึ่งเป็น upside ที่แท้จริง

## Conclusion

Phase 4 metrics ใช้ได้กับทั้งกรณี fits-RAM (Qwen จริง) และ >RAM (K3 sim)
— ตารางเดียวเปรียบเทียบได้ชัดเจน: **buffer ขนาดพอดี = 24× throughput
(0.049 → 1.18 tok/s) บน K3**; นี่คือตัวเลขหลักฐานที่ paper ต้องมี

## Verification

- `tests/test_k3_vs_qwen.py`: 8/8 ผ่าน (K3 active-set, compute 815ms,
  I/O-bound ที่ 50% hit, 5% miss = 2056ms anchor, tail distribution)
- ทั้งชุด hermetic: (รันเต็มด้านล่าง)

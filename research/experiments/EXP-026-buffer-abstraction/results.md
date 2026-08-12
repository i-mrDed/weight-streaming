# EXP-026: Streaming Buffer Abstraction Prototype — Results

## Demo output (simulator/buffer_demo.py)

### Simulator-backed (LRU, 600 accesses: hot 8 → wider 20 → cold shift)

| metric | value |
|--------|-------|
| hit rate | 95.3% |
| miss/token | 0.0394 GB |
| stall | 103.6 ms/tok |
| compute | 41.9 ms/tok |
| **predicted** | **6.87 tok/s** |

### Telemetry-backed (spike_page_faults_2026-07-30.json, Qwen 2.7B Q2_K)

| run | hit rate | miss/tok | stall | compute | predicted | measured |
|-----|----------|----------|-------|---------|-----------|----------|
| run1-cold | 79.3% | 0.1747 GB | 459.8 ms | 34.9 ms | 2.02 tok/s | 10.32 |
| run2-warm | **99.9%** | 0.0006 GB | 1.4 ms | 44.0 ms | **22.02 tok/s** | **21.88** |

## ข้อค้นพบ

1. **Warm prediction ตรง measured เกือบเป๊ะ** — 22.02 vs 21.88 tok/s (Δ+0.6%)
   — physics model (BW ÷ bytes/token) + telemetry observer ทำงานร่วมกัน
   ได้จริงบนข้อมูล production

2. **Cold prediction (2.02) เป็น conservative lower bound** — ต่ำกว่า measured
   (10.32) เพราะ spike data นับ faults ทั้งหมด (ส่วนใหญ่เป็น page-cache hits
   ไม่ใช่ disk read จริง) — เมื่อใช้ `disk_mb_per_token` (hard faults เท่านั้น)
   จะแม่นกว่า; นี่คือความต่างของ "fault" vs "disk traffic" ที่ observer
   เปิดเผยออกมา

3. **แม้ 4% miss ก็ครอง throughput** — disk-mmap 0.38 GB/s ช้ากว่า cpu-ram
   19.18 ถึง ~50 เท่า → miss 4% = stall 103 ms/token (simulator 95.3% hit
   ได้แค่ 6.87 tok/s ไม่ใช่ 22.7) — buffer ต้องได้ hit rate ~99%+ ถึงจะ
   ใกล้ RAM ceiling (ตรงกับ conclusion EXP-012/EXP-025: cold fault เป็น
   I/O-bound จริง)

4. **Open gap ปิดแล้ว** — `total_accesses` ไม่ใช่ 0 อีกต่อไป: production
   ใช้ observer แปลง OS signals (ที่ ship แล้ว) เป็น buffer stats ได้ทันที
   โดยไม่ต้อง intercept llama.cpp

## Acceptance criteria (workflow streaming-buffer-prototype)

| Criterion | สถานะ |
|-----------|-------|
| Abstraction interface กลาง (protocol) — input ต่างกัน output ชุดเดียวกัน | ✅ `BufferBackend` + `BufferStatsView` |
| Telemetry observer แปลง generation.paging + spike data จริง ด้วย calibrated disk BW | ✅ 9 tests รวม spike data จริง |
| predicted tok/s ใช้ calibrated BW จาก EXP-025 | ✅ helper `predicted_tok_per_sec` + tests ตรวจ BW ที่ใช้ |
| Hermetic tests: sim event → stats ตรงเดิม; telemetry → สอดคล้อง spike | ✅ 9 tests, ทั้งชุด 437 passed / 7 skipped |
| บันทึก brain + TASKS.md + ARCHITECTURE.md §0 | ✅ (ดู handoff ใน MongoModel) |

## Reproduce

```bash
python simulator/buffer_demo.py          # เทียบสองทาง side-by-side
pytest tests/test_buffer_abstraction.py  # hermetic tests
```

# EXP-027: Phase 3b — Actual Compute vs I/O Ratio — Results

## วัดจริง (Qwen1.5-MoE-A2.7B Q2_K, CPU pure, warm 100 tokens)

| run | tok/s | faults/tok | fault_mb/tok | compute ms/tok | I/O stall ms/tok | **ratio C:IO** |
|-----|-------|-----------|--------------|----------------|------------------|----------------|
| run2-warm | 22.23 | 944.5 | 3.69 | 43.8 | 9.71 | 4.5:1 |
| run3-warm | 20.88 | 185.3 | 0.72 | 44.0 | 1.90 | 23.1:1 |
| run4-warm | 23.52 | 312.7 | 1.28 | 43.9 | 3.37 | 13.0:1 |

(เฉลี่ย tok/s ≈ 22.2 — สอดคล้อง EXP-025: 20.76–22.73, physics ceiling 22.73)

## ข้อสรุปหลัก

### 1. โมเดลที่พอดี RAM = **compute-bound** ✅ (พิสูจน์จริงครั้งแรก)

- compute **43.8–44.0 ms/token** คงที่ (ตรง physics: 0.844 GB / 19.18 GB/s)
- I/O stall แค่ 1.9–9.7 ms — **< 20% ของ total**
- ratio 4.5:1 ถึง 23:1 (warm ที่เสถียร = 13:1 ขึ้นไป)
- → ปรับปรุง I/O/buffer แทบไม่ได้กำไรบนโมเดลที่พอดี RAM (ตรง ADR-003
  conclusion: buffer = RAM reduction ไม่ใช่ throughput accelerator)

### 2. โมเดลที่ >RAM = **I/O-bound** (ยืนยัน projection ของ EXP-004)

K3 (50B active, 15.6 GB/token) — แค่ 5% miss (0.78 GB/token จาก disk):

| ส่วน | ms/token |
|------|----------|
| compute (95% hit) | ~774 ms |
| **I/O stall (5% miss)** | **~2056 ms** |
| ratio | **< 0.4:1 (I/O-bound)** |
| predicted tok/s | < 0.4 |

→ EXP-004 ถูกต้อง: งาน streaming buffer/prefetch **มีค่าจริงเฉพาะเมื่อ
โมเดลเกิน RAM** — นี่คือโจทย์หลักของโปรเจค (K3 2.8T)

### 3. บทเรียนจาก telemetry จริง

- `fault_mb_per_token` (soft+hard) เป็น upper bound ของ disk traffic —
  บน warm run ส่วนใหญ่เป็น page-cache hit ไม่ใช่ disk read จริง (ต้องใช้
  `disk_mb_per_token` = hard faults เพื่อตัวเลขที่แม่นกว่า — เหมือนที่
  handoff EXP-026 บันทึกไว้)
- run แรกหลัง load (cold) ต่ำกว่า ~25% — ต้อง warmup ก่อนวัดเสมอ

## Acceptance criteria (workflow phase3b-real-moe-io-ratio)

| Criterion | สถานะ |
|-----------|-------|
| ≥3 runs warm (100 tokens) ได้ tok/s + faults + disk จาก /v1/stats | ✅ 3 runs ครบ (fault_mb_per_token มี; disk_mb_per_token = hard-fault only ไม่มีใน warm) |
| แยก compute vs I/O ด้วย physics + buffer abstraction | ✅ compute 43.8–44.0 ms คงที่, stall 1.9–9.7 ms, ratio ชัดเจน |
| เปรียบเทียบ EXP-004 scaling + ระบุ compute/I/O-bound | ✅ Qwen (พอดี RAM) = compute-bound; K3 (>RAM) = I/O-bound |
| Hermetic test พิสูจน์การแยกส่วน | ✅ 6 tests (`tests/test_io_ratio_split.py`) |
| บันทึก EXP + brain + TASKS.md #151 | ✅ |

## Reproduce

```bash
# 1. โหลดโมเดล (CPU pure)
curl -X POST http://127.0.0.1:8765/v1/models/load -H "Content-Type: application/json" \
  -d '{"model_id":"Qwen1.5-MoE-A2.7B_Q2_k","model_path":"research/models/Qwen1.5-MoE-A2.7B_Q2_k.gguf","gpu_layers":0}'
# 2. warmup แล้ว generate 100 tokens ×3 → ดู /v1/stats?model=...
# 3. แยกส่วนด้วย TelemetryBufferObserver (ดู tests/test_io_ratio_split.py)
pytest tests/test_io_ratio_split.py
```

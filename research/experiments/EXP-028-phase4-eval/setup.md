# EXP-028 — Phase 4: Evaluation metrics + real benchmark

**Date:** 2026-08-13 · **Status:** done · **Workflow:** `phase4-evaluation` (MongoModel rev 43)

## Purpose

ปิด TASKS.md Phase 4 (4 งาน): Define evaluation metrics + Benchmark hit
rate / latency distribution / throughput — บน real MoE (Qwen1.5-MoE-A2.7B
Q2_K, CPU pure) ผ่าน server :8765 โดยใช้ชุดเครื่องมือที่ calibrate แล้ว
(EXP-025 physics model + EXP-026 buffer abstraction + EXP-027 IO ratio)

## Metrics spec (นิยาม + หน่วย + เกณฑ์ผ่าน)

### 1. Hit rate — สัดส่วน bytes/token ที่ได้จาก RAM (ไม่ต้อง fault จาก disk)

- **นิยาม:** `hit_rate = 1 - disk_mb_per_token / bytes_per_token_mb`
  - `disk_mb_per_token` = hard-fault demand จาก `generation.paging`
    (telemetry ที่ ship แล้ว; `None`/0 = โมเดล resident ครบ = 1.0)
  - `bytes_per_token_mb` = physics active-set (EXP-025):
    Qwen 2.7B × 2.5 bpw = **864 MB/token**
- **หน่วย:** fraction 0–1
- **เกณฑ์ผ่าน:** warm ≥ 0.90 (โมเดลพอดี RAM); ค่า cold ต่ำกว่าเป็นเรื่อง
  ที่คาดหวัง (I/O-bound ชั่วคราว) — รายงานทั้งสอง

### 2. Latency distribution — per-token generation latency

- **นิยาม:** inter-chunk arrival time จาก SSE stream (1 chunk = 1 token)
  หน่วย ms; รายงาน **p50 / p90 / p99 / mean / max** (nearest-rank)
- **เกณฑ์ผ่าน:** p99 < 3× p50 (ไม่มี long-tail stall รุนแรง — ถ้า disk
  fault ขึ้นมาบน token ใด p99 จะพุ่ง)

### 3. Throughput — tok/s vs physics prediction

- **นิยาม:** `tok/s` จาก `/v1/stats` เทียบ `predicted = BW_cpu-ram /
  bytes_per_token` (EXP-025: 19.18 GB/s ÷ 0.844 GB = 22.73 tok/s);
  `error = (measured - predicted) / predicted`
- **เกณฑ์ผ่าน:** error อยู่ภายใน **±15%** (tolerance เดียวกับที่
  EXP-025 validate กับ hardware จริง)

## Method

1. ใช้ server ที่รันอยู่ (no clean-room restart — เหมือน EXP-025 validation)
2. warmup 1 request สั้น ๆ → วัด 3 runs × 100 tokens (stream, temp 0.7)
3. แต่ละ run: capture per-token latency จาก SSE + อ่าน `/v1/stats`
   (`tokens_per_sec` + `generation.paging`)
4. คำนวณ metrics ด้วย `weight_stream/eval/metrics.py` (pure, hermetic-testable)
5. รายงานแบบ JSON + ตาราง

## Files

- `weight_stream/eval/metrics.py` — metric definitions (pure functions)
- `scripts/bench_phase4.py` — benchmark harness (stream + telemetry + compute)
- `tests/test_eval_metrics.py` — hermetic tests ของ metric computation
- `raw_bench.json` — raw measurement (3 runs)

## Reproduce

```bash
python scripts/bench_phase4.py --runs 3 --tokens 100 --json \
    research/experiments/EXP-028-phase4-eval/raw_bench.json
pytest tests/test_eval_metrics.py
```

# EXP-030 — Test llama.cpp expert offloading on the PoC model (Qwen, fits VRAM)

**Date:** 2026-08-13 · **Status:** done · **TASKS.md:** "Test llama.cpp
expert offloading" (Phase 1, งานสุดท้ายที่ค้าง)

## Purpose

ทดสอบ llama.cpp expert offloading (`--n-cpu-moe`) บน **PoC model
(Qwen1.5-MoE-A2.7B Q2_K, 5.88 GB — พอดี VRAM 12 GB ทั้งหมด)** — ต่อจาก
EXP-005/007/011 ที่ครอบกรณี >VRAM (35B-A3B) — เพื่อตอบว่า "โมเดลที่พอดี
VRAM แล้ว offload experts ไป CPU ช่วยหรือแย่ลง"

## Method

- โหลดผ่าน API server (`/v1/models/load` + `extra_args`) ต่อ config
- **ไม่ restart server** (เป็น server ของ user — ใช้วิธีเดียวกับ
  EXP-025/027/028 ที่วัดผ่าน server ที่รันอยู่)
- แต่ละ config: warmup → 3 runs × 100 tokens → อ่าน `/v1/stats`
  (tok/s + paging + VRAM)
- คืนค่า baseline ให้ server หลังจบ (unload + reload ไม่มี extra args)

Configs:
1. `baseline` — ไม่มี extra args (server default / auto placement)
2. `n-cpu-moe 10` — บังคับ 10 expert layers ไป CPU (offload ไป RAM)
3. `n-cpu-moe 0` — experts ทั้งหมดอยู่ GPU (best case ของ EXP-011)

## Files

- `scripts/bench_expert_offload.py` — harness
- `tests/test_expert_offload.py` — 4 hermetic tests (physics ของ offload)
- `raw_bench.json` — raw measurement

## Reproduce

```bash
python scripts/bench_expert_offload.py --runs 3 --json \
    research/experiments/EXP-030-expert-offload/raw_bench.json
pytest tests/test_expert_offload.py
```

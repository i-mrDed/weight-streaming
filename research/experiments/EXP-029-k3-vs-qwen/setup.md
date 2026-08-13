# EXP-029 — K3 (>RAM) benchmark with Phase 4 metrics, vs real Qwen

**Date:** 2026-08-13 · **Status:** done · **Workflow:** `phase4-evaluation` (ขยาย)

## Purpose

Phase 4 (EXP-028) วัด Qwen จริงและได้ "compute-bound" story — แต่ Qwen
**พอดี RAM** (5.88 GB) เป้าหมายจริงของโปรเจคคือ **K3** (~2.8T params, 50B
active/token = 15.6 GB/token) ซึ่ง **ไม่พอดี RAM** งานนี้ใช้ Phase 4
metrics ชุดเดียวกันกับ K3 simulation เพื่อให้ตัวเลขเทียบกันได้โดยตรง

## Method

1. รัน K3 simulator เดิม (EXP-001/002/003: `run_simulation`) เก็บ
   **per-token hit/miss** (เพิ่ม option `collect_per_token` แบบ
   backward-compatible)
2. ใช้ Phase 4 metric definitions (`weight_stream.eval.metrics`) เดิม
   เป๊ะ:
   - **hit rate** — จาก `StreamingBuffer` (LRU + priority boost)
   - **latency distribution** — per-token: `compute 815ms + miss_fraction ×
     15.6GB / disk-mmap 0.38 GB/s` (EXP-026 สูตร stall เดียวกับที่ Qwen
     ใช้กับ real telemetry)
   - **throughput** — `predicted_tok_per_sec(hit_rate)` จาก EXP-026
     (hit bytes @ cpu-ram + miss bytes @ disk-mmap)
3. เทียบกับ Qwen real (EXP-028) ในตารางเดียวกัน

## Files

- `scripts/bench_k3_sim.py` — benchmark (hit rate → latency → throughput)
- `simulator/run.py` — เพิ่ม `collect_per_token` (ไม่เปลี่ยน behavior เดิม)
- `tests/test_k3_vs_qwen.py` — 8 hermetic tests ของ K3 physics + metrics
- `k3_bench.json` — raw result (256 MB buffer, 1000 tokens)

## Reproduce

```bash
python scripts/bench_k3_sim.py --tokens 1000 --buffer-mb 256 --json \
    research/experiments/EXP-029-k3-vs-qwen/k3_bench.json
pytest tests/test_k3_vs_qwen.py
```

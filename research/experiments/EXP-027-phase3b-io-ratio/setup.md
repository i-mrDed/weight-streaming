# EXP-027: Phase 3b — Actual Compute vs I/O Ratio on Real MoE

**วันที่:** 2026-08-13
**สถานะ:** ✅ Complete (TASKS.md #151)
**Workflow:** `phase3b-real-moe-io-ratio` (MongoModel, rev 40)

---

## Hypothesis (จาก EXP-004)

EXP-004 คาดการณ์ว่า K3 (>RAM) จะ **I/O-bound** (NVMe 1786 ms > compute
815 ms) แต่ยังไม่เคยวัดจริงว่า per-token time บน real MoE แบ่งเป็น
compute vs I/O เท่าไหร่

## วิธีวัด

- โมเดล: `Qwen1.5-MoE-A2.7B_Q2_k.gguf` (5.88 GB, 2.7B active @ 2.5 bpw,
  0.84375 GB/token) — CPU pure (`ngl=0`), default threads, n_ctx=512
- เครื่อง: consumer PC (RTX 3060 12GB — ไม่ใช้ GPU, 64GB RAM)
- ช่องทาง: server :8765 `/v1/chat/completions` + `/v1/stats`
  (`generation.paging`: faults_per_token, fault_mb_per_token)
- การแยกส่วน: **EXP-026 buffer observer** (`TelemetryBufferObserver`) —
  compute = bytes×hit / cpu-ram BW (19.18 GB/s), stall = miss / disk-mmap
  BW (0.38 GB/s) — calibrated จาก EXP-025

## ไฟล์

- `tests/test_io_ratio_split.py` — hermetic tests (6 ตัว)
- ใช้ `simulator/buffer_abstraction.py` (EXP-026) + `simulator/physics.py` (EXP-025)

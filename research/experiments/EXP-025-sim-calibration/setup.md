# EXP-025: Simulator Calibration via Physics Model (BW ÷ bytes/token)

**วันที่:** 2026-08-12
**สถานะ:** ✅ Complete (TASKS.md #96)
**Workflow:** `calibrate-simulator` (MongoModel, rev 28)

---

## Hypothesis

ตัวเลข timing ของ simulator (`compute_time_per_token_us`, NVMe BW) ควร
**derive จาก physics** ไม่ใช่ hardcode:

```
time_per_token = bytes_per_token ÷ effective_bandwidth
tok_per_sec    = effective_bandwidth ÷ bytes_per_token
```

โดย `effective_bandwidth` เป็น parameter เดียวที่ต้อง fit จากข้อมูลวัดจริง
— ตัวอื่น (bytes/token) มาจาก spec ของโมเดลล้วนๆ

## ข้อมูลวัดจริง (input)

| Source | Model | Tier | tok/s | หมายเหตุ |
|--------|-------|------|-------|----------|
| EXP-004 | Qwen1.5-MoE-A2.7B Q2_K | CPU (RAM) | 22.73 | 0.84375 GB/token วัดจริง |
| EXP-011 | Qwen1.5-MoE-A2.7B Q2_K | GPU (VRAM) | 56.4 / 72.4 | n-cpu-moe 10 / 0 |
| EXP-012 | DSv4 Flash 104GB | disk-mmap | 1.5–1.9 | 150–300 MB faulted/token |

## สิ่งที่สร้าง

- `simulator/physics.py` — physics model + calibrated BW ต่อ tier
- `simulator/calibrate.py` — CLI report (`--json` สำหรับ scripts/tests)
- `simulator/config.py` — `compute_time_per_token_us` derive จาก physics
- `tests/test_simulator_calibration.py` — hermetic tests (10 ตัว)

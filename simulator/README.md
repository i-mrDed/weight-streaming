# Simulator — Speculative Weight Streaming

> **用途:** จำลองและวัด performance ของ Speculative Weight Streaming  
> **ภาษา:** Python 3.10+ (ไม่ต้อง dependencies นอกเหนือจาก standard lib)  
> **รัน:** `python run.py --config config.json`

---

## Components

| Module | File | Purpose |
|--------|------|---------|
| **Config** | `config.py` | Simulation parameters |
| **Access Pattern** | `access_pattern.py` | สร้าง synthetic token workload |
| **Buffer** | `buffer.py` | Cache policy simulation |
| **Predictor** | `predictor.py` | Weight prediction models |
| **Timing** | `timing.py` | I/O + compute latency model |
| **Runner** | `run.py` | Main simulation entry point |

## Experiment Directory

แต่ละ experiment เก็บใน `research/experiments/EXP-NNN/`:
- `setup.md` — config ที่ใช้
- `results.md` — raw output numbers
- `analysis.md` — สรุป findings

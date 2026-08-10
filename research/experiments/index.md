# Experiment Log

> **用途:** บันทึกการทดลองทุกครั้ง — รู้ hypothesis, setup, result, conclusion  
> **ต้องทำ:** ก่อนเริ่มทดลอง → สร้าง entry | หลังได้ผล → บันทึก result + analysis  
> **รูปแบบการตั้งชื่อ:** `EXP-NNN-description/`

---

## 🧪 การทดลองทั้งหมด

| # | วันที่ | หัวข้อ | สถานะ | สรุป |
|---|-------|--------|-------|------|
| 001 | 2026-07-27 | Buffer Size & Eviction Policy | ✅ Complete (v2) | v1 (simulated 350ms): LFU 512 MB → 78.2%. v2 (real 815ms): **LRU 64MB → 93.8%** for shared MoE |
| 002 | 2026-07-27 | Predictor Accuracy Impact | ✅ Complete (v2) | v1: 2.73 t/s flat. v2: 1.15-1.23 t/s, LRU flat at 98.9%, predictor still not critical |
| 003 | 2026-07-27 | Timing & Overlap Efficiency | ✅ Complete | 76.6% overlap efficiency (simulated), superseded by EXP-004 real data |
| 004 | 2026-07-27 | Real MoE Hardware Benchmark | ✅ Complete | K3: 815ms compute vs 67ms max I/O stall → ~92% compute-bound. LRU 64MB sufficient |
| 005 | 2026-08-06 | GPU `--cpu-moe` Tiering Proof | ⚠️ Invalidated | ⚠️ **Contaminated** — stale Jan Qwythos-9B answered on port 8805 (our backend's port). Real 35B + --cpu-moe = **~18.4 tok/s** (EXP-007), not 42-44. Mechanism still proven (experts stream from RAM) but numbers void |
| 006 | 2026-08-06 | CPU Thread Scaling | ⚠️ Invalidated | ⚠️ **Contaminated** — measured a stale Jan Qwythos-9B (dense, GPU-resident) squatting on port 8805, not the 35B. See EXP-007. Real 35B + --cpu-moe: threads 8 is fine, but 42-46 tok/s claim is void |
| 007 | 2026-08-06 | Context (KV Cache) Scaling | ✅ Complete | Real 35B-A3B + --cpu-moe: **18.4 tok/s flat** across 2048/8192/32768 ctx; KV cache mostly in host RAM (+637 MiB VRAM for 16× ctx, not +5 GB). Also exposed the EXP-005/006 stale-server contamination |
| 008 | 2026-08-06 | `--n-cpu-moe` Expert Offload Matrix | ✅ Complete | Clean sweep (orphan-guarded, flag-verified): `--cpu-moe` 17.9 → `--n-cpu-moe 20` 33.8 → **10: 44.5** → **0: 53.9 tok/s** (3×). VRAM 3.9→11.3 GB. Sweet spot on 12 GB = `--n-cpu-moe 10` (44.5, 88%). **Re-validated 2026-08-06 ผ่าน clean-room gate: 17.9 / 33.9 / 47.2 / 56.4 tok/s** |
| 009 | 2026-08-06 | KV Cache q8_0 vs f16 | ✅ Complete | **No-op บนเครื่องนี้ (~10 MiB VRAM, tok/s เท่าเดิม)** — ยืนยัน EXP-007: KV อยู่ RAM เป็นส่วนใหญ่ → quantize KV ไม่ช่วยบน 12 GB นี้ |
| 010 | 2026-08-06 | Speculative Decoding | ❌ Dead end (ที่พิสูจน์แล้ว) | Qwen3-0.6B draft ถูก reject: **vocab ไม่ตรง** (Qwen3 151k vs Qwen3.6 ~128k). ไม่มี Qwen3.6 เล็กบน HF. `ngram-simple` ≈ baseline. **ข้อค้นพบ:** build นี้ต้อง `--spec-type` (default none). สรุป: ไม่ใช่ lever สำหรับ bottleneck bandwidth นี้ |
| 011 | 2026-08-07 | Ultra-Low-Bit Quant (IQ1_M) | ✅ Complete | **พังเพดานครั้งแรก: 72.4 server / 77.6 raw tok/s** (n-cpu-moe 0 + IQ1_M 10.05 GB, VRAM 10.8 GB, p95 13.9ms) vs IQ2_M ceiling 56.4. ไฟล์เล็ก 1.5 GB → ทั้งโมเดลอยู่ใน VRAM จริง + expert bytes น้อยลง. **Quality eval: 8/9 มิติเท่ากัน แต่ Thai tonal classification พังทั้งชุด (79.1 vs 50.3 tok/s)** — verdict: ใช้ได้สำหรับแชททั่วไป, ต้อง IQ2_M สำหรับงานภาษาไทยที่พึ่งวรรณยุกต์ |
| 011b | 2026-08-07 | Hub download integrity bug | ✅ Fixed | **บั๊กตัวเลขปลอม:** task รายงาน done 10.05 GB แต่ไฟล์จริง 3.8 GB — loop ถือว่า EOF = สำเร็จ โดยไม่ตรวจ Content-Length + override bytes_downloaded = total. แก้ integrity gate (bytes ครบก่อน os.replace) + test ครอบ + resume ต่อจาก .part จน byte-exact 10,047,749,088 |

---

## 🔍 Clean-room gate (ตั้งแต่ EXP-009)

ทุกการวัดต้องผ่าน `scripts/check_clean_environment.py` ก่อน
(exit: `0` = clean, `1` = warn, `2` = **ห้ามวัด**) — บทเรียนจาก EXP-005/006
ที่ invalidate เพราะ stale server / port ชน โดย harness (`measure_*.py`)
เรียก gate นี้อัตโนมัติตอนเริ่ม

รายละเอียดเต็ม: [`CLEAN_ROOM_CHECKLIST.md`](CLEAN_ROOM_CHECKLIST.md)

---

## 📝 Template สำหรับการทดลองใหม่

```markdown
## EXP-001: [หัวข้อสั้น]

| รายการ | รายละเอียด |
|--------|-----------|
| **วันที่** | YYYY-MM-DD |
| **ผู้ทดลอง** | — |
| **สถานะ** | 🟡 Planned / 🔄 Running / ✅ Complete / ❌ Failed |
| **Related ADR** | ADR-NNN (ถ้ามี) |

### Hypothesis
สิ่งที่คาดว่าผลจะเป็น

### Setup
- **Model:** 
- **Hardware:** 
- **Parameters:**
  - Buffer size: 
  - Predictor: 
  - Workload: 
- **Metrics:** 

### Method
วิธีการทดลอง

### Results
```
raw data, logs, numbers
```

### Analysis
- สิ่งที่เห็น
- surprise findings
- comparison vs hypothesis

### Conclusion
- ข้อสรุป
- action items
- next experiment
```

---

## 📁 โครงสร้าง

```
experiments/
├── index.md              ← ไฟล์นี้ — สรุปรวมทุก experiment
└── EXP-NNN-description/  ← แต่ละ experiment
    ├── setup.md          ← config + parameters
    ├── results.md        ← raw data
    └── analysis.md       ← สรุป findings
```

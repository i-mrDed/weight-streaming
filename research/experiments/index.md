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

# Experiment Log

> **用途:** บันทึกการทดลองทุกครั้ง — รู้ hypothesis, setup, result, conclusion  
> **ต้องทำ:** ก่อนเริ่มทดลอง → สร้าง entry | หลังได้ผล → บันทึก result + analysis  
> **รูปแบบการตั้งชื่อ:** `EXP-NNN-description/`

---

## 🧪 การทดลองทั้งหมด

| # | วันที่ | หัวข้อ | สถานะ | สรุป |
|---|-------|--------|-------|------|
| 001 | 2026-07-27 | Buffer Size & Eviction Policy | ✅ Complete | LFU 512 MB → 78.2% hit rate |
| 002 | 2026-07-27 | Predictor Accuracy Impact | ✅ Complete | LFU flat (76.2%), LRU+P decays with accuracy (priority clogging), throughput compute-bound (2.73 t/s flat) |
| 003 | 2026-07-27 | Timing & Overlap Efficiency | ✅ Complete | 76.6% overlap efficiency, 2.74 tok/s |
| 004 | 2026-07-27 | Real MoE Hardware Benchmark | ✅ Complete | K3 I/O-BOUND: compute 815ms vs NVMe 1786ms. Predictor+buffer CRITICAL |

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

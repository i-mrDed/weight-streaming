# Experiment Log

> **用途:** บันทึกการทดลองทุกครั้ง — รู้ hypothesis, setup, result, conclusion  
> **ต้องทำ:** ก่อนเริ่มทดลอง → สร้าง entry | หลังได้ผล → บันทึก result + analysis  
> **รูปแบบการตั้งชื่อ:** `EXP-NNN-description/`

---

## 🧪 การทดลองทั้งหมด

| # | วันที่ | หัวข้อ | สถานะ | สรุป |
|---|-------|--------|-------|------|
| — | — | — | — | ยังไม่มีการทดลอง |

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

# Changelog — Speculative Weight Streaming

> รูปแบบ: [Semantic Versioning](https://semver.org/)  
> ทุกการเปลี่ยนแปลงต้องบันทึกในไฟล์นี้

---

## [0.3.0] - 2026-07-27

### 📚 Documentation System + Workflow

- **ติดตั้งระบบบันทึกที่เป็น workflow ถาวร** — ทุก session ต้องปฏิบัติตาม
- สร้าง `docs/WORKFLOW.md` — กำหนดกฎ mandatory สำหรับทุก session (start, during, end)
- สร้างระบบบันทึกและติดตามงานครบชุด

#### ระบบที่เพิ่ม

| ไฟล์ | Purpose |
|------|---------|
| `SESSION_LOG.md` | บันทึกทุก session — อ่านก่อนเริ่ม, เขียนเมื่อจบ |
| `docs/DECISIONS.md` | ADR — ตัดสินใจทางเทคนิคพร้อมเหตุผล |
| `docs/GLOSSARY.md` | รวมคำศัพท์ — ใช้คำเดียวกันทั้งโปรเจค |
| `TASKS.md` | Task board — backlog, in progress, done |
| `research/experiments/index.md` | Experiment log template + protocol |
| `docs/WORKFLOW.md` | **Workflow บังคับ** — ครอบคลุมทุก session |

#### Key workflows ที่กำหนด
- **Every Session Checklist:** Start (5 steps) + End (5 steps)
- **Decision Protocol:** ต้องบันทึก ADR เมื่อไหร่ + template
- **Experiment Protocol:** hypothesis → setup → result → conclusion
- **Problem Resolution Protocol:** symptom → root cause → solution → prevention

---

## [0.1.0] - 2026-07-27

### ✨ Initial Concept

- กำหนดแนวคิด **Speculative Weight Streaming** — รันโมเดล 2.8T+ บนเครื่องทั่วไป RAM 32–64 GB
- ออกแบบสถาปัตยกรรม 3-layer: Draft Model → Weight Predictor → Streaming Buffer
- วิเคราะห์ feasibility: bandwidth, latency, memory budget
- ระบุ novel contributions และ open problems
- บันทึกแนวทางเสริม: Computational Storage, Collaborative Inference, MoE Compression

#### ไฟล์ที่สร้าง
- `PROJECT.md` — ภาพรวมโครงการ
- `docs/CONCEPT.md` — Concept ฉบับสมบูรณ์
- `CHANGELOG.md` — ไฟล์นี้

---

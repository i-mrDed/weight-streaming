# Session Log — Speculative Weight Streaming

> **用途:** บันทึกการทำงานทุก session — session ถัดไปรู้ทันทีว่าค้างตรงไหน  
> **ต้องทำทุกรอบ:** ก่อนเริ่ม session → อ่าน entry ล่าสุด | หลังจบ session → เขียน entry ใหม่

---

## [S002] — 2026-07-27 — Setup Documentation System

**🎯 เป้าหมาย:** สร้างระบบบันทึกที่เป็น workflow ถาวรของโปรเจค

### ✅ สิ่งที่ทำ
- สร้างระบบบันทึกครบชุด: SESSION_LOG, ADR, GLOSSARY, TASKS, experiments, WORKFLOW
- กำหนด workflow ให้ AI และคนต้องทำทุก session

### ⚡ การตัดสินใจ
- **ไม่แก้ PROJECT.md ซ้ำซ้อน** — WORKFLOW.md แยกจาก concept
- ADR เป็นไฟล์เดียว (เรียงตามลำดับ) — ง่ายกว่าแยกไฟล์
- GLOSSARY เชื่อมกับทุก docs — ใช้คำศัพท์เดียวกันทั้งโปรเจค

### 🐛 ปัญหา / อุปสรรค
- (ไม่มี — เป็น session สร้างระบบ)

### ⏭️ ถัดไป
- Phase 1b: อ่าน PreScope paper + EAGLE-3 paper ฉบับเต็ม
- หรือเริ่ม Phase 2: Architecture Design

### 📎 อ้างอิง
- `docs/WORKFLOW.md` — workflow ที่ต้องปฏิบัติ
- `docs/DECISIONS.md` — ADR-001
- `TASKS.md` — task board ปัจจุบัน

---

## [S001] — 2026-07-27 — Initial Concept + Phase 1 Research

**🎯 เป้าหมาย:** กำหนดแนวคิดโปรเจค + ค้นคว้างานวิจัยที่เกี่ยวข้อง

### ✅ สิ่งที่ทำ
- ตั้ง Concept Speculative Weight Streaming
- Phase 1 Research Review ครบ 5 หมวด
- ขยายเป้าหมายจาก K3 สู่ cross-architecture
- สร้าง research/ structure

### ⚡ การตัดสินใจ
- **เลือก 3-layer architecture** (Draft Model → Weight Predictor → Streaming Buffer)
- **เริ่มที่ K3 ก่อน** แต่ framework ต้องรองรับทุก model
- **ไม่ใช้ near-storage computing** — รอ hardware 成熟

### ⏭️ ถัดไป
- ตั้งระบบบันทึกการทำงาน (กำลังทำใน S002)

### 📎 อ้างอิง
- `v0.1.0` — Concept + feasibility
- `v0.2.0` — Research Review

---

> **Template สำหรับ session ใหม่:**
> ```markdown
> ## [S000] — YYYY-MM-DD — [หัวข้อสั้น]
>
> **🎯 เป้าหมาย:** ...
>
> ### ✅ สิ่งที่ทำ
> - ...
>
> ### ⚡ การตัดสินใจ
> - ...
>
> ### 🐛 ปัญหา / อุปสรรค
> - ...
>
> ### ⏭️ ถัดไป
> - ...
>
> ### 📎 อ้างอิง
> - ...
> ```

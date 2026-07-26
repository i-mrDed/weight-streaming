# Session Log — Speculative Weight Streaming

> **用途:** บันทึกการทำงานทุก session — session ถัดไปรู้ทันทีว่าค้างตรงไหน  
> **ต้องทำทุกรอบ:** ก่อนเริ่ม session → อ่าน entry ล่าสุด | หลังจบ session → เขียน entry ใหม่

---

## [S004] — 2026-07-27 — Phase 3a: Prototype Simulator

**🎯 เป้าหมาย:** สร้าง Python simulator + รัน experiments วัด performance

### ✅ สิ่งที่ทำ
- สร้าง simulator framework ครบ 5 modules (600+ บรรทัด)
- EXP-001: Buffer size & eviction policy sweep → **พบว่า 512 MB + LFU = 78.2% hit rate**
- EXP-003: Timing + overlap efficiency → **76.7% overlap, 2.74 tok/s**
- EXP-002: Predictor — partial (ต้องปรับ access model)
- วิเคราะห์ findings: predictor accuracy = biggest performance leverage

### ⚡ การตัดสินใจ (อัปเดต)
- **เปลี่ยน buffer default จาก 256 MB → 512 MB** (จาก evidence)
- **เปลี่ยน default eviction จาก LRU+priority → LFU** (LFU > LRU สำหรับ MoE)
- **Priority boost ปิด** จนกว่า predictor accuracy >30%
- **RAM budget ยัง OK:** 512 MB buffer + draft head (~6 GB) + KV cache (~8 GB) = ~14.5 GB

### 🐛 ปัญหา / อุปสรรค
- Windows encoding (cp874) → emoji + special chars พิมพ์ไม่ได้ → แก้เป็น ASCII
- Access pattern per-layer independent → working set ใหญ่เกินจริง → ต้องปรับ

### ⏭️ ถัดไป
- [ ] EXP-002: ปรับ access model + ทดสอบ MLP predictor
- [ ] EXP-004: Per-layer expert sharing (K3 realistic)
- [ ] เลือก MoE model เล็กสำหรับ PoC + fork llama.cpp

### 📎 อ้างอิง
- `simulator/` — code ทั้งหมด
- `research/experiments/EXP-001-buffer-sim/` — buffer results
- `research/experiments/EXP-003-timing-sim/` — timing results

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

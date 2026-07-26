# Session Log — Speculative Weight Streaming

> **用途:** บันทึกการทำงานทุก session — session ถัดไปรู้ทันทีว่าค้างตรงไหน  
> **ต้องทำทุกรอบ:** ก่อนเริ่ม session → อ่าน entry ล่าสุด | หลังจบ session → เขียน entry ใหม่

---

## [S003] — 2026-07-27 — Phase 2: Architecture Design Complete

**🎯 เป้าหมาย:** ออกแบบสถาปัตยกรรมระบบ Speculative Weight Streaming ทั้ง 6 components

### ✅ สิ่งที่ทำ
- สร้าง `docs/ARCHITECTURE.md` ครอบคลุมทุก component:
  1. **NVMe Data Layout** — shard-based, popularity layout, O(1) metadata index
  2. **Weight Predictor** — MLP (PreScope-style, 2-layer, 2M params), heuristic fallback
  3. **Pre-fetch Scheduler** — priority queue, I/O batching, timing model, emergency handler
  4. **Streaming Buffer** — LRU+priority eviction, 256 MB default, cold start strategy
  5. **Execution Engine** — BufferReader + MmapFallback, framework-agnostic interface
  6. **Abstraction Layer** — plugin architecture รองรับ MoE/Dense/Hybrid
- Interface contracts ครบ: Predictor→Scheduler→Buffer→Engine
- Implementation roadmap สำหรับ Phase 3-4
- อัปเดต TASKS.md, CHANGELOG.md

### ⚡ การตัดสินใจ
- **เลือก MLP Predictor (PreScope-style)** — weighted sum + confidence
- **ไม่เลือก Extend EAGLE-3 head** — เก็บไว้เป็น future work (novel แต่เสี่ยงสูง)
- **Buffer default 256 MB** — sweet spot ของ RAM vs hit rate
- **Fork llama.cpp สำหรับ Phase 3** — มี MoE support พร้อม
- **Windows I/O: IOCP** — io_uring ไม่มีบน Windows

### ⏭️ ถัดไป
- Phase 3a: Prototype Simulator (Python)
  - create experiments/EXP-001-simulator
  - implement buffer simulator
  - implement heuristic predictor
  - run simulations with K3 access pattern

### 📎 อ้างอิง
- `docs/ARCHITECTURE.md` — design หลัก
- `docs/DECISIONS.md` — ADR-001, ADR-002
- `research/pre-scope/` — predictor reference

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

# 📚 Research Notes: WASTE vs Speculative Weight Streaming

> **Research Date:** 2026-08-03
> **เปรียบเทียบ:** [sqliteai/waste](https://github.com/sqliteai/waste) vs โปรเจค Speculative Weight Streaming (D:\.opencode\.Weight-Streaming)
> **คู่มือฉบับเต็ม:** `index.html` (เปิดดูใน browser)

---

## 🎯 สรุป verdict

| คำถาม | คำตอบ |
|--------|-------|
| **แนวคิดถูกทางไหม?** | ✅ **ถูกต้อง 100%** — Predict → Prefetch → Stream → Execute ตรงกับ WASTE ที่ทำสำเร็จ |
| **ตอนนี้ทำถูกที่ไหม?** | ⚠️ **กำลังเบน** — งาน dashboard/UI กำลังดึงออกจาก core engine |
| **ต้องปรับอะไร?** | 1. ตัดสินใจเป้าหมาย (research > product ก่อน) 2. ปิด gap `total_accesses=0` 3. ใช้ Kimi-Linear 48B แทน K3 ก่อน |
| **จุดแข็งที่ต้องรักษา** | วินัย honest telemetry + วิเคราะห์ bandwidth-bound ถูกต้อง + การบันทึก ADR |

---

## ⚖️ เปรียบเทียบแกนหลัก

| แกน | WASTE | โปรเจคคุณ | สถานะ |
|------|-------|-----------|-------|
| Core Engine | C ล้วน, custom, ควบคุมทุกอย่าง | Python + llama-cpp-python (opaque mmap) | ⚠️ ต่าง — ควบคุมการอ่านไม่ได้ |
| Container Format | Custom `.waste` — 1 expert = 1 read, 4KiB aligned | GGUF มาตรฐาน | ⚠️ ต่าง — จัดวางไฟล์ไม่ได้ |
| Quantization | VQ3R (3-bit) + 4-bit trunk | GGUF quant (Q4_K_M/Q6_K) | 🟡 พึ่ง quant ของ GGUF |
| Predictor | Router lookahead (59% recall) | Heuristic (ไม่ critical ที่ Qwen) | ⚠️ ต้องยกระดับเมื่อ I/O เป็นคอขวด |
| RAM Budget | Hard ceiling + floor + cgroup-aware | ไม่มี | ⚠️ เสี่ยง paging cliff |
| Chunked Prefill | 3.3x อ่านน้อยลง | ไม่มี | ⚠️ ยังไม่ได้ exploit |
| Telemetry | วัดได้แม่น (คุมทุกอย่าง) | OS page faults (total_accesses=0) | ⚠️ gap ตัวจริง |
| Scaling | ถึง K3 (2.78T) จริง | ยังอยู่ Qwen 2.7B | ⚠️ ยังห่าง |

---

## ✅ จุดแข็งของคุณ (หลักฐานจริง)

1. **ค้นพบว่า consumer CPU เป็น compute-bound ~92%** — EXP-003/004, ADR-003
2. **ใช้ mmap + OS page cache** — ไม่สร้างล้อใหม่ (ถูกต้องสำหรับ Phase 1)
3. **Honest telemetry** — ยอมรับ `total_accesses=0` จริง ไม่ fake ตัวเลข
4. **บันทึก ADR + negative results** — วินัย engineering ตรงกับปรัชญา WASTE
5. **เข้าใจ bandwidth-bound physics** — `tok/s ≈ bandwidth ÷ bytes/token` (F16 4.2B อ่าน 8.4 GB/tok → 2.8 tok/s ตรงคำทำนาย)

---

## 🔧 ช่องว่างที่ต้องปิด (เรียงตามความสำคัญ)

1. **`total_accesses = 0`** — tracker มองไม่เห็นการอ่านของ llama.cpp → วัดผล streaming จริงไม่ได้ = **blocker ตัวจริง**
2. **Predictor ยังเป็น heuristic** — ต้องเป็น router-aware (WASTE: 29% → 59% recall)
3. **จัดวางไฟล์ไม่ได้** — GGUF ถูกจัดวางโดย llama.cpp → ไม่ได้ "placement decides speed"
4. **ไม่มี RAM budget control + chunked prefill** — เสี่ยง paging cliff เมื่อไปโมเดลใหญ่

---

## 🎯 คำแนะนำ 3 ข้อ (บันทึกที่ docs/ADVISORY-2026-08-03-WASTE.md)

1. **ตัดสินใจเป้าหมาย: Research ก่อน Product** — งาน UI กำลังดึงออกจาก core
2. **ปิด gap `total_accesses=0` ก่อน** — fork llama.cpp หรือ native core (`core/native/` มีอยู่แล้วยังไม่ wire)
3. **ใช้ Kimi-Linear 48B แทน K3** — 19GB, 1.28GB RAM, 10.65 tok/s (คำแนะนำเดียวกับ WASTE)

---

## 🗺️ แผนปฏิบัติ

| # | งาน | ผลลัพธ์ที่วัดได้ |
|---|-----|----------------|
| 0 | ส่งท้าย + merge worktree dashboard | git clean |
| 1 | ตัดสินใจ: fork llama.cpp vs native core | ADR-004 |
| 2 | ปิด `total_accesses=0` | เห็น expert routing + hit/miss จริง |
| 3 | ยกระดับ predictor → router-aware | recall > 50% |
| 4 | ทดสอบ Kimi-Linear 48B | 10+ tok/s |
| 5 | เพิ่ม RAM budget + chunked prefill | ไม่มี paging degradation |
| 6 | ค่อยขึ้น K3 | 0.5+ tok/s บน 64GB |

---

## 🔑 หลักคิดจาก WASTE (cheat sheet)

- **Placement decides speed, never precision** — 1 entity = 1 contiguous read, align 4 KiB
- **รู้จัก floor ก่อน optimize** — RAM ที่เหลือคือ "ของที่ซื้อความเร็วได้"
- **ระวัง paging cliff** — ให้ RAM มากเกิน → ช้า 8 เท่า (หน้าต่าง 46→52 GB)
- **Predictor ต้องเป็น router-aware** — heuristic แพ้ (29%), router lookahead ชนะ (59%)
- **Measure before build + บันทึกสิ่งที่ล้มเหลว** — WASTE แพ้ 3/4 ครั้งที่ลอง optimization
- **GPU ไม่ได้เร็วเสมอไป** — matmul ก้อนเล็กต่อเนื่อง → CPU ชนะ (Metal ช้า 22%)

---

## 🔗 แหล่งข้อมูล

- WASTE repo: https://github.com/sqliteai/waste
- บทความไทย: https://vibecodingthailand.com/blog/waste-kimi-k3-laptop
- บทความต้นฉบับ: https://marcobambini.substack.com/p/the-waste-inference-engine
- โปรเจคคุณ: D:\.opencode\.Weight-Streaming (docs/ARCHITECTURE.md, docs/DECISIONS.md)

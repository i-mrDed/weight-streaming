# ⚠️ ADVISORY — คำแนะนำเชิงกลยุทธ์จาก WASTE Research (2026-08-03)

> **ที่มา:** จากการ Deep Research โปรเจกต์ [sqliteai/waste](https://github.com/sqliteai/waste)
> (WASTE = Weight-Aware Streaming Tensor Engine — รัน Kimi K3 2.78T บน 64GB RAM ได้จริง 0.5–0.62 tok/s)
> เทียบกับสถาปัตยกรรมของโปรเจค Speculative Weight Streaming
>
> **สถานะ:** 🟡 ต้องอ่านก่อนตัดสินใจเรื่องทิศทางโปรเจคครั้งต่อไป
> **วิธีใช้:** กลับมาอ่านไฟล์นี้ทุกครั้งก่อนเลือกงานถัดไป (ก่อนดิ่งงาน UI/product)

---

## 🎯 เป้าหมายที่ควรยึด

> รันโมเดลใหญ่ (100B–3T+) บนเครื่อง RAM 32–64 GB + NVMe — โดยที่ **weight streaming engine ทำงานจริงได้**
> ไม่ใช่แค่ dashboard สวยๆ

---

## 📌 คำแนะนำ 3 ข้อ (ห้ามลืม)

### 1️⃣ ตัดสินใจเป้าหมายให้ชัด: Research ก่อน Product
- งานที่ "เสร็จ" ไปล่าสุดคือ dashboard/UI/issues/hub — **ไม่ใช่** core engine
- ยังไม่มีหลักฐานว่า core streaming ทำงานจริงกับโมเดลใหญ่พอ (ยังอยู่ที่ Qwen 2.7B, ยังไม่ถึง K3)
- **ตัดสินใจ:** ถ้าจะทำ research paper → งาน core ต้องมาก่อน UI
- worktree dashboard (feature/dashboard-theme) → **ส่งท้ายให้เสร็จ แล้ว merge** อย่าปล่อยค้าง

### 2️⃣ ต้องปิด gap `total_accesses = 0` ก่อนทำอย่างอื่น
- ปัญหา: llama.cpp อ่าน mmap แบบ opaque → tracker ของเรามองไม่เห็นการอ่านเลย → วัดผล streaming จริงไม่ได้
- ตราบใดที่ปิด gap นี้ไม่ได้ = ไปต่อไม่ได้ (วัดไม่ได้ = พิสูจน์ไม่ได้)
- **ทางเลือก:** fork llama.cpp (expose expert routing + hooks) หรือ ทำ native core จริง (มี `core/native/` อยู่แล้วยังไม่ wire)

### 3️⃣ อย่าเพิ่งทำ K3 — ใช้ Kimi-Linear 48B เป็น stepping stone
- K3 = NVMe 1TB + RAM 64GB + convert 4.7 ชม. → **แพงเกินจะ experiment บ่อย**
- Kimi-Linear 48B = container 19 GB, RAM ขั้นต่ำ 1.28 GB, 10.65 tok/s (คำแนะนำเดียวกับ WASTE)
- ใช้ Kimi-Linear 48B พิสูจน์ core ก่อน → ค่อยขึ้น K3

---

## 🔑 หลักคิดจาก WASTE ที่ควรจำ (cheat sheet)

| หลักคิด | รายละเอียด |
|---------|-----------|
| **Placement decides speed, never precision** | จัดวางไฟล์ให้ 1 entity = 1 contiguous read, align 4 KiB → output ต้อง bit-identical ไม่ว่า data มาจาก RAM หรือดิสก์ |
| **รู้จัก floor ก่อน optimize** | หา RAM ขั้นต่ำ (floor) ก่อน → RAM ที่เหลือคือ "ของที่ซื้อความเร็วได้" |
| **ระวัง paging cliff** | ให้ RAM/cache มากเกินไป → ช้ากว่าเดิม 8 เท่า (หน้าต่างใช้งานแคบ: 46→52 GB) |
| **Predictor ต้องเป็น router-aware** | heuristic prediction แพ้ (29% recall) — WASTE ใช้ router ของ layer ถัดไป = 59% recall |
| **Measure before build + บันทึกสิ่งที่ล้มเหลว** | WASTE แพ้ 3/4 ครั้งที่ลอง optimization — เก็บ negative results ไว้ใน LEARNED.md |
| **GPU ไม่ได้เร็วเสมอไป** | workload matmul ก้อนเล็กต่อเนื่อง (latency-bound) → CPU ชนะ (Metal ช้า CPU 22%) |

---

## 📊 ตัวเลขที่ควรจำ (จาก WASTE)

- Kimi K3: 2.78T params, 896 experts, top-16, latent MoE → **ใช้จริง ~4% ต่อ token**
- K3 container: 982 GB / trunk 27.28 GB resident / RAM floor 29.06 GB @ 4K
- Cold token อ่าน ~17 GB → ดิสก์คือคอขวด (internal NVMe 12.78 GB/s vs USB 0.94 GB/s)
- Expert cache sweet spot: 17.32 GB → 0.63 tok/s (52 GB → 0.07 tok/s ❌ paging)
- VQ3R (3-bit experts) = operating point 19.4% error; 2-bit = 34% อันตราย
- KDA linear attention → KV cache 0.21 GB @ 4K (แทน 11.25 GB) → RAM เหลือให้แคช

---

*บันทึกโดย OpenCode Agent · 3 สิงหาคม 2026 · อ้างอิง: `research/waste-comparison/` (คู่มือฉบับเต็ม)*

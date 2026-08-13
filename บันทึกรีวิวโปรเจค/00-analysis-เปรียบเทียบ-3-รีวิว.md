# การวิเคราะห์เปรียบเทียบรีวิวจากแพลตฟอร์ม (Sonnet 5 / Manus AI / Qwen — ได้ 3 จาก 4)

วันที่: 2026-08-10 · อ้างอิง: บันทึกรีวิว 3 ไฟล์ในโฟลเดอร์นี้ + หลักฐานเชิงประจักษ์ EXP-012..017
วิธีวิเคราะห์: เทียบ 3 รีวิวเข้าด้วยกัน แล้ว**กรองทุกข้อเสนอผ่านผลวัดจริงของโปรเจค** (ไม่รับคำแนะนำแบบสุ่มสี่สุ่มห้า)

---

## 1. สรุปแต่ละรีวิว

| แพลตฟอร์ม | คะแนน | จุดยืนหลัก | คุณภาพการรีวิว |
|---|---|---|---|
| **Sonnet 5** | ~7.5/10 | เจอช่องว่าง vision vs shipped ("speculative streaming ยังไม่เกิดจริง, สิ่งที่ได้คือ honest benchmark platform") + เสนอ 2 track (A: product จริง / B: research ต่อ) | **ลึกที่สุด** — อ่าน README + PROJECT.md + ARCHITECTURE.md (888 บรรทัด) + ISSUES.md แล้วชี้จุดเฉพาะเจาะจง (buffer dead code, frontend bug pattern, no auth) |
| **Manus AI** | 9.1/10 | ชื่นชม architecture + telemetry + research ครบ (EXP-001..17) | กลาง — รายงานกว้างๆ ถูกต้องเป็นส่วนใหญ่ แต่ข้อเสนอหลายข้อ naive (LAN streaming, near-storage) |
| **Qwen** | 9.0/10 | เหมือน Manus — praise-heavy + แนะนำ predictive prefetching / NAS / Docker / community | กลาง — อ่าน surface (EXP-001..13, ไม่เห็น 14-17) จึงแนะนำสิ่งที่เราพิสูจน์แล้วว่าปิดไปแล้ว |

**ประเด็นเรื่องคะแนน:** ช่วง 7.5–9.1 สะท้อน "ความลึกของการอ่าน" ไม่ใช่คุณภาพโปรเจค — Sonnet อ่านลึกสุด เจอจุดบกพร่องจริง; Manus/Qwen โดน "short prompt" แล้วตอบแบบ praise pattern ทั่วไป รีวิวที่ "ชมมากสุด" ไม่ใช่ "แม่นสุด"

---

## 2. จุดที่ทุกฝ่ายเห็นตรงกัน (consensus — น่าเชื่อถือ)

1. **Honest telemetry คือ brand identity ที่แข็งสุด** — 3 ฝ่ายยกเป็นจุดเด่นอันดับ 1 ทั้งหมด (Sonnet 10/10 ในมิติความซื่อสัตย์)
2. **สถาปัตยกรรม/เอกสารแข็ง** — ADR-003, As-Built Summary, traceability ระหว่างเอกสาร
3. **แนะนำ "predictive prefetching / expert predictor" เป็นขั้นต่อไป** — ทั้ง 3 ฝ่าย (แต่ Sonnet ระวังตัว: ต้อง expose routing event ก่อน ค่อยทดสอบกับ Qwen3.6-35B ก่อน K3 — ตรงกับแผนที่เราตรวจ feasibility ไว้แล้วใน EXP-015/016)
4. **Frontend ขาด test runner** — Sonnet + Qwen (ตรวจแล้ว: จริง — `frontend/package.json` ไม่มี vitest/jest, CI มีแค่ `tsc` + `vite build`)

---

## 3. จุดที่ขัดแย้งกัน / ต่างกัน

| ประเด็น | Sonnet | Manus | Qwen | ความจริงใน repo |
|---|---|---|---|---|
| สถานะ "streaming" | **วิพากษ์ตรงๆ**: buffer subsystem เป็น dead code (total_accesses=0 เพราะ llama.cpp อ่าน mmap แบบ opaque) | ยกย่องว่า "Memory-mapping แบบ Zero-copy" โดยไม่เห็นปัญหานี้ | ไม่แตะประเด็นนี้ | Sonnet ถูก — ตรงกับ ARCHITECTURE.md ที่เราบันทึกเอง (Stats buffer = n/a by design) |
| ช่องว่าง README vs reality | ชี้ว่าควรทำ banner ชัดว่า predictor ยังไม่ active | ไม่เห็น | แนะนำแค่ split Quick Start | README ปัจจุบัน (หลังแก้) ตรงความจริงค่อนข้างมากแล้ว — เหลือแค่ step "Streams weights" ที่ยัง ambiguous |
| เป้าหมายโปรเจค | เสนอให้**ตัดสินใจ 2 track** (A: honest platform / B: research) — จุดที่ลึกสุด | มองว่าไปต่อได้ทั้งคู่ไม่ขัดแย้ง | ไม่แยกประเด็น | จุดนี้คือคำถามเชิงกลยุทธ์ที่แท้จริงของโปรเจค |
| การทดสอบ | 6/10 (บั๊กพื้นฐานใน ISSUES.md) | 9.0/10 | 8.5/10 | ต่างกันที่เกณฑ์ — Sonnet ดู pattern ของบั๊ก ส่วนอีก 2 ดูแค่ test count (287) |

---

## 4. กรองข้อเสนอผ่านหลักฐานเชิงประจักษ์ของเรา (สำคัญที่สุด)

ข้อเสนอของรีวิว (ส่วนใหญ่ไม่รู้ผล EXP-012..017) → เทียบกับสิ่งที่เราวัดจริง:

| ข้อเสนอจากรีวิว | Verdict ตามหลักฐานเรา | เหตุผล |
|---|---|---|
| **Predictive prefetching / expert predictor** (3 ฝ่าย) | ⚠️ **ยังเปิดอยู่ แต่ต้องเจอ path ก่อน** | EXP-016: expert activation flat ข้าม layer (placement ไม่ชนะ) — แต่ *prefetch timing* (disk→RAM) เป็นคนละแกนกับ placement ยังไม่ถูกทดสอบปิด; EXP-012: disk-bound จริง (150–300 MB/token) → ถ้ามี pattern ที่ OS readahead ทำไม่ได้ = ได้จริง แต่**ต้อง instrumented build ก่อน** (LLAMA_LOG_MOE ไม่มีใน b9967 — EXP-016 พิสูจน์แล้ว) |
| **CPU lane / expert คำนวณบน CPU** (pulsar-style) | ❌ **ปิดแล้ว** (EXP-017) | CPU bandwidth-bound ไม่ใช่ core-bound — CPU ใช้แค่ 39–51% แต่ DDR4 bandwidth อิ่ม → ย้ายงานมา CPU เพิ่ม = แย่ลง |
| **LAN / distributed weight streaming** (Manus #3) | ❌ **ขัดฟิสิกส์** | คอขวดคือ disk→RAM; LAN (10GbE ≈ 1.25 GB/s) ช้ากว่า NVMe (3.5+ GB/s) เสียอีก + เพิ่ม latency |
| **Near-storage compute** (Manus #2) | 🟡 ไอเดียจริง แต่เกินขอบเขตตอนนี้ | ต้อง custom hardware/FPGA — เก็บไว้เป็น research direction ระยะยาว |
| **Frontend test runner (vitest)** (Sonnet + Qwen) | ✅ **เห็นด้วย — gap จริง** | ไม่มีใน package.json; ISSUES.md มีบั๊กที่ test ควรจับได้ (duplicate let, null ref) |
| **Auth บน API** (Sonnet) | ✅ **เห็นด้วย — gap จริง** | โค้ด comment บอกเอง "No auth in v1"; default bind 127.0.0.1 ยังพอ safe แต่ถ้าจะ expose ออก LAN ต้องมีก่อน |
| **Spec decode** (pulsar/DSpark ที่เคยเสนอ) | ❌ **ปิดแล้ว** (EXP-015) | MTP ช้าลง 11–18% บน 12 GB (bandwidth-bound) — DSpark สำเร็จเฉพาะเครื่อง bandwidth เหลือ |
| **Docker / one-click install** (Qwen) | 🟡 กลาง | DX gap จริง (ไม่มี Dockerfile) แต่ Docker+GPU บน Windows messy; value อยู่ที่คนนอก |
| **เผยแพร่ EXP-012 สู่สาธารณะ** (Sonnet Track A + Qwen) | ✅ **เห็นด้วย** | repo เพิ่ง public (0 star = ปกติ ยังไม่ถึง 24 ชม.) — write-up ลง r/LocalLLaMA/HN = วิธีหา traction จริง |

---

## 5. Fact-check ตัวเลขที่รีวิวอ้าง (ตรวจกับ repo แล้ว)

| ที่อ้าง | ตรวจแล้ว | ผล |
|---|---|---|
| ~287–290 Python tests | `pytest --collect-only` = **287** | ✅ ตรง |
| ไม่มี frontend test runner | `frontend/package.json` ไม่มี vitest/jest | ✅ ตรง |
| ไม่มี auth บน API | comment ใน `api_server.py`/`hub.py`: "No auth in v1" | ✅ ตรง |
| ไม่มี Docker | ไม่มี Dockerfile/docker-compose.yml | ✅ ตรง |
| buffer subsystem เป็น dead code | ARCHITECTURE.md ระบุ total_accesses=0 เอง | ✅ ตรง |
| "0 stars/forks" = ความพร้อมชุมชนต่ำ | repo เพิ่ง public เมื่อวันนี้ | ⚠️ **วัดเร็วเกินไป** — ไม่ใช่ defect |

---

## 6. สรุป Action Items (จัดลำดับตามคุณค่า/ต้นทุน)

**กลุ่มที่ควรทำ (เห็นด้วย + ต้นทุนต่ำ):**
1. **Frontend test runner (vitest)** — จับบั๊ก pattern ใน ISSUES.md ตั้งแต่ CI (Sonnet+Qwen ตรงกัน)
2. **Auth token บน API** — ก่อนคิด expose ออก LAN ใดๆ (Sonnet; โค้ดเองก็ flag ไว้)
3. **Write-up EXP-012 สู่สาธารณะ** — r/LocalLLaMA/blog — ใช้ honest telemetry เป็น bait ดึง traction (Sonnet + Qwen ตรงกัน)

**กลุ่มที่ต้องตัดสินใจเชิงกลยุทธ์:**
4. **Track A vs B ของ Sonnet** — คำถามเดียวที่สำคัญที่สุด: โปรเจคนี้คือ "honest local-inference platform" (shipped แล้ว, พร้อมขาย) หรือ "speculative weight streaming research" (ยังไม่เกิด)? ตอบข้อนี้ก่อนทุกอย่าง
5. **Predictive prefetching path** — ถ้าเลือก Track B: ต้อง instrumented llama.cpp build (expose routing) ก่อนถึงจะทดสอบ predictor ได้ — งานใหญ่สุด กำไร uncertain แต่เป็น "กุญแจ" ที่ทุกแพลตฟอร์มชี้ทางเดียวกัน

**กลุ่มที่ปิดแล้วตามหลักฐาน (ไม่ต้องทำซ้ำ):**
6. CPU lane (EXP-017) / spec decode (EXP-015) / census→tiering (EXP-016) / LAN streaming (ขัดฟิสิกส์)

---

## หมายเหตุ
- รีวิวที่ 4 ยังมาไม่ถึง — เมื่อได้ครบ 4 ควรอัปเดตเอกสารนี้ (โดยเฉพาะถ้าฝ่ายที่ 4 เจอประเด็นใหม่ที่ 3 ฝ่ายแรกไม่เจอ)
- จุดแข็งร่วมของ 3 รีวิว = ยืนยันว่า "honest telemetry" เป็นสิ่งที่คนนอกมองเห็นและให้ค่ามากที่สุด — นี่คือ asset ที่ควรปกป้องที่สุดของโปรเจค

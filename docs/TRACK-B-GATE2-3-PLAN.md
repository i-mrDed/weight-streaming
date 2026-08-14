# Track B — Gate 2/3 Plan (2026-08-14)

> **สถานะ:** แผน + ประเมินด้วย evidence ที่มีอยู่ — **ยังไม่ได้ตัดสินใจ** ต้อง user ตัดสินใจต่อท้าย
> **อ้างอิง:** `docs/TRACK-B-GATE1-FEASIBILITY.md` (Gate 1 ✅) · `TASKS.md` §Track B · DECISION criteria
> (Gate 2: predictability **< 90% ที่ N ต่ำ = ปิด** · Gate 3: idle gap **< 10% = ไม่คุ้ม**)

---

## สรุปสั้น (TL;DR)

- **Gate 2 ถูกวัดไปแล้วจริงระหว่างงาน L1/A-series (EXP-031/031b, 2026-08-13)** — บน Qwen1.5-MoE-A2.7B
  (4096 tokens): top-N hit rate 6.9–13.1% useful vs random 6.7% (เป้า ≥ 50%) · routing เปลี่ยน ~97.7% ของ tokens ·
  verdict ของ L1 closure = **per-token expert prediction เป็น dead end บนสถาปัตยกรรมนี้**
- ตามเกณฑ์ DECISION (ต้อง ≥ 90% ที่ N ต่ำ) → **Gate 2 เท่ากับ FAIL ไปแล้ว** — เหลือแค่การตัดสินใจว่าจะ
  ยอมรับ evidence นี้ (ประหยัด 1–3 วัน build CUDA) หรือ re-run บน target model (DS V4 Flash)
- **Gate 3 (latency gap บน disk-bound) ยังไม่ถูกตอบอย่างเป็นทางการ** — แต่ตอบได้ **โดยไม่ต้อง fork**
  (ใช้ telemetry ที่มีอยู่: EXP-012 paging stall, EXP-029 buffer size impact) — นี่คืองานเดียวที่ "ใหม่" จริง
- สิ่งที่ Gate 1 บอกว่า "ต้อง fork + patch เอง" **มี patched build อยู่แล้วบนเครื่อง dev**
  (`D:\Run_model\llama.cpp\build-ws-static` — จาก A1–A3, ยังไม่ commit ต้นทาง) → ถ้าจะ re-run ไม่ต้อง build ใหม่

---

## หลักฐานที่ตอบ Gate 2 ไปแล้ว (จากการทำงานจริง ไม่ใช่แผน)

| แหล่ง | วัดอะไร | ผล | ต่อ Gate 2 |
|---|---|---|---|
| EXP-031 (A-series) | per-token expert prediction: global-top4 / window-1 / frequency / recent-8 | useful 9.1% / 6.9% / 8.7% / 13.1% vs random 6.7% (เป้า ≥ 50%) | ❌ ต่ำกว่าเป้ามาก |
| EXP-031b (A5b) | router probs: top-1 avg 0.174 (vs uniform 0.0167), ~2.7 experts > 5% | routing เลือกจริงแต่**เปลี่ยนทุก token** — overlap ติดกัน 0.25/4 | ❌ ไม่มี temporal structure |
| EXP-016 | expert census บน layer | traffic flat ข้ามทุก layer — ไม่มี hot layer | สอดคล้อง (ไม่มี set ถาวร) |
| A-series capture | patch kernel `ggml_compute_forward_argsort_f32` dump expert ids → WS_EXPERT | **instrumentation ทำงานจริง** (PR #6 ใน product) | ✅ machinery พร้อม |

**ข้อจำกัดของ evidence นี้:** วัดบน **Qwen1.5-MoE-A2.7B** (เล็ก, 60 experts) — ยังไม่ได้รันบน
**DS V4 Flash** (target model, 1.8T params) → ถ้าต้องการตัวเลขของ target model จริง ต้อง re-run
ด้วย patched build บนเครื่อง dev (~0.5–1 วัน รวม sanity check)

---

## ทางเลือก (ต้อง user ตัดสินใจ)

| ทาง | งาน | effort | risk | verdict |
|---|---|---|---|---|
| **1. ปิด Gate 2 ด้วย evidence EXP-031** (แนะนำ) | อัปเดต TASKS.md/plan → Gate 2 ❌ ตามเกณฑ์ DECISION + บันทึก verdict | ~15 นาที (docs) | ต่ำ — ตัวเลขมาจากการวัดจริง; จุดอ่อน = ต่าง model | ✅ **แนะนำ** — สอดคล้อง L1 closure |
| **2. Re-run Gate 2 บน DS V4 Flash** | ใช้ patched build ที่มีอยู่ → รัน A-series harness กับ DS V4 Flash (TH/EN prompts) → วัด top-N hit rate | 0.5–1 วัน (เครื่อง dev) | กลาง — build เก่าอาจไม่ตรง mainline ล่าสุด; ต้องเช็ค `llama-server --version` | เลือกได้ ถ้าต้องการตัวเลข target model ก่อนปิด |
| **3. วัด Gate 3 (latency gap)** | **ไม่ต้อง fork** — ใช้ paging telemetry: (disk-mmap stall / total gen time) จาก EXP-012 + buffer-size sweep EXP-029 → idle gap % | 0.5–1 วัน (เครื่องจริง, script มีอยู่) | ต่ำ | ✅ ควรทำ — เป็น gate เดียวที่ยังไม่มีคำตอบ |
| **4. ปิด Track B ถาวร** | ตาม L1 closure + Gate 2 fail → ลบ/archive Track B ออกจาก active | ~15 นาที | ต่ำ | ทางเลือกถ้าตัดสินใจ 1 + 3 เป็นลบ |

> หมายเหตุ: DECISION criteria ของ Gate 2 ตั้งเป้า "< 90% ที่ N ต่ำ = ปิด" — evidence EXP-031 อยู่ที่ ~7–13%
> (random baseline 6.7%) → ห่างจากเป้าเกิน order of magnitude มาก การ re-run บน model ใหญ่ที่
> routing อาจ "เสถียรกว่า" เล็กน้อย ไม่น่าพลิก verdict (แต่ถ้าอยากชัวร์ = ทางเลือก 2)

---

## ถ้าเลือกทางเลือก 2 หรือ 3 — ขั้นตอนจริง

### ทางเลือก 2: Re-run Gate 2 บน DS V4 Flash

1. **ตรวจ patched build** — `D:\Run_model\llama.cpp\build-ws-static` ยังอยู่ไหม + `llama-server --version`
   เทียบกับ mainline ที่ product ใช้ (brain note: build 8196) · ถ้าไม่อยู่ → Gate 1 draft steps (build ใหม่ 1–3 วัน)
2. **เปิด capture** — `WS_EXPERT_TRACE=1` (env) รัน server กับ DS V4 Flash IQ3_XXS (n_ctx เดียวกับ EXP-012)
3. **รัน harness** — prompt ไทย/อังกฤษ อย่างละ 2–3 ชุด (~2–4k tokens) → เก็บ routing history
   (มี `scripts/measure_*.py` + `summarize_dsv4flash.py` เป็น template)
4. **วิเคราะห์** — top-N hit rate (N=2/4), co-occurrence matrix, window-N stability — เทียบเกณฑ์ 90%
5. **สรุป** — verdict → อัปเดต TASKS.md Gate 2

### ทางเลือก 3: วัด Gate 3 (latency gap) — ไม่ต้อง fork

1. **ข้อมูลที่มีอยู่:** EXP-012 (DS V4 Flash 1.5–1.9 tok/s, disk-bound; paging faults/token จริง) ·
   EXP-029 (K3: buffer 4 GB → 1.18 tok/s) · `scripts/spike_page_faults.py` + paging telemetry ใน product
2. **คำนวณ idle gap** — `disk-mmap stall time / total generation time` ต่อ token (จาก `faults_per_token ×
   avg fault service time` กับ disk bandwidth ที่ calibrated — EXP-025)
3. **ถ้า gap < 10%** → prefetch ซ่อนได้น้อยกว่า 10% = ไม่คุ้ม (DECISION) → ปิด Track B
   · **ถ้า gap > 10%** → ดูว่า buffer tuning (EXP-029) ครอบ gap ได้ไหมก่อนสรุป

---

## Decision point (สำหรับ user)

- [ ] **Gate 2:** ยอมรับ evidence EXP-031 (ปิด ❌) หรือ re-run บน DS V4 Flash (ทางเลือก 2)?
- [ ] **Gate 3:** วัด latency gap ด้วย telemetry ที่มี (ทางเลือก 3) — ใช่/ไม่ใช่?
- [ ] **Track B โดยรวม:** ปิดถาวร (ตาม L1 closure) หรือ keep เป็น bounded spike?

> ข้อเสนอของผม: **ทางเลือก 1 + 3** — ใช้ evidence ที่วัดจริงปิด Gate 2, วัด Gate 3 ให้จบ (งานเดียวที่ใหม่จริง,
> ไม่ต้อง fork) แล้วปิด Track B ด้วยหลักฐานครบทั้ง 3 gates — ประหยัด build CUDA 1–3 วันที่ไม่คุ้มกับผลลัพธ์ที่คาด

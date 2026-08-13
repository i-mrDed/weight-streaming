# DECISION: Track A vs Track B — โปรเจคนี้คืออะไรกันแน่ (identity crisis)

**วันที่:** 2026-08-10 · **อัปเดตครั้งล่าสุด:** 2026-08-13 (หลักฐานใหม่ EXP-025..030 + paper + fact-check) ·
**ผู้ตั้งคำถาม:** รีวิวสาธารณะ 4 แพลตฟอร์ม (Sonnet ชี้ตรง, OpenCode ตั้งชื่อ "W13 identity crisis") ·
**สถานะ: ✅ ตัดสินใจแล้ว (2026-08-13) — Track A เป็น product, Track B เป็น research spike แบบมี gate**
(ดูสรุปท้ายเอกสาร)

---

## ปัญหาในหนึ่งประโยค

> ชื่อโปรเจคสัญญา "speculative weight streaming" (predictor + prefetch
> ล่วงหน้า เอาชนะ mmap) แต่ของที่ shipped จริงคือ **local-inference platform
> + honest telemetry** ที่รัน llama-server + OS page cache — predictor ยัง
> ไม่เคยถูก validate กับ routing จริงเลย (`total_accesses = 0` ระหว่าง
> inference)

สอง track นี้ต้องการ resource, audience, และ roadmap ที่ต่างกัน — เลือก
**ผิดทาง** = ลงทุนผิดที่

---

## Track A — "honest local-inference platform" (ของที่ shipped แล้ว)

**Value proposition:** รันโมเดลใหญ่กว่า RAM บนเครื่อง consumer + **วัดราคาจริง**
(page faults/tok, disk MB/tok) — ซื้อฮาร์ดแวร์ด้วยข้อมูล ไม่ใช่ hype

| มิติ | สถานะ |
|---|---|
| สถานะ | ✅ **Shipped + tested** (300 tests, CI เขียว, console/hub/API/MCP ครบ) |
| รีวิว 4 แพลตฟอร์ม | 7.5–9.1/10 — **จุดแข็งที่ทุกฝ่ายยกย่องตรงกัน = honest telemetry** |
| ใครใช้ | home-lab, นักวิจัย, คนตัดสินใจซื้อ hardware, IDE/agent ท้องถิ่น |
| คู่แข่ง | llama.cpp/Ollama/LM Studio รัน inference เหมือนกัน — **ส่วนต่างของเราคือ telemetry + การวัด >RAM** |
| ความเสี่ยง | ชื่อ "weight-streaming" over-promise; buffer/prefetcher เป็น dead code บน GPU path (ต้อง cleanup หรือ rebrand) |

**ต้องทำถ้าเลือก A:**
1. Rebrand/ปรับ README — เปลี่ยน positioning จาก "speculative streaming" → "honest >RAM inference + telemetry"
2. ลบ/ตัด dead code (buffer/prefetcher/predictor) ออกจาก path หลัก หรือย้ายเป็น optional
3. เผยแพร่ EXP-012 write-up (มี draft แล้ว) → หา community + feedback
4. PyPI release + Linux CI + Docker (review ข้อ B5–B7)

---

## Track B — "speculative weight streaming research" (วิสัยทัศน์ตั้งต้น)

**Thesis:** predict expert ที่ token ต่อไปจะใช้ → prefetch จาก NVMe ขึ้น RAM
ล่วงหน้า → ชนะ OS page cache (reactive) ที่ EXP-012 พิสูจน์แล้วว่าคือกำแพง

| มิติ | สถานะ |
|---|---|
| สถานะ | 🔬 research code (HeuristicPredictor + Prefetcher + shard format) — **ยังไม่เคย validate กับ routing จริง** |
| หลักฐานค้าน | EXP-016 (activation flat → placement ไม่มี hot layer) · EXP-017 (CPU bandwidth-bound) · EXP-015 (spec decode ช้าลง) |
| หลักฐานสนับสนุน | disk-bound จริง (150–300 MB/tok) · **4 รีวิวชี้ทางเดียวกันว่า predictor คือ "กุญแจ"** · EXP-014 landscape (imatrix 747M obs ของ Strix-Halo = census ใช้ calibrate quant ได้จริง) |
| อุปสรรคสำคัญ | llama.cpp **ไม่ expose per-token routing** (EXP-016 พิสูจน์: ไม่มี LLAMA_LOG_MOE ใน b9967) → validate ไม่ได้จนกว่าจะมี instrumented build |

**ข้อวิเคราะห์ที่สำคัญที่สุด (เพิ่มจาก EXP-012..017):**

> EXP-012 พิสูจน์ว่า pipeline **bandwidth-bound** (disk อิ่ม: 150–300 MB/tok)
> — ถ้าดิสก์ส่งข้อมูลได้เต็มอัตราอยู่แล้ว **prefetch แค่ "จัดคิว" ไม่ได้เพิ่ม
> throughput** มันช่วยได้แค่ *latency hiding* (ลดการรอเป็นจังหวะ)
>
> → ceiling ของ Track B บนเครื่องนี้คือ **ซ่อน latency** ไม่ใช่เพิ่ม tok/s
> — ต่างจากที่ PROJECT.md เดิมคาดหวังไว้มาก
>
> → แต่ ceiling นั้นยังไม่ได้ถูกวัด (เราวัดแค่ throughput ไม่ได้วัด
> latency gap) — นี่คือคำถามที่เปิดอยู่และวัดได้

**ต้องทำถ้าเลือก B (ตามลำดับ, มี gate):**
1. **Gate 1 — instrumented llama.cpp build** (expose per-expert routing ผ่าน callback/env) — ถ้าทำไม่ได้ = ปิดถาวร
2. **Gate 2 — วัด predictability จริง** บน Qwen3.6-35B-A3B (256 experts): expert co-occurrence, top-N hit rate ข้าม prompt ไทย/อังกฤษ — ถ้า < 90% ที่ N ต่ำ = ปิด
3. **Gate 3 — วัด latency gap บน disk-bound config** (DS V4 Flash): มี idle gap กี่ % ของเวลา ที่ prefetch จะซ่อนได้ — ถ้า gap < 10% = ไม่คุ้ม
4. ถ้าผ่านทั้ง 3 → PoC prefetcher → เทียบ tok/s กับ mmap baseline

---

## เกณฑ์ตัดสินใจ (decision criteria)

| ถ้า... | เลือก |
|---|---|
| เป้าหมาย = product ที่มีคนใช้ + traction + release | **A** |
| เป้าหมาย = นวัตกรรม "สร้างสิ่งที่ไม่เคยมี" (K3 ระดับ) ยอมรับความเสี่ยง research | **B** |
| อยากได้ทั้งสอง (แนะนำ) | **A เป็นแกน + B เป็น bounded spike คู่ขนาน** |

## ✅ มติ (2026-08-13) — Track A เป็น product, Track B เป็น bounded research spike

**หลักฐานใหม่ที่ยืนยัน Track A (ตั้งแต่ 2026-08-11..13):**
- **Physics calibrated + validated จริง** (EXP-025/028): `tok/s = BW ÷ bytes/token` แม่น ±9% — Qwen 22.73 vs ทำนาย 22.73 (EXP-028) — "วัดได้ ไม่ใช่ vibes" คือตัวตนที่พิสูจน์แล้ว
- **30 experiments ครบ (EXP-001..030)** + paper ฉบับเต็ม (`research/paper/paper.md`) + **auto fact-check 33/33 PASS** (`scripts/factcheck_paper.py`) — ตัวเลขทุกตัวอ้าง raw data จริง
- **EXP-030 ปิดคำถาม offload**: โมเดลพอดี VRAM → offload ช้าลง 4× (126.6 → 31.8 tok/s) → offload คุ้มเฉพาะ >VRAM เท่านั้น
- **EXP-029 ระบุขอบเขต B ให้ชัด**: K3 buffer 256MB → 0.049 tok/s vs 4GB → 1.18 (**24×**) — prefetch เป็น *latency-hiding* ไม่ใช่ throughput (ตรงข้อวิเคราะห์เดิม) แต่ payoff = f(BW gap) — ใหญ่สุดเมื่อ disk-bound (K3)
- **โพสต์เผยแพร่พร้อม** (HN/blog ไทย+อังกฤษ) — เหลือแค่สวิตช์ public

**ผลต่อการตัดสินใจ:** Track A เลือกแล้วในทางปฏิบัติ (ทุกอย่าง prepped ถึงขั้นสวิตช์สุดท้าย) —
Track B ไม่ได้ตาย แต่**เพดาน = latency-hiding** และต้องผ่าน Gate 1 (instrumented build) ก่อน —
บันทึกเป็น spike คู่ขนาน ไม่ใช่ roadmap หลัก

---

## บทวิเคราะห์เดิม (2026-08-10)

**คำแนะนำของผม (จากหลักฐาน):**

**ทางสายกลาง — Track A เป็น product จริง, Track B เป็น research spike
ที่มี gate ชัดเจน 3 ขั้น (ใช้เวลา ~1–2 สัปดาห์ต่อ gate)**

เหตุผล:
1. **A ขายได้แล้ว** — telemetry คือ differentiation ที่ 4 รีวิวยกย่องตรงกัน; การไม่ปล่อย A = ปล่อยให้ asset ที่พิสูจน์แล้วนอนใน repo
2. **B ยังไม่ตายแต่เพดานต่ำกว่าที่คิด** — bandwidth-bound ทำให้ prefetch เป็น latency-hiding ไม่ใช่ throughput; แต่คำถาม "latency gap เท่าไร" ยังไม่ถูกวัด → คุ้มที่จะวัด 1 ครั้งแล้วปิด/เปิดด้วยข้อมูล
3. **Gate 1 (instrumented build) คือ "ลูกกุญแจ"** — ถ้าเปิดไม่ได้ B ก็จบ; ใช้เวลาและ effort จำกัดในการพิสูจน์
4. **ต้นทุนต่ำของ spike:** predictor/prefetcher code มีอยู่แล้ว — ต่อยอด = วัด ไม่ใช่เขียนใหม่

**สิ่งที่ต้องไม่ทำ:** ปล่อยสถานะปัจจุบัน (ชื่อสัญญา B แต่ shipped A, predictor วางเฉย ไม่ active ไม่ cleanup) — นี่คือ "identity crisis" ที่ทั้ง 2 track เสียหาย

---

## ผลต่อ ROADMAP ณ ส.ค. 2026

- Phase 4 (2.5–4 tok/s software-only) ยัง valid ภายใต้ Track A — lever ที่เหลือคือ IQ2_XXS (ลด bytes/token)
- ถ้าตัดสินใจ A ล้วน: ปิด research/ ต่อเป็น knowledge base, ย้าย predictor ไป optional, เริ่ม release v0.15.0
- ถ้าตัดสินใจ B: เริ่ม Gate 1 ทันที (instrumented build) ก่อนลงทุนอย่างอื่น

---

*เอกสารนี้เป็นการวิเคราะห์จากหลักฐาน EXP-012..017 + รีวิว 4 แพลตฟอร์ม — ตัวตัดสินใจสุดท้ายคือคุณ*

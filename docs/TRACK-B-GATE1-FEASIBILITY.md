# Track B — Gate 1 Feasibility: exposing per-expert routing from llama.cpp

> **วันที่:** 2026-08-13 · **สถานะ:** ✅ ตรวจสอบแล้ว (feasibility report — ยังไม่ลงมือ build)
> **Gate 1 (จาก `docs/DECISION-2026-08-10-track-a-vs-b.md`):** instrumented
> llama.cpp build ที่ expose per-expert routing — ถ้าทำไม่ได้ = ปิด Track B ถาวร

---

## คำถามของ Gate 1

> เราสามารถได้ **per-expert routing (expert ที่ token ต่อไปจะใช้) ต่อ token ต่อ layer**
> จาก llama.cpp ที่เรารันอยู่ (llama-server, Windows + CUDA 12 GB) ได้ไหม —
> โดยไม่ต้องจ่าย cost จนเพี้ยนการวัด?

## สรุปสั้น (TL;DR)

- **ทำได้ แต่ต้อง fork + patch เอง** — ไม่มี callback/API สาธารณะใน llama.cpp
  ที่ expose routing (ยืนยัน: `LLAMA_LOG_MOE` **ไม่มีอยู่จริง** ใน source; ไม่มี
  ฟังก์ชันใน `llama.h` ที่คืน expert indices ต่อ token)
- **หลักฐานว่า feasible:** Martin Alderson สร้าง [moe-viz](https://martinalderson.com/posts/moe-expert-routing-visualization/)
  (2026-04) โดยแก้ llama.cpp ให้ dump profiling data — ได้ heatmap routing
  ต่อ token ต่อ layer บน Gemma 26B-A4B จริง — "really fun weekend project"
- **Cost ประมาณ:** 1–3 วัน (รวม build CUDA on Windows) — bounded ตามที่
  DECISION ตั้งไว้ (~1–2 สัปดาห์ต่อ gate)
- **ผลลัพธ์แรกที่น่าสนใจของคนอื่น:** ~25% ของ experts **ไม่เคย activate**
  ใน prompt สั้นๆ — แต่เป็นคนละ 25% ทุกครั้ง (ไม่มี hot set ถาวร) —
  สอดคล้อง EXP-014/016 ของเรา (activation flat)

## ทำไมต้อง fork (ข้อเท็จจริงที่ตรวจแล้ว)

1. **ไม่มี per-token callback ใน API สาธารณะ** — `llama.h` มี callback สำหรับ
   log/progress/beam-search แต่ไม่มีสำหรับ MoE routing
2. **Routing เกิดลึกใน compute graph** — expert indices ถูกคำนวณใน
   `llama_moe`/`ggml` (จาก router logits → top-k) แล้วใช้ภายใน op นั้น —
   ไม่มีทางอ่านจากภายนอกโดยไม่แก้ C++
3. **`LLAMA_LOG_MOE` (ที่ EXP-016 กล่าวถึง) ไม่มีจริง** — เป็นตัวเลือกสมมุติ
   ที่เราเขียนไว้ตอนนั้น ต้องสร้างเอง

## ทางเลือกที่ประเมินแล้ว

| ทาง | งาน | ข้อดี | ข้อเสีย | verdict |
|---|---|---|---|---|
| **A. Fork + patch น้อยที่สุด** | ใส่ callback/env dump ที่จุดคำนวณ routing (llama_moe forward) → stdout/pipe | ตรงเป้า, proof จาก moe-viz | ต้อง build CUDA (VS + toolkit บน Windows), ต้องดูแล fork | ✅ **แนะนำ** |
| B. Defuse GGUF + reimplement routing | อ่าน GGUF เอง คำนวณ router logits ด้วย numpy (ไม่มี decode) | ไม่ต้อง build C++ | ต้อง match math ของ llama.cpp เป๊ะ (risk สูง), ช้า | fallback ถ้า A build ไม่ได้ |
| C. รอ upstream feature | ขอ PR/feature ใน llama.cpp | ไม่ต้องดูแลเอง | ไม่มีใครทำ, ไม่มี ETA — Gate 1 เปิดค้าง | ❌ |
| D. ใช้ router logits หลัง decode (token เก่า) | อ่าน logits ของ token ที่แล้ว | ไม่ต้อง fork | **ไม่ใช่ routing จริง** — เป็น logits ขาเข้า ไม่ใช่ expert ที่เลือก | ❌ (ตอบผิดคำถาม) |

## ขั้นตอนถ้าเปิด Gate 1 (ร่าง)

1. **เลือก commit ฐาน** — ใช้ version เดียวกับ llama-server ที่รันอยู่ตอนนี้
   (เช็ค `llama-server --version` / binary) เพื่อให้ผลเทียบ EXP-030/028 ได้
2. **Patch จุดเดียว:** ใน `src/llama-moe.cpp` (หรือจุดที่ `ggml_mul_mat` route
   ถูกสร้าง) — dump `(token_id, layer, expert_indices[])` ผ่าน env
   `WS_EXPERT_TRACE=1` + ไฟล์/pipe — **off by default** → zero cost ตอนไม่ใช้
3. **Build:** `cmake -DGGML_CUDA=ON` (ต้อง Visual Studio + CUDA toolkit —
   เครื่องนี้มี RTX 3060 + VS อยู่แล้ว แต่น่าจะต้องติดตั้ง CUDA toolkit)
4. **Sanity check:** รัน Qwen A2.7B 2–3 prompt → ตรวจว่า expert indices
   สมเหตุสมผล (60 experts, top-2/top-4 ต่อ layer) + tok/s ไม่เพี้ยน vs baseline
5. **ต่อ Gate 2** — วัด predictability จริง (expert co-occurrence, top-N
   hit rate ข้าม prompt ไทย/อังกฤษ) ตาม DECISION

## ความเสี่ยง / สิ่งที่ต้องรู้ก่อนตัดสินใจ

- **Build env เป็นงานก้อน** — Windows CUDA build ครั้งแรก (VS + CUDA toolkit +
  cmake) อาจกินครึ่งวันเอง; ทางลัด: ใช้ `llama-cpp-python` sdist build หรือ
  GitHub Actions build artifact (Linux CUDA) ถ้ารับได้ว่า env ต่างจาก Windows
- **Fork ต้องตาม upstream** — ถ้า upstream แก้ MoE บ่อย fork อาจล้าหลัง
  (ลดความเสี่ยง: patch เล็ก + cherry-pick ได้)
- **คุ้มไหมตอนนี้?** EXP-016/029 บอกว่า prefetch ceiling = latency-hiding
  ไม่ใช่ throughput — Gate 2/3 ยังเป็นคำถามเปิด แต่ Gate 1 เป็น "ลูกกุญแจ"
  ที่ราคา bounded — เปิดได้เมื่อมี budget research

## Verdict

**Gate 1: FEASIBLE (bounded)** — fork + patch ~1–3 วัน build env เป็น
ตัวแปรหลัก ไม่ใช่ตัว patch เอง (proof: moe-viz) — Track B ไม่ต้องปิดถาวร
แต่ก็ไม่ควรเริ่มจนกว่า Track A release จะนิ่ง (ตอนนี้)

## อ้างอิง

- `docs/DECISION-2026-08-10-track-a-vs-b.md` — Gate 1..3 definition
- `research/experiments/EXP-016-expert-census/results.md` — ที่มาของคำถาม
  (per-expert skew, `LLAMA_LOG_MOE` hypothesis)
- `research/experiments/EXP-029-k3-vs-qwen/` — ทำไม prefetch = latency-hiding
- [moe-viz — Martin Alderson](https://martinalderson.com/posts/moe-expert-routing-visualization/)
  (2026-04) — proof ที่ fork + dump ได้จริง
- llama.cpp `src/llama-moe.cpp`, `include/llama.h` — จุดที่ต้อง patch

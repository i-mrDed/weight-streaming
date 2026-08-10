# โมเดลที่รันแล้วใช้ทำงานได้จริงบนเครื่องนี้ (12 GB VRAM) — Shortlist 2026-08

> **เครื่อง:** i9-9900KF (8C/16T) + RTX 3060 12 GB + 64 GB DDR4 + NVMe (Windows)
> **เกณฑ์ "ใช้ได้จริง":** ≥30–40 tok/s (โต้ตอบลื่น) + คุณภาพดี + ภาษาไทยผ่าน (gate ของโปรเจค)
> **หลักฐานเรา:** EXP-011 (IQ1_M 74.7 vs IQ2_M 50.3 tok/s — bytes↓ → เร็ว↑ แต่ IQ1_M ล้ม Thai tones),
> EXP-017 (CPU lane bandwidth-bound — spill เยอะ = ตาย), carteakey/community benchmark 2026-07

---

## 🏆 Tier 1 — ตัวหลัก (ใช้ของเดิม + ปรับ config ที่ยังไม่เคยวัด)

### 1. Qwen3.6-35B-A3B (มีอยู่แล้ว — D:\models\Qwen3.6-35B-A3B-GGUF\)
Community verdict 2026: *"INSANE even for VRAM-constrained systems"* — เป็นตัวชูโรงของคลาส 12 GB
(SWE-bench 73.4, coding/reasoning/multilingual เก่ง รวมไทย)

| quant | ขนาด | สถานะ | คาดการณ์บนเครื่องเรา |
|---|---|---|---|
| UD-IQ1_M | 9.36 GB | ✅ วัดแล้ว | **74.7 tok/s** แต่ **Thai tones ล้ม** (EXP-011) |
| UD-IQ2_M | 10.73 GB | ✅ วัดแล้ว | 43–56 tok/s, ไทยผ่าน — VRAM เต็ม (10.9 GB) → ช้าลง |
| **UD-IQ2_XXS** | **10.02 GB** | ⏸ **ยังไม่เคยวัด** | **จุดหวานที่พลาดไป**: ใหญ่กว่า IQ1_M นิดเดียว (fit มีเผื่อ) → น่าจะ ~60–75 tok/s + คุณภาพ > IQ1_M (ไทยน่าจะผ่าน) |
| **UD-IQ3_XXS** | 12.30 GB | ⏸ ยังไม่เคยวัด | เกิน VRAM นิดหน่อย → `--fit on` spill ~0.3 GB (EXP-017 บอก spill น้อย = ยังเร็ว) — คุณภาพขยับชัด |

**บทเรียน:** เราวัดแค่หัวกับท้ายของบันได quant — **IQ2_XXS (จุดกลาง) ไม่เคยถูกวัด** = lever ฟรีจากของเดิม

### 2. Gemma 4 26B-A4B QAT + MTP (ดาวน์โหลดใหม่ ~14 GB)
- ไฟล์: `unsloth/gemma-4-26B-A4B-it-qat-GGUF` — **UD-Q4_K_XL 13.27 GB** + MTP draft Q8_0 **0.43 GB**
- Benchmark 2026-07 (RTX 4070 12 GB, llama.cpp mainline): baseline 38.5 → QAT 69 → **QAT+MTP 100.6 tok/s**
  (`--fit on --fit-target 1536 --spec-draft-model ... --spec-type draft-mtp --spec-draft-n-max 2 --flash-attn on -ctk f16 -ctv f16`)
- บน 3060 ของเรา (bandwidth ~70% ของ 4070): คาด **~45–60 tok/s (ไม่ใช้ MTP) / ~65–85 tok/s (ใช้ MTP)**
- **จุดแข็ง:** QAT Q4 ≈ คุณภาพ Q8 (intelligence-per-byte สูง) + 128K–262K context
- **ความเสี่ยง (ต้องวัด):** Thai ยังไม่มีหลักฐานบน Gemma 4 · QAT flat quant มีรายงาน regression ในงาน multi-constraint (blogger กำลัง benchmark)
- ✅ **Feasibility ยืนยันแล้วบน build เรา** (bb7049f7 รู้จัก Gemma4 arch — probe ด้วย MTP draft ผ่าน)

---

## 🥈 Tier 2 — ตัวเลือกสำรอง

| โมเดล | ขนาด | คาดการณ์ | หมายเหตุ |
|---|---|---|---|
| Phi-4 14B | Q4 ~8 GB | 25–32 tok/s | best reasoning-per-GB (MMLU 84.8) — แต่ช้ากว่า MoE ตัวหลัก |
| Gemma 4 12B QAT | ~7 GB | ? (120 tok/s อ้างบน 4070 — ยังไม่ชัวร์บน 3060) | multimodal — ถ้า 120 tok/s จริง = ตัวเลือกเร็วสุด |
| Llama 4 Scout 17B | 109B total — **ไม่ fit 12 GB** | — | guide บางที่เขียน "10 GB" ผิด (สับสน active/total) — ตัดทิ้ง |

---

## 🎯 แผนทดสอบที่แนะนำ (test-first, ค่าใช้จ่ายต่ำสุดก่อน)

1. **[ฟรี] วัด UD-IQ2_XXS ของ Qwen3.6** (10.02 GB — ดาวน์โหลด ~10 GB) → tok/s + ชุดไทย 9 ข้อ (เดียวกับ EXP-011) → ถ้าผ่านไทย + ≥60 tok/s = **ได้ทั้งเร็วทั้งดีจากของเดิมทันที**
2. **[14 GB] วัด Gemma 4 26B QAT+MTP** → tok/s + ชุดไทย 9 ข้อ → เทียบกับ Qwen3.6 IQ2_XXS/IQ3_XXS
3. **ตัวชนะ = daily driver** ของระบบ (บันทึกลง MODEL_INVENTORY + EXP ใหม่)

## 🔍 ที่มาข้อมูล (2026-07/08)

- r/LocalLLaMA: "Qwen3.6 35B A3B is INSANE…", "110 tok/s 12GB + ik_llama.cpp", "Gemma 4 26B QAT+MTP 100 tok/s"
- promptquorum.com/local-llms (VRAM tier guide 2026)
- carteakey.dev/blog/local-inference/gemma-4-26b-qat-mtp/ (benchmark ตาราง + flags)
- unsloth HF repos (quant ladder + ขนาดไฟล์จริง)
- ik_llama.cpp (ikawrakow) — fork ที่ให้ +45% บน Qwen3.6 (76→110) — ยังไม่มี Windows binary release; ถ้าอยากได้ต้อง build เอง (งานใหญ่ — ไว้เป็น option ทีหลัง)

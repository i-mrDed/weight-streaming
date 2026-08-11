# โมเดลที่รันแล้วใช้ทำงานได้จริงบนเครื่องนี้ (12 GB VRAM) — Shortlist 2026-08

> **เครื่อง:** i9-9900KF (8C/16T) + RTX 3060 12 GB + 64 GB DDR4 + NVMe (Windows)
> **เกณฑ์ "ใช้ได้จริง":** ≥30–40 tok/s (โต้ตอบลื่น) + คุณภาพดี + ภาษาไทยผ่าน (gate ของโปรเจค)
> **หลักฐานเรา:** EXP-011 (IQ1_M 74.7 vs IQ2_M 50.3 tok/s — bytes↓ → เร็ว↑ แต่ IQ1_M ล้ม Thai tones),
> EXP-017 (CPU lane bandwidth-bound — spill เยอะ = ตาย), carteakey/community benchmark 2026-07

---

## 🏆 Tier 1 — ตัวหลัก (วัดแล้วทุกตัว — EXP-011/018/019)

### 1. Qwen3.6-35B-A3B (มีอยู่แล้ว — D:\models\Qwen3.6-35B-A3B-GGUF\)
Community verdict 2026: *"INSANE even for VRAM-constrained systems"* — เป็นตัวชูโรงของคลาส 12 GB

| quant | ขนาด | สถานะ | วัดจริงบนเครื่องเรา |
|---|---|---|---|
| UD-IQ1_M | 9.36 GB | ✅ วัดแล้ว | **74.7 tok/s** แต่ **Thai tones ล้ม 0/6** (EXP-011) |
| UD-IQ2_M | 10.73 GB | ✅ วัดแล้ว | 43–56 tok/s, ไทยผ่าน (EXP-011) — VRAM เต็ม (10.9 GB) |
| UD-IQ2_XXS | 10.02 GB | ✅ วัดแล้ว | **61–66 tok/s** แต่ **Thai tones ล้ม 1/6** (EXP-018) — ใช้ได้สำหรับ non-Thai |

### 2. Gemma 4 26B-A4B QAT + MTP (ดาวน์โหลดแล้ว — C:\Users\dedch\models\Gemma4-26B-A4B-QAT\)
- ไฟล์: `gemma-4-26B-A4B-it-qat-UD-Q4_K_XL.gguf` 14.25 GB + `MTP/mtp-gemma-4-26B-A4B-it-Q8_0.gguf` 0.46 GB
- Benchmark 2026-07 (RTX 4070 12 GB): QAT+MTP **100.6 tok/s**; บน 3060 เรา: **45–47 tok/s** (EXP-019)
- **✅ วัดแล้ว (EXP-019): Thai gate 9/9 + Thai tonal 6/6 PERFECT — คำแรกบนเครื่องนี้ที่ผ่านครบที่ความเร็วใช้ได้**
- MTP บน build เรา: `--spec-draft-model <draft> --spec-type draft-mtp --spec-draft-n-max 2` → **+20%** (37.6→45.1 warm)
- **จุดแข็ง:** QAT Q4 ≈ คุณภาพ Q8 — ข้ามหน้าผาคุณภาพของ IQ quant (EXP-011/018) ได้ทั้งหมด

## 🏆 สรุป verdict (หลัง EXP-019)

| ใช้เมื่อ | โมเดล | tok/s | หมายเหตุ |
|---|---|---|---|
| **ภาษาไทย / คุณภาพสูงสุด** | **Gemma 4 26B QAT+MTP** | **45–47** | Thai 9/9 + tonal 6/6 — daily driver ใหม่ |
| เร็วสุดที่ไทยผ่าน | Qwen3.6 IQ2_M | 43–56 | ตัวเดิม (EXP-011) |
| non-Thai speed | Qwen3.6 IQ2_XXS | 61–66 | Thai tonal ล้ม (EXP-018) |
| speed-first | Qwen3.6 IQ1_M | 74.7 | Thai tonal ล้ม (EXP-011) |

---

## 🥈 Tier 2 — ตัวเลือกสำรอง

| โมเดล | ขนาด | คาดการณ์ | หมายเหตุ |
|---|---|---|---|
| Phi-4 14B | Q4 ~8 GB | 25–32 tok/s | best reasoning-per-GB (MMLU 84.8) — แต่ช้ากว่า MoE ตัวหลัก |
| Gemma 4 12B QAT | ~7 GB | ? (120 tok/s อ้างบน 4070 — ยังไม่ชัวร์บน 3060) | multimodal — ถ้า 120 tok/s จริง = ตัวเลือกเร็วสุด |
| Llama 4 Scout 17B | 109B total — **ไม่ fit 12 GB** | — | guide บางที่เขียน "10 GB" ผิด (สับสน active/total) — ตัดทิ้ง |

---

## 🎯 แผนทดสอบ (ทำเสร็จหมดแล้ว — EXP-018/019)

1. ✅ **วัด UD-IQ2_XXS ของ Qwen3.6** → 61–66 tok/s แต่ **ไทยล้ม 1/6** → reject (EXP-018)
2. ✅ **วัด Gemma 4 26B QAT+MTP** → **45–47 tok/s + ไทย 9/9 + tonal 6/6** → **ชนะ = daily driver ไทยใหม่** (EXP-019) → config sweep เจอ **t12 = 49–51 tok/s** (EXP-020)
3. ✅ **วัด Gemma 4 12B QAT+MTP** → **75.7 tok/s + ไทย 9/9 + tonal 6/6** → **daily driver เร็วสุด** (EXP-022)
4. ✅ **engine swap proxy**: mainline b10357 ≈ b9967 (EXP-021) → ik build เลื่อน (ดู `IK_LLAMA_EVAL.md`)
5. ✅ **บันทึก** MODEL_INVENTORY + EXP ใหม่ + recommended list ใน Hub

## 🏆 Leaderboard สุดท้าย (12 GB VRAM — วัดจริง, clean room)

| โมเดล | tok/s | ไทย tonal | ใช้เมื่อ |
|---|---|---|---|
| **Gemma 4 12B QAT+MTP** | **76** | ✅ 6/6 | daily driver เร็วสุด (EXP-022) |
| Qwen3.6 IQ1_M | 74.7 | ❌ 0/6 | non-Thai speed (EXP-011) |
| Qwen3.6 IQ2_XXS | 61–66 | ❌ 1/6 | non-Thai speed (EXP-018) |
| **Gemma 4 26B QAT+MTP** | **49–51** | ✅ 6/6 | quality-first ไทย (EXP-019/020) |
| Qwen3.6 IQ2_M | 43–56 | ✅ | ไทย (EXP-011) |

> **บทสรุป: ความเร็ว + ภาษาไทย อยู่ด้วยกันได้แล้วบน 12 GB — 12B QAT+MTP (76 tok/s) หรือ 26B QAT+MTP (50 tok/s) ตามระดับงาน** — หมดยุคต้องเลือกอย่างใดอย่างหนึ่ง

## 🔍 ที่มาข้อมูล (2026-07/08)

- r/LocalLLaMA: "Qwen3.6 35B A3B is INSANE…", "110 tok/s 12GB + ik_llama.cpp", "Gemma 4 26B QAT+MTP 100 tok/s"
- promptquorum.com/local-llms (VRAM tier guide 2026)
- carteakey.dev/blog/local-inference/gemma-4-26b-qat-mtp/ (benchmark ตาราง + flags)
- unsloth HF repos (quant ladder + ขนาดไฟล์จริง)
- ik_llama.cpp (ikawrakow) — fork ที่ให้ +45% บน Qwen3.6 (76→110) — ยังไม่มี Windows binary release; ถ้าอยากได้ต้อง build เอง (งานใหญ่ — ไว้เป็น option ทีหลัง)

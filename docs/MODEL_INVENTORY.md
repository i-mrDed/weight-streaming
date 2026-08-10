# Model Inventory (บันทึกตำแหน่ง + บทบาทของโมเดลทั้งหมด)

> อัปเดตล่าสุด: 2026-08-10 — ควรอัปเดตทุกครั้งที่ดาวน์โหลด/ลบ/ย้ายโมเดล
> **กฎ:** ดาวน์โหลดผ่าน hub → เขียนที่ `WS_MODELS_DIR` (ถ้าตั้ง) หรือโฟลเดอร์ default
> (รวม `~/models` = `C:\Users\<user>\models` บน Windows) — ดู `weight_stream/server/config.py`
> และหน้า Models → LIBRARY ของ console เพื่อดูรายการจริงเสมอ

## 📍 โมเดลหลัก (ใช้งาน/วัดผล)

| โมเดล | quant | ขนาด | ที่อยู่ (เครื่องนี้) | แหล่ง | บทบาท | สถานะ |
|---|---|---|---|---|---|---|
| DeepSeek-V4-Flash-0731 | UD-IQ3_XXS | 98 GB | `C:\Users\dedch\models\UD-IQ3_XXS\` | unsloth (HF) | **โมเดลหลักของ EXP-012** — พิสูจน์รัน 104 GB บน 64 GB RAM | ✅ วัดเสร็จ (EXP-012: 1.5–1.9 tok/s, disk-bound) · ⏸ รอตัดสินใจลบเพื่อคืนที่ให้ IQ2_M |
| Qwen3.6-35B-A3B | UD-IQ2_M | 10.7 GB | `D:\models\Qwen3.6-35B-A3B-GGUF\Qwen3.6-35B-A3B-UD-IQ2_M.gguf` | unsloth (HF) | **Thai-safe benchmark บน 12 GB** (43–56 tok/s) — ก่อน EXP-019 เป็น daily driver ไทย | ✅ ใช้ประจำ |
| Qwen3.6-35B-A3B | UD-IQ2_XXS | 10.0 GB | `D:\models\Qwen3.6-35B-A3B-GGUF\Qwen3.6-35B-A3B-UD-IQ2_XXS.gguf` | unsloth (HF) | non-Thai speed king (61–66 tok/s) — Thai tonal FAIL (EXP-018) | ✅ วัดเสร็จ (EXP-018) |
| Qwen3.6-35B-A3B | UD-IQ1_M | 9.4 GB | `D:\models\Qwen3.6-35B-A3B-GGUF\Qwen3.6-35B-A3B-UD-IQ1_M.gguf` | unsloth (HF) | speed-first (74.7 tok/s) — Thai tonal FAIL | ✅ วัดเสร็จ (EXP-011) |
| **Gemma 4 26B-A4B** | QAT UD-Q4_K_XL + MTP draft Q8_0 | 14.25 + 0.46 GB | `C:\Users\dedch\models\Gemma4-26B-A4B-QAT\` (+ `MTP\`) | unsloth (HF) | **NEW daily driver (ไทย): Thai gate 9/9 + tonal 6/6 PERFECT, 45–47 tok/s ด้วย MTP (EXP-019)** | ✅ วัดเสร็จ (EXP-019) — ใช้กับ `--spec-type draft-mtp` |
| Qwen3-0.6B-Q8_0 | Q8_0 | 0.6 GB | `C:\Users\dedch\models\Qwen3-0.6B-Q8_0.gguf` | — | draft/helper ขนาดเล็ก | ✅ |

## 🧠 Embedding models

| โมเดล | quant | ขนาด | ที่อยู่ | บทบาท |
|---|---|---|---|---|
| Qwen3-Embedding-4B | Q4_K_M | 2.3 GB | `D:\models\Qwen3-Embedding-4B-GGUF\` | embedding หลัก |
| bge-m3 | f32 | 2.1 GB | `D:\models\bge-m3-f32-gguf\` | embedding |
| bge-m3 | q8_0 | 0.6 GB | `D:\models\bge-m3-q8_0-gguf\` | embedding |
| embeddinggemma-300m | q8_0 | 0.3 GB | `D:\models\embeddinggemma-gguf\` | embedding เล็ก |

## 🧪 โมเดลทดสอบ (research/models — ใน repo)

| โมเดล | quant | ขนาด | บทบาท |
|---|---|---|---|
| Qwen1.5-MoE-A2.7B | Q2_K | 5.9 GB | ทดสอบ backend/MoE (test suite, smoke test) |
| Llama-3.2-1B-Instruct | Q2_K | 0.6 GB | test/smoke |
| qwenpus0.6B | Q2_K | 0.3 GB | test/smoke |

## 📥 เป้าหมายดาวน์โหลดถัดไป

| โมเดล | quant | ขนาด | ต้องการพื้นที่ | สถานะ |
|---|---|---|---|---|
| Gemma 4 26B-A4B | QAT Q4_K_M (เล็กลงจาก Q4_K_XL ถ้าต้องการประหยัด VRAM) | ~12–13 GB | ~13 GB | ⏸ ตัวเลือกถ้า Q4_K_XL spill รบกวน (ตอนนี้ 45–47 tok/s ใช้ได้) |
| DeepSeek-V4-Flash-0731 | **UD-IQ2_M** (`--variant iq2m`) | ~96 GB | ~40 GB | ⏸ เลื่อนก่อน (กำไร 8% ไม่คุ้ม — ตัดสินใจแล้ว) |

## 🗑️ ประวัติการลบ

| เมื่อ | โมเดล | เหตุผล |
|---|---|---|
| (ว่าง) | | |

---

## วิธีค้นหาตำแหน่งโมเดล (ถ้าลืมอีก)

```bash
# 1. ดูจาก console: หน้า Models → LIBRARY (โชว์ทุกโฟลเดอร์ที่ระบบสแกน)
# 2. ดู config จริง: curl http://127.0.0.1:8765/v1/config
# 3. หาไฟล์จากดิสก์:
find /d /c -maxdepth 4 -iname "*.gguf" -size +500M 2>/dev/null | head -20
```

> หมายเหตุ: ตัวเลข "98 GB" ในตาราง = ขนาดจริงบนดิสก์ (du); ขนาดที่ HF โฆษณา (104 GB)
> คือผลรวม shard ตาม manifest — ต่างกันเพราะการนับหน่วย/compression

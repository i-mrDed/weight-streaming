# EXP-012 Phase 2.5: แผนสลับไป TacoTakumi IQ3_XXS (ถ้า baseline ช้า)

> สถานะ: **STANDBY** — รอผล baseline วัดจริง (Phase 2) ก่อนตัดสินใจ
> วันที่: 2026-08-10 · อ้างอิง: quant-options-comparison.md

## เกณฑ์ตัดสินใจ (เขียนก่อนวัด — กัน bias หลังเห็นตัวเลข)

| สัญญาณจาก baseline (UD-IQ3_XXS, 104 GB) | การตัดสินใจ |
|---|---|
| tok/s ≥ 3-4 และ quality ใช้ได้ | **อยู่ UD-IQ3_XXS** — เล็กสุด พอดี RAM 64 GB |
| tok/s 2-3 แต่ quality ดี | พิจารณา TacoTakumi **ถ้า** disk พอ (ต้อง +11 GB) |
| tok/s < 2 (IQ dequant บน CPU เป็นคอขวดจริง) | **สลับ TacoTakumi IQ3_XXS (115 GB)** — imatrix + KLD ดีกว่า อาจชดเชย |
| page-fault ระบุว่า disk-bound มากกว่า CPU-bound | เปลี่ยนที่อื่นก่อน (ดิสก์/RAM) — ไฟล์ไม่ใช่ปัญหา |

**หลัก:** สลับเมื่อหลักฐานชี้ว่า *quant pipeline* (IQ dequant บน CPU) เป็น
คอขวด — ไม่ใช่เมื่อ disk/page-cache เป็นคอขวด (กรณีนั้นไฟล์ไหนก็ไม่ช่วย)

## วิธีวัดว่า IQ dequant เป็นคอขวดจริง (ก่อนสลับ)

บน baseline UD-IQ3_XXS ให้ดูจาก harness output:
- `disk_mb_per_token` สูง (หลาย MB/tok) → **disk-bound** — เก็บ RAM/ดิสก์
  ดีกว่า อย่าเสียเงิน 11 GB ไปกับไฟล์ใหม่
- `disk_mb_per_token` ต่ำ (< 0.5) แต่ tok/s ยังต่ำ → **CPU dequant-bound**
  → สลับ TacoTakumi ได้เหตุผล (แม้ยังเป็น IQ3 เหมือนกัน — แต่ imatrix
  ช่วยคุณภาพ ไม่ช่วยความเร็วมาก; จริงๆ ถ้า CPU-bound ควรดู MXFP4 mix
  ตามคำเตือนผู้ทำ: "mix ที่เก็บ MXFP4/K-quants จะชนะ")

⚠️ **ข้อควรรู้:** TacoTakumi ก็เป็น IQ3 เหมือนกัน — ถ้า CPU-bound จริง
สลับไปก็ไม่เร็วขึ้นมาก (ผู้ทำวัด 1.52× vs MXFP4 บน rig ที่ spill น้อย)
**ทางเลือกที่ตรงกว่าเมื่อ CPU dequant-bound: bartowski MXFP4 source
(~120 GB+) หรือ mix ที่เก็บ experts เป็น MXFP4** — ต้องสำรวจเพิ่ม

## ขั้นตอนสลับ (เมื่อตัดสินใจแล้ว)

```bash
# 1. เช็คพื้นที่ (ต้องว่าง ≥ 121 GB)
python scripts/download_dsv4flash.py --dry-run --variant tacotakumi

# 2. ดาวน์โหลด (hub resume ได้ ถ้าหลุดกลางคัน)
python scripts/download_dsv4flash.py --variant tacotakumi

# 3. ลบ UD-IQ3_XXS ชุดเดิม (คืน 104 GB) — หลัง verify TacoTakumi โหลดได้
rm -rf "C:/Users/dedch/models/UD-IQ3_XXS"

# 4. วัด matrix เดิม (เปรียบเทียบ apples-to-apples)
WS_TEST_MODEL="C:/Users/dedch/models/DeepSeek-V4-Flash-0731-IQ3_XXS-imat-00001-of-00004.gguf" \
  WS_TEST_MODEL_ID="dsv4flash" python scripts/measure_dsv4flash.py
```

## ตัวชี้วัดเปรียบเทียบ (บันทึกทั้งสองชุดใน results.md)

- tok/s (cold + warm) ทุก config — ตัวชี้วัดหลัก
- `faults_per_token` / `disk_mb_per_token` — บอกว่า expert มาจากไหน
- Quality spot-check ชุดเดียวกัน (ไทย 3 ข้อ + โค้ด) — เทียบ KLD จริงกับ
  ตัวเลขผู้ทำ (0.263 vs ~0.29)

## ถ้าต้อง MXFP4 mix จริง (CPU-bound หนัก)

- bartowski/DeepSeek-V4-Flash-0731-GGUF (native MXFP4, source ของ
  TacoTakumi) — ขนาด ~120 GB+ ต้องเช็ค
- ต้อง verify backend b9967 รองรับ MXFP4 tensor (type 39) — gate มี
  block size แล้ว (17 B/32 elems) แต่ยังไม่เคยทดสอบ load จริง
- วางเป็น **Phase 3** (หลัง baseline + TacoTakumi) — ไม่ทำพร่ำเพรื่อ

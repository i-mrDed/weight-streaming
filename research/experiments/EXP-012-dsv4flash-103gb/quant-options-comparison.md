# EXP-012: เปรียบเทียบตัวเลือกไฟล์ DS V4 Flash 0731 (2026-08-10)

> หลัง pre-flight พบว่ามี 3 ทางเลือกหลัก — บันทึกข้อเท็จจริง + ความเหมาะสม
> กับเครื่องนี้ (i9-9900KF, RAM 64 GB, RTX 3060 12 GB, expert spill 100%)

## ตารางเทียบ (ข้อมูล verified 2026-08-10)

| | unsloth UD-IQ3_XXS | TacoTakumi IQ3_XXS | TacoTakumi IQ3_XXS-D_IQ3_S |
|---|---|---|---|
| ที่มา | unsloth (ไฟล์เป้าหมายเดิมของเรา) | requant จาก bartowski MXFP4 | requant จาก bartowski MXFP4 |
| ขนาด | 4 shards **104.21 GB** | 4 shards **115.26 GB** | 4 shards **119.59 GB** |
| Experts | IQ3_XXS (down) / IQ2_XS (gate) | IQ3_XXS ทั้งหมด (129 tensors) | gate/up IQ3_XXS, down IQ3_S |
| Attention/shared | Q8_0/Q6_K/BF16 ปน | Q8_0 (จาก source) | Q8_0 (จาก source) |
| Mean KLD | ~0.29 (โดยประมาณ, tier 3-bit) | **0.2629** | **0.2386** |
| Same top-1 | ~83% | 83.91% | **84.65%** |
| Speed (CPU-spill rig, 5-GPU) | — | **15.0 t/s (1.52× vs MXFP4)** | 13.9 t/s (1.41×) |
| imatrix | — | ✓ | ✓ |
| เหมาะกับ | RAM 64 GB (เล็กสุด) | RAM ≥ 120 GB | RAM ≥ 128 GB |

## ข้อค้นพบสำคัญ (ความหมายต่อเครื่องนี้)

1. **KLD ดีกว่า unsloth UD-IQ3_S ทั้งคู่** แต่เปรียบกับ **UD-IQ3_XXS** ของเรา
   (104 GB) ยังไม่มีตัวเลข KLD โดยตรง — tier ใกล้เคียงกัน (3-bit)

2. **Speed 1.4-1.5× vs MXFP4 บน CPU-spill** — ตรงกับเส้นทาง `--cpu-moe`
   ของเรา แต่ต้องระวัง: วัดบน rig 5-GPU (96 GB VRAM, spill น้อย) — เครื่อง
   เรา spill 100% (64 GB RAM < 104 GB ไฟล์) ผลอาจต่าง

3. **คำเตือนจากผู้ทำ (สำคัญสุด):** "ถ้า CPU ช้ากับ IQ quants (dequant path)
   mix ที่เก็บ MXFP4/K-quants จะชนะ" — เครื่องเรา i9-9900KF (Skylake-class,
   AVX-512 ไม่มีบน 9900KF) — **ต้องวัดจริง** ว่า IQ3 dequant บน CPU เรา
   ช้าแค่ไหน เทียบกับ EXP-011 ที่ Qwen IQ1_M ได้ 79 tok/s (นั่นคือ IQ1_M
   บน GPU ผ่าน n-cpu-moe 0 — ไม่ใช่ CPU spill!)

4. **0731 ยากต่อการ quant ที่ ~3-bit** — ทั้งสอง pipeline (unsloth + TacoTakumi)
   ได้ KLD แย่ลงเมื่อเทียบกับ pre-0731 — เป็นสมบัติของ weights ไม่ใช่ pipeline

## ข้อสรุปสำหรับ EXP-012

- **ไฟล์เป้าหมายเดิม (UD-IQ3_XXS 104.21 GB) ยังเป็นตัวเลือกแรก** — เล็กสุด
  พอดีกับ RAM 64 GB + เหลือดิสก์/headroom ที่สุด และ KLD tier เดียวกัน
- **TacoTakumi IQ3_XXS (115 GB) เป็นทางเลือกถ้าดิสก์เหลือ** — KLD ดีกว่า
  เล็กน้อย + imatrix + เร็วขึ้นบน spill (แต่เครื่องเรา spill 100% — ต้อง
  วัดจริง)
- **ตัดสินใจหลังวัด baseline:** ถ้า tok/s จาก UD-IQ3_XXS ต่ำเกินไปเพราะ
  IQ dequant บน CPU → พิจารณา TacoTakumi (imatrix อาจช่วย quality) หรือ
  สำรวจ mix ที่เก็บ MXFP4/K-quants (ตามคำแนะนำผู้ทำ)

## แหล่งข้อมูล

- TacoTakumi README: https://huggingface.co/TacoTakumi/DeepSeek-V4-Flash-0731-GGUF
- Reddit thread: https://www.reddit.com/r/LocalLLaMA/comments/1vd44uv/
- unsloth docs: https://unsloth.ai/docs/models/deepseek-v4

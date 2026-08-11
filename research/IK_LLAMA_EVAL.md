# ik_llama.cpp — Evaluation record (EXP track: "faster engine on 12 GB")

> สถานะ: **ยังไม่ทดสอบบนเครื่องนี้** — ต้อง build จากซอร์ส (ไม่มี Windows
> binary release) และเครื่องนี้ยังไม่มี toolchain ครบ บันทึกนี้คือข้อเท็จจริง
> ที่เจอจากการสืบหาข้อมูล + ผลการทดสอบตัวแทน (proxy) แล้ว

## Claim เดิม (จาก research รอบแรก)
- r/LocalLLaMA: "110 tok/s with 12GB VRAM on Qwen3.6 35B A3B and ik_llama.cpp"
  → บันทึกไว้ใน `MODELS_12GB_SHORTLIST.md` ว่าเป็น fork ที่ให้ +45% (76→110)
  แต่ **ยังไม่มี Windows binary release**

## ข้อเท็จจริงที่ตรวจเพิ่ม (2026-08-11)

### 1. ik_llama.cpp ไม่มี Windows binary — ต้อง build เอง
- `github.com/ikawrakow/ik_llama.cpp/releases` → มีแค่ tag `t0002`
  ("Unsuspended") **ไม่มี asset** ใดเลย
- README: วิธีใช้งานบน Windows = build เอง (docs/build.md)
- บันทึกเดิมของเราถูกต้อง: "ถ้าอยากได้ต้อง build เอง (งานใหญ่)"

### 2. เครื่องนี้ยังไม่มี toolchain สำหรับ build
```
cmake   → ไม่ติดตั้ง
nvcc    → ไม่ติดตั้ง (ไม่มี CUDA Toolkit)
cl      → ไม่มี (ไม่มี Visual Studio Build Tools)
```
การ build ต้องติดตั้งก่อน: VS Build Tools (~2–6 GB) + CUDA Toolkit (~3–4 GB)
+ cmake — รวม ~8–10 GB บนดิสก์ที่ตอนนี้ C: เหลือ 14 GB / D: 8.7 GB
(ติดแล้วจะเหลือ ~4–6 GB — เสี่ยงกับงานอื่น)

### 3. ตัวเลข 110 tok/s วัดบน GPU ที่เร็วกว่าเรา
- สรุป community (startupfortune + กระทู้ต้นทาง): **110 tok/s = RTX 4070 Super**
  — 4070S มี compute สูงกว่า 3060 มาก → ตัวเลขนั้น**ไม่ใช่เพดานจริงของเครื่องเรา**

### 4. ตัวเลขที่เทียบได้จริงบน RTX 3060 12 GB
- r/LocalLLaMA (janvitos, 2026-05): **"80 tok/s + 128K ctx บน 12 GB VRAM"
  Qwen3.6-35B-A3B + llama.cpp MTP** — ระบุ Hardware: **RTX 3060 12 GB**,
  Ryzen 9 5950X (16 threads ≈ i9-9900KF ของเรา)
- เทียบของเรา: Qwen3.6 IQ2_XXS = 61–66 tok/s (Jan b9967, EXP-018)
- → เพดานจริงของ fork บน 3060 น่าจะอยู่ที่ ~70–85 tok/s (กำไร ~15–30%
  เทียบกับ b9967) — ยังคุ้ม แต่ไม่ใช่ 110

## ทางเลือกที่ถูกกว่า: ทดสอบ official mainline prebuilt ก่อน
llama.cpp mainline มี **prebuilt Windows CUDA**: `llama-b10357-bin-win-cuda-12.4-x64.zip`
(250 MB, ดาวน์โหลดแล้วที่ `tools/llama-b10357/`) — b10357 ใหม่กว่า Jan b9967
และรองรับ CUDA 12.4 (เข้ากับ 3060) backend รองรับการสลับผ่าน `WS_LLAMA_SERVER`
— ทดสอบได้ทันทีโดยไม่ต้อง build: ถ้า mainline ใหม่กว่าไม่ช่วยเลย แปลว่า
3060 เป็นคอขวด → ik ก็ไม่น่าช่วยได้มาก; ถ้า mainline ช่วย → ค่อยตัดสินใจลงทุน build ik

## สรุปการตัดสินใจ
| ทาง | ต้นทุน | ค่าที่คาด | สถานะ |
|---|---|---|---|
| build ik_llama.cpp | ติดตั้ง toolchain ~8–10 GB + build หลายชม. | +15–30% (61→~80) | ⏸ เลื่อน — ไม่คุ้มตอนนี้ (ดิสก์ + เวลา) |
| mainline b10357 prebuilt (proxy) | 250 MB (มีแล้ว) | +0–15%? | ▶ กำลังวัด (เปรียบกับ b9967) |
| อยู่กับ Jan b9967 | 0 | 61–66 (IQ2_XXS) / 45–47 (Gemma MTP) | baseline |

## ผล proxy แล้ว (EXP-021, 2026-08-11) — mainline b10357 ≈ Jan b9967

วัด Qwen3.6 IQ2_XXS (default config, harness clean room) ด้วย official
prebuilt mainline b10357 (CUDA 12.4): **cold 62.3 / warm 56.7 tok/s** —
อยู่ในแถบเดียวกับ Jan b9967 (cold 43–62 / warm 52–61) → **engine เวอร์ชัน
ไม่ใช่คอขวดบนเครื่องนี้**

> ⚠️ บทเรียน: รอบแรกได้ 9 tok/s เพราะ prebuilt ไม่มี CUDA runtime DLL
> (ต้องโหลด `cudart-llama-bin-*.zip` แยก) — llama-server fallback เป็น
> CPU เงียบๆ โดยไม่มี error → ตรวจ device init (`--list-devices`) ก่อน
> เชื่อตัวเลขทุกครั้งที่สลับ engine

## สรุปการตัดสินใจ ik (อัปเดต)
- **เลื่อน build ik** — upstream mainline ไม่ชนะ b9967 เลย → โอกาสที่ fork
  จะให้ +45% บน 3060 ต่ำ (เพดานจริง ~80 tok/s ตามกระทู้ 3060-12GB)
- จะกลับมาลุยเมื่อ: ik มี Windows binary release, หรือมี toolchain+ดิสก์
  พอ และต้องการ +~30% จริงๆ
- lever ที่ได้ผลจริงบนเครื่องนี้ตอนนี้: **threads tuning (EXP-020: -t 12
  ให้ +13% บน Gemma)** — คิวต่อไป: sweep threads บน Qwen IQ2_XXS ด้วย

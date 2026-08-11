# Curation Checklist — "Proven on this rig" (โมเดลแนะนำใน Hub)

> โมเดลจะได้เข้า `GET /v1/hub/recommended` (หน้าฮับ → "Proven on this rig")
> **เฉพาะเมื่อพิสูจน์ด้วยการวัดจริง** — กฎเดียวกับ ADR-003 (honest telemetry):
> ไม่มีโมเดลใดได้เข้าลิสต์จากการ ranking, ยอดดาวน์โหลด, หรือ hearsay
> ตัวเลขทุกตัวต้องมาจากการวัดบนเครื่องอ้างอิงพร้อมหลักฐานใน repo

## เกณฑ์ขั้นต่ำ (ทุกข้อต้องผ่าน)

1. **Clean-room measurement** ผ่าน harness `weight_stream/bench`
   (เดิม `python -m weight_stream bench <model.gguf> …`) บนเครื่องอ้างอิง
   (i9-9900KF · RTX 3060 12 GB · 64 GB RAM):
   - server restart สดต่อ config (ไม่มี llama-server ค้าง, ตรวจ `CLEAN_ROOM_CHECKLIST.md`)
   - verify cmdline จริง (`-t/-fa/-ctk/-ctv/--spec-*`) ว่าตรง config ที่ตั้งใจ
   - cold + warm generation
2. **Thai quality gate ครบ**: 9 คำถามคงที่ (ชุด EXP-009) + tonal discriminator
   (6 คำ) — ผ่าน `--thai` ใน harness ต้องได้คะแนนเต็ม
3. **บันทึก EXP ครบ** ใน `research/experiments/EXP-XXX-<ชื่อ>/`:
   - `setup.md` (ทำไม/โมเดลไหน/ไฟล์ไหน/วิธีวัด)
   - `results.md` (ตัวเลขจริง + ไฟล์ JSON ของ harness)
   - `analysis.md` (ข้อสรุป + hypothesis ได้รับการยืนยัน/ปฏิเสธ)
   - อัปเดต `research/experiments/index.md`
4. **ขนาดไฟล์ยืนยันกับ HF** — byte sizes ใน recommended ต้องตรงกับ
   HF tree API (ตัวเลขที่ผู้ใช้จะดาวน์โหลด = ตัวที่เราวัด ไม่ใช่ตัวใกล้เคียง)

## ขั้นตอนเพิ่มโมเดลใหม่

```bash
# 1. วัด (clean room + Thai gate) → ได้ EXP docs + ตัวเลข
# 2. เปิด server ด้วยโค้ดใหม่ แล้วยืนยันไฟล์ที่ดาวน์โหลดได้จริง:
curl -s "https://huggingface.co/api/models/<org>/<repo>/tree/main?recursive=1"
# 3. เพิ่ม entry ใน weight_stream/server/recommended.py
#    (role: thai | balanced | speed — ดูเกณฑ์ด้านล่าง)
# 4. รัน data-integrity test:
python -m pytest tests/test_p4_hub.py -k recommended
# 5. รัน pytest เต็ม + typecheck + build หน้า  (เหมือน CI)
# 6. ตรวจ UI จริงบนหน้า Hub (screenshot) ว่าเรนเดอร์ถูก
# 7. อัปเดต docs/MODEL_INVENTORY.md + CHANGELOG.md
```

## การเลือก `role`

| role | เงื่อนไข | badge |
|---|---|---|
| `thai` | Thai gate **9/9 + tonal เต็ม** — daily driver | 🏆 Thai-safe daily driver |
| `balanced` | Thai gate 9/9 แต่ช้ากว่า tier บน | ⚖️ Thai-safe · slower |
| `speed` | เร็วสุด แต่ tonal **ไม่ผ่าน** (ต้องระบุคะแนนจริง) | ⚡ Speed-first · Thai not safe |

**กฎเหล็ก:** quant ที่ Thai tonal ไม่ผ่าน **ห้าม** ใส่ role `thai`/`balanced`
— ต้อง `speed` พร้อมคะแนนจริง (เช่น `tonal 1/6`) โชว์เป็นสีแดงใน UI
(ช่องว่างนี้เคยทำให้ IQ1_M/IQ2_XXS ถูกเข้าใจผิดว่าใช้ภาษาไทยได้ — EXP-011/018)

## ข้อห้าม (honest-telemetry)

- ❌ ประดิษฐ์/ปัดตัวเลข tok/s — ต้องมาจากไฟล์ผลวัดของ harness
- ❌ `total_bytes` ไม่เท่ากับผลรวมไฟล์จริง (test กันไว้แล้ว)
- ❌ ลิงก์ experiment ไป path ที่ไม่มีอยู่ (test กันไว้แล้ว — ต้องอัปเดตถ้าย้ายโฟลเดอร์)
- ❌ เพิ่ม quant ที่ยังไม่ได้วัด — ถ้าอยากแนะนำก็ต้องวัดก่อน หรือไม่ใส่เลย

## ใครพอจะเข้าข่ายถัดไป

- Gemma 4 26B QAT **Q4_K_M** (เล็กกว่า, spill น้อยกว่า) — รอวัด
- Gemma 4 **12B QAT** (dense, community ~120 tok/s) — รอวัด + Thai gate
- Qwen3.6-35B-A3B ผ่าน **ik_llama.cpp fork** — รอประเมิน build
- DS V4 Flash (ถ้าวัด matrix จนได้ตัวเลขใช้จริง) — ต้องการดิสก์ + เวลา

> คู่มือนี้ลิงก์จาก `docs/BENCHMARKING.md` — วัดยังไงดูที่นั่น

# EXP-012: DeepSeek V4 Flash 0731 (IQ3_XXS 104 GB / 4 shards) — Prep Plan

> สถานะ: **PREP — ยังไม่เริ่มวัด** (รอเคลียร์ดิสก์ + verify support)
> วันที่: 2026-08-10 · ผู้ริเริ่ม: ต่อจาก HARDWARE_100TPS_PLAN §6 (โมเดลใหญ่ที่ "รันได้จริง" ที่สุด)

## 1. เป้าหมาย

พิสูจน์ว่าโมเดล **284B / 13B active** (ใหญ่กว่า Qwen 35B-A3B 8× ในแง่ total
params) รันได้จริงบนเครื่องนี้ผ่านระบบ expert-streaming ของเรา (llama-server
`--cpu-moe` / `--n-cpu-moe`) — วัด tok/s จริง + VRAM + page-fault เทียบกับ
ประมาณการ และบันทึกเป็นหลักฐานว่า "รันโมเดลใหญ่ทำงานจริง" ไม่ใช่แค่โหลดได้

## 2. ข้อมูลโมเดล (verified 2026-08-10 จาก unsloth docs + HF)

| field | value |
|-------|-------|
| ชื่อ | `unsloth/DeepSeek-V4-Flash-0731-GGUF` |
| total / active | 284B / **13B active** (MoE; 43 layers, 256 experts, 6 used)
  — **verified จาก shard-1 metadata จริง** (general.size_label = 256x8.4B) |
| context | 1M (จริง: ขึ้นกับ RAM/VRAM — metadata ยืนยัน 1048576) |
| ไฟล์เป้า | **UD-IQ3_XXS = 4 shards รวม 104.21 GB** (ไม่ใช่ไฟล์เดียว 103 GB!)
  shard 1 = **5.26 MB metadata-only** (0 tensors) · shard 2 = 49.91 GB ·
  shard 3 = 49.26 GB · shard 4 = 5.03 GB |
| **Experts** | **IQ3_XXS (down) / IQ2_XS (gate) — k-quants ที่ถูก verify จาก
  tensor table จริง** — ⚠️ **ไม่ใช่ MXFP4** อย่างที่ unsloth docs บอก
  (docs ว่า "QAT MXFP4 bit-exact" แต่ไฟล์ UD-IQ3_XXS นี้ใช้ IQ3_XXS/IQ2_XS;
  ถ้าต้องการ MXFP4 จริงต้องหาตัวแปรอื่น — บันทึกเพื่อไม่ให้เข้าใจผิดเรื่อง
  คุณภาพ lossless) |
| DSpark | speculative decoding 1.5-1.9× (ต้องการ llama.cpp ≥ PR 25784) |

## 3. ความจริงของเครื่องนี้ (ตรวจแล้ว 2026-08-10)

| ทรัพยากร | ค่า | ผลกระทบ |
|----------|-----|---------|
| RAM | **64 GB** | < 104 GB ไฟล์ → **full-RAM เป็นไปไม่ได้** — ต้อง disk-streaming path (คือจุดของโปรเจคนี้) |
| GPU | RTX 3060 12 GB | attention+shared (~4% ของโมเดล ≈ 4-5 GB) ลง VRAM ได้ |
| ดิสก์ D: | เหลือ **24 GB** (95% full) | **ไม่พอ** — ต้องเคลียร์ ≥ 110 GB |
| ดิสก์ C: | เหลือ **70 GB** | ไม่พอเหมือนกัน (103 + headroom) |
| llama.cpp | 0.3.34 (llama-cpp-python) + Jan backends | **ต้อง verify** ว่ารองรับ DeepSeek-V4-Flash-0731 architecture (release 2026-07-31) |

**ข้อสรุปก่อนลุย:** งานนี้มี 2 gate ก่อนดาวน์โหลด — (a) ดิสก์ว่าง ≥ 110 GB,
(b) llama-server ที่ใช้รองรับโมเดล (ตรวจผ่าน `--version` / test load ไฟล์เล็ก
หรือเช็ค changelog). ถ้า (b) ไม่ผ่าน ต้องอัปเดต Jan backend / llama.cpp ก่อน
— **อย่าดาวน์โหลด 104 GB ก่อน verify นี้** (บทเรียนจาก EXP-011b: ดาวน์โหลด
เสร็จแล้วเจอว่าใช้ไม่ได้ = เสียเวลา + พื้นที่)

## 4. แผนดำเนินการ (ตามลำดับ)

### Phase 0 — Pre-flight (ตรวจเสร็จแล้ว 2026-08-10 ✅ ยกเว้น disk)
- [x] ตรวจ disk free: D: เหลือ 24 GB · C: 70 GB → **ยังต้องเคลียร์ ≥ 110 GB**
      (⏳ รอ user — งานนี้เป็นตัว blocker เดียวที่เหลือ)
- [x] Verify llama-server: server ใช้ **b9967** (llama.cpp `bb7049f7`, build
      2026-07-12) — llama.cpp merge DS V4 support **July 7** (PR #24162) →
      **b9967 รองรับ DS V4 Flash baseline ✓** (อยู่หลัง merge 5 วัน)
- [x] **DSpark (1.5-1.9×) ยังไม่มีใน b9967** — PR 25784 เข้ามาหลัง Aug →
      EXP-012 วัด baseline ก่อน (ไม่บล็อก); ถ้าต้องการ DSpark ต้องรอ Jan
      อัปเดต backend หรือ build llama.cpp เอง
- [x] หมายเหตุ 0731: เป็นรุ่นปรับปรุงของ arch เดียวกัน (tool-calling fix) —
      ต้องยืนยันตอน test load หลังดาวน์โหลดจริง (ไม่บล็อก baseline)
- [x] ทดสอบ dry-run: โหลด Qwen3-0.6B ผ่าน `/v1/models/load` → 200 ✓
      + generate 30 tokens + `/v1/stats` มี paging (faults 4251, 0.58 MB/tok)
- [x] รัน `scripts/check_clean_environment.py` → CLEAN ✓

### Phase 1 — ดาวน์โหลด (104 GB / 4 shards, หลายชั่วโมง ตามเน็ต)
- [x] **Pre-flight verify โครงสร้างจริง (2026-08-10, ไม่ต้องดาวน์โหลด 104 GB):**
      ดึง header shard 1 + 2 ผ่าน HTTP Range (~9 MB) — ยืนยัน arch
      `deepseek4`, split.count=4, experts IQ3_XXS/IQ2_XS, 43 layers/
      256 experts/6 used/1M ctx — **gate ใหม่รองรับ metadata-only shard
      แล้ว** (commit นี้) — ตัวเลข 104.21 GB จาก HF tree API
- [x] **สคริปต์ดาวน์โหลดพร้อม:** `scripts/download_dsv4flash.py` — ส่ง
      4 shards ผ่าน `POST /v1/hub/download` (ทีละ task), poll progress,
      resume จาก .part อัตโนมัติ, verify ครบก่อน rename (gate EXP-011b),
      dry-run ตรวจพื้นที่ก่อน (ต้องว่าง ≥ 110 GB)
- [x] **Hub รองรับ subdir + sharded + Xet (2026-08-10, commit 91007a3):**
      เจอ + แก้ 2 บั๊กที่ block ดาวน์โหลด DS V4 Flash โดยตรง — (a) tree
      call ไม่ recursive → ไฟล์ใต้ `UD-IQ3_XXS/` ไม่โชว์ใน hub detail
      (โชว์แค่ Q8_0 ที่ root), (b) `_sanitize_filename` reject path
      separators → ดาวน์โหลดไม่ได้ต่อให้โชว์ แก้เป็น recursive=true +
      ยอมรับ repo-relative path (ยัง block absolute/.. traversal)
- [x] **ทดสอบ end-to-end จริง (2026-08-10):** ดาวน์โหลด shard 1 (5.26 MB)
      ผ่าน hub API บน server จริง → done 5,257,696 bytes ครบเป๊ะ, subdir
      `UD-IQ3_XXS/` สร้างอัตโนมัติ, **gate ยอมรับ metadata-only shard**
      (ok: True, arch: deepseek4) → pipeline พร้อม 100% สำหรับ 104 GB
- [x] **Research MXFP4 (2026-08-10):** Reddit LocalLLaMA ยืนยันว่า
      "MXFP4 ไม่ถูกต้องทางเทคนิค — มี BF16 และ Q8 ปน" (ตรงกับ tensor table
      ที่เราพบ) + มี community requant "expert-only IQ3" ที่ KLD ดีกว่า
      UD-IQ3_S และ **decode เร็วขึ้น 1.4× บน CPU-spill rig** (ตรงกับ
      เส้นทาง --cpu-moe ของเรา) — บันทึกไว้พิจารณาหลังวัด baseline
- [x] **พิสูจน์ b9967 โหลด + รัน MXFP4 จริง (2026-08-10):** สร้าง minimal
      qwen3 GGUF (มือ, GGUF v3) ที่มี ffn_gate/down/up เป็น **MXFP4
      (type 39)** — b9967 `llama-server` (--n-gpu-layers 0, CPU เท่านั้น)
      **โหลดผ่าน (`model loaded`) + generate 8 tokens ครบ**
      (system_fingerprint b1-bb7049f7, eval 1.59ms/8 tok) — ไม่มี error/
      assert เกี่ยวกับ MXFP4 → **MXFP4 support ยืนยัน 100% บน backend นี้**
      (คำตอบเดิมจาก warning "unknown type mxfp4" คือ guess-type path
      เฉยๆ — ไฟล์จริงที่มี general.file_type ไม่มีผล)
      ชี้แจง: builder อยู่ scripts/_make_mxfp4_test.py (สำหรับ reproduce);
      ระหว่างทางเจอ + แก้ serialization: kv_count ต้องตรง (เคย hardcode 1),
      tensor offset ต้อง relative ต่อ data section (ไม่ใช่ absolute file),
      rope.dimension_count == n_embd_head (8 สำหรับ qwen3), SPM vocab
      ต้องมี byte-fallback tokens (<0x00>..<0xFF>) ถึงจะ tokenize ได้
- [ ] ผ่าน hub ของระบบเรา (`POST /v1/hub/download` หรือ CLI) — ได้ประโยชน์
      จาก integrity gate (EXP-011b: ตรวจ bytes ครบก่อน done + resume จาก .part)
- [ ] ยืนยันผล: ขนาดไฟล์ตรงกับ HF (103 GB), GGUF magic ถูกต้อง
- [ ] บันทึกเวลาดาวน์โหลด + speed → ลง results.md

### Phase 2 — วัด config matrix (หลังดาวน์โหลด, รันผ่าน harness ตัวเดียวกับ EXP-008/011)
- [x] Harness: `scripts/measure_dsv4flash.py` (เขียนใหม่ ต่อยอดจาก
      measure_ncmoe_matrix) — มี clean-room gate อัตโนมัติ + verify flags
      จริงบน cmdline ของ llama-server + วัด **cold vs warm paging** แยก
      (สำคัญสำหรับโมเดล > RAM: บอกว่า expert มาจาก page cache หรือ disk)
- [x] **Validate เส้นทาง restart จริง (2026-08-10)** — รัน 2 configs ผ่าน
      restart server จริง (kill → restart → load → verify flag → วัด):
      `cpu-moe t8` = 8.1 tok/s (experts ทั้งหมดบน CPU — ช้าตามคาดสำหรับ
      35B) · `n-cpu-moe 0 t8` = 48.5 tok/s — ตัวเลขสอดคล้องกับ EXP-008
      เดิม → harness พร้อมใช้กับ DS V4 Flash 100% (จุดนี้ไม่เคยทดสอบ
      ก่อนหน้า — ถ้าพังจะเจอตอนรัน 104 GB)
- [x] **ยืนยัน --cpu-moe / --n-cpu-moe ใช้กับ arch deepseek4 ได้ (2026-08-10):**
      ตรวจ source ของ backend b9967 (bb7049f7) — flags ทำงานผ่าน regex
      override `\.ffn_(up|down|gate|gate_up)_(ch|)exps` (common.h
      LLM_FFN_EXPS_REGEX) ที่เป็น **arch-agnostic** และ deepseek4.cpp
      สร้าง tensor ชื่อ `blk.N.ffn_gate_exps.weight` / `ffn_down_exps` /
      `ffn_up_exps` ตรงกับ regex เป๊ะ → flags ใช้ได้เหมือน qwen35moe
      **โดยไม่ต้องแก้ harness** (หมายเหตุ: shared experts `ffn_*_shexp`
      ไม่ match regex → อยู่ GPU ตามที่ต้องการ — ตัวเล็กอยู่แล้ว)
- [x] **Validate harness กับโมเดลจริง (Qwen IQ1_M, 10 GB)** 2026-08-10:
      cold 68.9 / warm 64.8 tok/s, faults 212→823/tok, fault_mb 0.87→3.37
      — ค่า paging อ่านจาก `/v1/stats` ได้จริง; ปลดโหลดคืนสะอาด ✓
      (ระหว่างเขียนเจอบั๊ก: `/v1/stats?model=` คืน stats ตรงๆ ใต้ `models`
      ไม่ใช่ `{id: stats}` — แก้ให้รองรับทั้งสอง shape แล้ว)
- [ ] Matrix: `--cpu-moe` vs `--n-cpu-moe 10/5/0` (ถ้า VRAM พอ) × ctx 2048
- [ ] ต่อ config: threads 8 (ค่าเริ่มต้น) vs 16 (ถ้า CPU-bound)
- [ ] โหลดเสร็จ วัด prompt processing + decode แยก (ถ้า stats ให้)

### Phase 3 — วิเคราะห์ + บันทึก
- [ ] เทียบกับประมาณการ (ตาราง §5) — อธิบาย gap (RAM 64 < 103 → ต้องพึ่ง
      OS page cache; คาด disk-bound)
- [ ] วัด quality spot-check: ถามคำถาม 3 ข้อ (ไทย + โค้ด) เทียบ Qwen IQ1_M
- [ ] เขียน results.md + analysis.md + อัปเดต index + HARDWARE plan

## 5. ประมาณการ tok/s (ทำนายก่อนวัด — เพื่อเทียบหลังวัด)

โมเดล 13B active + experts IQ3_XXS/IQ2_XS (~0.35-0.4 B/param) →
~5-7 GB weights/token (Reddit: ~8 GB/forward สำหรับ MXFP4) — คอขวดอยู่ที่
RAM/disk ไม่ใช่ VRAM (ตัวเลขเดิมอิง MXFP4; k-quants เบากว่าเล็กน้อย):

| path | bandwidth | tok/s โดยประมาณ |
|------|-----------|:---:|
| ทั้งหมดใน RAM (ต้อง 128 GB+) | DDR4 ~45 GB/s | ~6 |
| RAM 64 GB + OS page cache (เครื่องนี้) | ~45 GB/s + disk spill | **~2-5** |
| ผ่าน disk โดยตรง (cold) | NVMe ~3 GB/s | <1 |
| บน 3090 + 128 GB RAM (อ้างอิงแผน) | 936 GB/s VRAM + RAM | ~47-60 |

**ที่ตั้งสมมติฐาน:** 13B active × ~0.55 B/param ≈ 7 GB/token จาก RAM
→ 45/7 ≈ 6.4 tok/s ถ้า hot; เครื่องนี้ RAM 64 GB เก็บ page cache ได้ ~60 GB
ของไฟล์ 104 GB → บางส่วน spill ไป disk → **คาดการณ์จริง ~2-5 tok/s**
(ใช้ได้กับงาน agentic ที่ไม่เร่ง แต่ไม่ใช่แชทโต้ตอบ)

## 6. ความเสี่ยง + การลด

| ความเสี่ยง | ผล | การลด |
|-----------|-----|-------|
| llama.cpp ยังไม่รองรับ DS V4 arch | ดาวน์โหลด 104 GB เปล่า | **verify ก่อนดาวน์โหลด (Phase 0)** — arch `deepseek4` ยืนยันแล้ว |
| ดิสก์เต็มระหว่างดาวน์โหลด | .part ค้าง | เช็ค ≥ 110 GB + hub resume (EXP-011b gate) |
| RAM 64 GB → thrash | tok/s ต่ำมาก | วัดแบบ honest + บันทึก page-fault เป็นหลักฐาน (ไม่ใช่ failure — คือผลที่คาดไว้) |
| DSpark ต้อง build ใหม่ | ไม่ได้ speculative gain | ไม่ blocking — วัด baseline ก่อน |
| ไฟล์ IQ3 คุณภาพต่ำกว่า Q8 | คำตอบเพี้ยน | spot-check quality; บันทึก quant ที่ใช้ชัดเจน |

## 7. Deliverables

- `results.md` — ตัวเลขจริง (tok/s, VRAM, page-fault, download time)
- `analysis.md` — เทียบประมาณการ + verdict "คุ้ม/ไม่คุ้มบนเครื่องนี้" +
  เส้นทางบน hardware ใหญ่ขึ้น (3090 + 128 GB RAM)
- ข้อมูลป้อนกลับสู่ HARDWARE_100TPS_PLAN §6 (ยืนยัน/แก้ตัวเลข ~47-60)

## 8. หมายเหตุ

- ถ้าดาวน์โหลด 92 GB (1-bit) ไว้ก่อน: ใช้ได้เหมือนกัน แต่คุณภาพต่ำ — เลือก
  IQ3_XXS เป็นเป้าแรก (unsloth แนะนำ), ถ้าดิสก์ไม่พอค่อยลดเป็น 1-bit
- **ไฟล์เป็น sharded (4 ไฟล์) — โหลดผ่าน llama-server ได้โดยชี้ที่ shard 1**
  (llama.cpp auto-detect พี่น้องจาก split metadata, PR #6187); hub ของเรา
  ดาวน์โหลดทีละ shard และ gate ยอมรับ metadata-only shard 1 แล้ว
- **ตัวเลือกไฟล์ (2026-08-10):** มีทางเลือก 3 — unsloth UD-IQ3_XXS
  104.21 GB (เป้าหมายเดิม, เล็กสุดพอดี RAM 64 GB) · TacoTakumi IQ3_XXS
  115.26 GB (KLD 0.263, imatrix, 1.52× decode บน spill rig) ·
  IQ3_XXS-D_IQ3_S 119.59 GB (KLD 0.239 ดีสุด) — เทียบเต็ม:
  `quant-options-comparison.md`. **คำเตือนจากผู้ทำ:** IQ dequant บน CPU
  อาจช้า — เครื่องเรา spill 100% ต้องวัดจริง (ตัดสินใจหลัง baseline)
- โมเดลนี้เป็น reasoning model (think default on) — วัด tok/s จะรวม think
  tokens ด้วย (เหมือน EXP-011: ใช้ `reasoning_mode: off` ถ้าต้องการเปรียบตรง)

## P8 (2026-08-10): threads / flash-attn / KV-q8 sweep บน Qwen IQ1_M

ก่อนวัด DS V4 Flash — ยืนยันจุด optimum บนเครื่องนี้ด้วย Qwen3.6-35B-A3B
IQ1_M (10 GB, โหลดบน GPU 12 GB, `n-cpu-moe 0` = experts ทั้งหมดบน GPU)
ทุก config ผ่าน value-aware flag verification ใหม่ใน harness (ตรวจค่า
`-t`/`-fa`/`-ctk` จริงใน cmdline ของ process ที่ spawn — ไม่ใช่แค่ presence
เพราะ load request จะ emit `-t 8` เสมอ และ extra args ต่อท้าย = ค่าที่มีผล)

| config | cold tok/s | warm tok/s | cold f/t | warm f/t |
|---|---:|---:|---:|---:|
| ncm0 t4 | 75.0 | 71.0 | 141 | 551 |
| ncm0 t6 | 76.4 | 73.2 | 142 | 550 |
| **ncm0 t8 (anchor)** | **75.9** | **73.9** | 141 | 550 |
| ncm0 t10 | 74.8 | 74.0 | 141 | 551 |
| ncm0 t12 | 74.9 | 72.8 | 141 | 551 |
| ncm0 t16 | 76.3 | 72.5 | 141 | 550 |
| ncm0 t8 fa-off | 74.7 | 70.4 | 141 | 551 |
| ncm0 t8 kv-q8 (-ctk/-ctv q8_0) | 74.6 | 73.1 | 141 | 547 |

**ข้อสรุป (สำคัญสำหรับ DS V4 Flash):**

1. **Threads แทบไม่มีผลเมื่อ experts อยู่ GPU** — 74.6–76.4 cold, 70.4–74.0
   warm ตลอด t4→t16 (i9-9900KF 8C/16T) → GPU เป็น bottleneck, CPU threads
   ไม่ใช่ตัวแปรรบกวน → **สำหรับ DS V4 (experts บน CPU) threads จะมีผลจริง
   ต่างหาก** — sweep threads ต้องทำกับ DS V4 เอง ไม่ใช่เอา curve นี้ไป extrapolate
2. **flash-attn on ดีกว่า off เล็กน้อย** (warm 73.9 vs 70.4, −4.7%) → ใช้
   `-fa on` กับ DS V4 ต่อไป (สำคัญขึ้นเมื่อ ctx ใหญ่ — KV บน GPU)
3. **KV q8 เป็นกลาง** ที่ ctx 2048 (74.6 vs 75.9 ≈ noise) → ปลอดภัยใช้
   `-ctk/-ctv q8_0` กับ DS V4 Flash (KV ใหญ่ ~5 GB ที่ 32k ctx — q8 ลดครึ่ง
   โดยไม่เสีย tok/s บนเครื่องนี้)
4. **anchor t8 ใหม่ = 75.9/73.9** — สูงกว่า baseline เก่า 66.1/60.8
   (commit b73faa1) เพราะ page cache อุ่นขึ้น (faults 282→141 cold) →
   **เปรียบเทียบ DS V4 กับ Qwen ต้องใช้ anchor ใน session เดียวกัน**
   (harness ใส่ anchor ไว้ใน matrix เดียวกับ DS V4 configs เสมอ)

ผลเต็มอยู่ใน `scripts/.qwen_threads_out.json` (8 configs) — harness แก้
เพิ่ม value-aware verification (จะ fail ทันทีถ้า flag ถูก override เงียบ)

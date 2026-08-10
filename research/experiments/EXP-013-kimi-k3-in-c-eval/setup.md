# EXP-013: Deep-Research — kimi-k3-in-c (Kimi K3 2.8T บน 8GB RAM ใน C)

> สถานะ: **Complete (research + evaluation)** · วันที่: 2026-08-10
> แหล่งที่ศึกษา: repo + บทความที่ user ส่งมา + โคลน repo มาอ่านโค้ดจริง (75 MB, `/tmp/kimi-k3-in-c`)

## 1. แหล่งที่มา

1. **Repo:** https://github.com/FareedKhan-dev/kimi-k3-in-c
   - Kimi K3 inference ใน **C99 บริสุทธิ์ 176 KB** (6 ไฟล์ C + 2 headers, ~5,950
     บรรทัด) — ไม่มี BLAS/framework/GPU, ใช้แค่ libm + OpenMP
   - รันโมเดล **2.78T params / 1.56 TB checkpoint** บน **RAM 8 GB** (CPU-only)
   - License: Apache-2.0
2. **บทความ:** "Building Kimi K3 2.8T Model in C to Run on 8GB RAM"
   (Fareed Khan, Level Up Coding, ~6 วันก่อน) — บทความ member-only; เนื้อหา
   ทางเทคนิคตรงกับ README ของ repo (ผู้เขียนเดียวกัน) — ใช้ README + โค้ดเป็นหลัก

## 2. ผลลัพธ์ที่เขาอ้าง (docs/data/ มี measurement จริง)

| RAM | s/token | เกิดอะไรขึ้น |
|-----|:---:|---------|
| 8 GB (laptop) | 26.5 | โมเดล stream จาก disk ทุก step |
| 32 GB | 24.2 | บางส่วนใน RAM |
| 64 GB | 19.8 | มากขึ้นใน RAM |
| 128 GB+ | 5.6 | ทั้งไฟล์ใน RAM, ไม่รอ disk |

- **Output byte-identical ทุก budget** (8 GB ถึง 224 GB) — แค่ clock เปลี่ยน
- วัดบน EPYC 7763 124-core, 228 GB RAM, NVMe 3.2 TB, O_DIRECT 5.4-6.1 GB/s
- KV cache 2.37 MB/position

## 3. กลไกหลัก (4 reductions: 5,560 GB → 1,560 GB → 113.5 GB → 8.24 GB RSS)

1. **Experts ส่งมาแบบ MXFP4 อยู่แล้ว (0.53125 B/param)** — 1.447 TB จาก 1.56 TB
   = 82,432 routed experts (896 × 92 ชั้น) × 17,547,264 bytes — **stream อย่างเดียว
   ไม่เคย resident**. 2 shared experts รันทุก token → ต้อง resident (กับดักที่
   คำนวณมือผิดบ่อย)
2. **ไม่ dequant experts — คูณจาก packed nibbles ตรงๆ** — ถ้า dequant เป็น f32
   จะต้องเขียน **194 GB/token** ก่อนคูณ (1 expert 17.5 MB → 132 MB f32 × 1,472
   experts/token) → ใช้ E2M1 LUT (16 ค่า) + E8M0 scale table (256 ค่า) คูณตรง
3. **KDA + MLA** — สถาปัตยกรรม attention ของ Kimi K3 (KDA = recurrent attention
   ที่ memory ไม่โต, MLA = latent เดียวแทน 96 heads) — ลด KV/state
4. **Streaming trunk (reduction หลักสำหรับ memory)** — pack 93 dense layers ลง
   ไฟล์ `trunk.bin` 109 GB ไฟล์เดียว ที่ layer L อยู่ offset รู้ล่วงหน้า → อ่าน
   ครั้งเดียวต่อ layer ผ่าน **O_DIRECT** — `--trunk-gb` เป็น "dial" ปรับ memory
   ตามงบประมาณ

**ส่วนเสริมที่ทำให้เชื่อถือได้:**
- **Gate ladder**: test แบบ weightless (oracle 13-layer) — teacher forcing,
  greedy decode, incremental decode ต้อง match reference **เป๊ะ** ก่อนแตะ checkpoint จริง
- **Verification**: 96 shards ตรวจ byte-exact ต่อ shard (จับคู่ shard ผิดที่
  total ไม่ออก) · config reader **refuses to guess** (หาย field = error ไม่ใช่ default)
  · tokenizer เทียบ tiktoken 45/45 cases + roundtrip byte-identical
- **`-ffp-contract=off`**: scalar/OpenMP/AVX2 paths ต้อง bit-identical — perf
  change ไม่มีทางกลายเป็น accuracy change เงียบๆ
- **Telemetry ที่ซื่อตรง**: `TRUE resident hit rate` (แยก prefetch ออกจาก
  resident — hits counter มักอ่าน 100% หลอก) + `I/O share of wall clock` (41-71%)
  + `PEAK RSS` (getrusage, quote ตัวนี้ไม่ใช่ plan)
- **บทเรียนการวัด**: O_DIRECT เร็วกว่า buffered (3.2 vs 2.3 GB/s) · เปิด
  unattended-upgrades ก่อนวัด (กิน core) · **ให้ memory กับ trunk ก่อน expert
  cache** (1.69× ที่งบ 128 GB) · `max` preset ไม่เร็วกว่า `server` (96 GB เสียเปล่า)

## 4. สิ่งที่เขาทำไม่ได้ / ข้อจำกัด (เพื่อเทียบให้ยุติธรรม)

- **รองรับแค่ Kimi K3 รุ่นเดียว** — อ่าน safetensors เฉพาะโครงสร้างนี้; เปลี่ยน
  โมเดล = เขียนใหม่ทั้ง binder/kernels
- **CPU-only ไม่มี GPU path** — 124-core EPYC ยังได้แค่ 0.18 tok/s (5.6 s/token)
- **Linux x86-64 เท่านั้น** (O_DIRECT, posix_memalign, getrusage)
- **Base model — ไม่มี chat template** (output คือ continuation ไม่ใช่ reply)
- ไม่มี API/console/UI — เป็น CLI ไบนารีตัวเดียว
- 26.5 s/token บน 8 GB = ใช้งานจริงไม่ได้ (พิสูจน์แนวคิดเรื่อง memory มากกว่า)

## 5. หลักฐานที่เก็บ

- Repo โคลนที่ `/tmp/kimi-k3-in-c` (อาจถูกล้าง) — สรุปสำคัญอยู่ใน analysis.md
- ตัวเลข measurement: README §Part IV + `docs/data/memory-ladder.tsv` (ใน repo)
- บทความ: https://levelup.gitconnected.com/building-kimi-k3-2-8t-model-in-c-to-run-on-8gb-ram-a5792cbf3b59

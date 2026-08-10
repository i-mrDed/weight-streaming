# EXP-013: Analysis — kimi-k3-in-c vs Weight-Streaming (คะแนนเทียบทุกมิติ)

## 1. ภาพรวมสองระบบ (ต่างกันที่แกนหลัก)

| | **kimi-k3-in-c** | **Weight-Streaming (เรา)** |
|---|---|---|
| แกนหลัก | เขียน engine เองใน C สำหรับ **โมเดลเดียว** (Kimi K3) | ใช้ llama.cpp (GGUF ecosystem) เป็น backend + layer จัดการ streaming/VRAM/UI เอง |
| ภาษาพื้นฐาน | C99, 176 KB binary | Python (FastAPI) + Vue console + llama.cpp subprocess |
| กลยุทธ์ memory | MXFP4-packed experts stream จาก disk (O_DIRECT) + packed trunk + LRU expert cache | `--cpu-moe`/`--n-cpu-moe` (experts จาก RAM/VRAM tiering) + page-fault instrumentation |
| โมเดลที่รันได้ | เฉพาะ Kimi K3 (safetensors) | ทุก GGUF ที่ llama.cpp รองรับ (Qwen, DeepSeek, GLM…) |
| ผลลัพธ์จริง | Kimi K3 2.78T บน 8 GB RAM, 0.04-0.18 tok/s | Qwen 35B-A3B IQ1_M 79.1 tok/s บน 3060 12 GB |

**สำคัญ:** ไม่ใช่คู่แข่ง — เป็นคนละชั้น. เขาพิสูจน์ "โมเดล 2.78T รันบน RAM 8 GB"
(extreme memory engineering, ประสิทธิภาพต่ำ); เราพิสูจน์ "โมเดลที่เหมาะสมรัน
**เร็วพอใช้ทำงานจริง** บนการ์ดที่มี" (performance ที่ใช้งานได้, กับโมเดลเล็กกว่า)
จุดที่เขาเหนือกว่าคือบทเรียน engineering ที่เรานำมาใช้ได้ (§3)

## 2. คะแนนรายมิติ (1-10, ให้คะแนนตามหลักฐาน ไม่ใช่ตามกระแส)

| # | มิติ | kimi-k3-in-c | เรา | หลักฐาน / เหตุผล |
|---|------|:---:|:---:|---------|
| 1 | **ความสามารถรันโมเดลยักษ์** (memory ceiling) | **10** | 4 | เขา: 2.78T/1.56TB บน RAM 8 GB (189× จาก checkpoint) — byte-identical ทุกงบ. เรา: 35B-A3B เต็ม VRAM; โมเดล >24GB ต้อง stream (ยังไม่ได้พิสูจน์กับ 100GB+) |
| 2 | **ความเร็วใช้งานจริง (tok/s)** | 3 | **8** | เขา: 0.04-0.18 tok/s (26.5-5.6 s/token). เรา: 79.1 tok/s (Qwen IQ1_M) — ต่างกันที่เป้าหมาย (เขาพิสูจน์ feasibility, เราพิสูจน์ usability) |
| 3 | **ความหลากหลายของโมเดล** | 2 | **8** | เขา: โมเดลเดียว (K3 binder เฉพาะ). เรา: ทุก GGUF (Qwen/DeepSeek/GLM/…) + quant หลายระดับ + hub |
| 4 | **การใช้ GPU** | 1 | **9** | เขา: ไม่มี GPU path เลย. เรา: VRAM tiering (--n-cpu-moe), nvidia-smi tracking, /v1/hardware |
| 5 | **ความแม่นยำ/ความถูกต้อง (numerical)** | **10** | 7 | เขา: bit-exact oracle gates, shard byte-verify, config refuses-to-guess, -ffp-contract=off. เรา: honest quality evals (EXP-011 พบ tonal regression จริง), integrity-gated downloads — แต่ rely บน llama.cpp |
| 6 | **ความพร้อมใช้งานเป็นผลิตภัณฑ์** | 4 | **9** | เขา: CLI ตัวเดียว, base model ไม่มี chat template. เรา: FastAPI + Vue console + stats/chat/hub/settings + i18n (en/th) |
| 7 | **ความน่าเชื่อถือของ telemetry** | **9** | 7 | เขา: TRUE resident hit rate, I/O share of wall clock, PEAK RSS. เรา: page-fault counter (cold 175→warm 0.55 MB/token), /v1/stats tok/s + p95 — ใกล้เคียงแต่ยังไม่มี "I/O share" และ expert hit-rate |
| 8 | **การวัดประสิทธิภาพที่สะอาด** | **9** | 8 | เขา: cgroup memory ladder, เปิด updater ก่อนวัด, O_DIRECT วัดแบบ engine อ่านจริง. เรา: clean-room gate (EXP-005/006 contamination → gate กันหมด), harness อัตโนมัติ — เทียบเท่ากัน, เขาเหนือเรื่อง storage micro-benchmark |
| 9 | **การพกพา/ติดตั้ง** | 5 | **7** | เขา: C99 แต่วิ่งได้แค่ Linux x86-64 (O_DIRECT). เรา: Python + Windows-native (เครื่อง user ใช้ได้เลย) แต่พึ่ง backend build |
| 10 | **ความยั่งยืน/community** | 3 | **8** | เขา: ผู้เขียนเดียว, โมเดลเดียว (K3 ใหม่ = เขียนใหม่). เรา: llama.cpp ecosystem + GGUF + HF hub — โมเดลใหม่ออกมาเรารองรับได้ทันที (DS V4 Flash เป็นตัวอย่าง) |
| 11 | **การจัดการ disk/download** | 6 | **8** | เขา: download-model.sh + per-shard byte verify + pack-trunk. เรา: hub integrity gate (EXP-011b — จับบั๊กตัวเลขปลอมจริง), resume จาก .part, byte-exact 10,047,749,088 |
| 12 | **จุดแข็งด้านสถาปัตยกรรมที่ "กุญแจ"** | **9** | 6 | เขา: packed trunk (single-read ต่อ layer), MXFP4 multiply-ไม่-dequant, expert LRU + prefetch, resident-hit honesty. เรา: --n-cpu-moe tiering ที่พิสูจน์แล้ว + page-fault channel (ไม่แตะ llama.cpp) — แต่ยังไม่มี trunk packing/prefetch |

**คะแนนรวม: kimi-k3-in-c 71/120 · เรา 87/120** — เราเหนือในมิติ
product/ความเร็ว/ความหลากหลาย; เขาเหนือใน memory-engineering/rigor —
**จุดที่ควรยืมมาจากเขาคือ §3 ไม่ใช่ย้ายไปใช้ engine เขา**

## 3. ไอเดียที่ยืมได้ (เรียงตามความคุ้มค่า ต่อระบบเรา)

### A. ให้ memory/VRAM กับ trunk (attention+shared) ก่อน expert cache — **ยืนยันด้วยข้อมูลเราเอง**
เขาวัดว่า "give the trunk memory before the expert cache = 1.69× ที่งบ 128 GB"
— **ตรงกับ EXP-008 ของเราเป๊ะ**: `--n-cpu-moe 10` (attention+shared บน GPU,
10/40 ชั้น experts) = 44.5 vs `--n-cpu-moe 0` เต็ม = 53.9; `--cpu-moe` หมด =
17.9 — ลำดับความสำคัญเดียวกัน: attention ใน VRAM ก่อน แล้วค่อย experts
→ เอามาเขียนเป็น "guidance" ใน quant advisor/auto-tune ได้ (เราทำด้วยข้อมูล
จริงแล้ว เขายืนยันอิสระ)

### B. Packed trunk / sequential read locality (สำหรับโมเดล 100GB+)
เขาจัด layer ลงไฟล์เดียว offset รู้ล่วงหน้า → อ่านครั้งเดียวต่อ layer ผ่าน
O_DIRECT. เรา (llama.cpp) ใช้ mmap ของ GGUF อยู่แล้ว — แต่สำหรับ DS V4 Flash
103 GB ที่ RAM 64 GB ไม่พอ **การอ่านแบบรู้ offset ล่วงหน้า + prefetch ลำดับ
ชั้นต่อชั้น** อาจลด seek แบบเดียวกับเขา → วัด disk bandwidth แบบ engine อ่านจริง
(`tools/devbw.py` แนวคิด) ก่อน/หลัง

### C. "TRUE resident hit rate" telemetry (แยก prefetch หลอก)
เขาชี้ว่า hits counter มักอ่าน 100% หลอก (prefetch ดึงมาเมื่อครู่) — ต้องแยก
"resident จริง". **เรามีช่องทางเทียบเท่าอยู่แล้ว: page_faults.py** — cold
175 MB/token → warm 0.55 MB/token (300×) — แต่ยังไม่ expose เป็น metric ราย
config ใน stats. → เพิ่ม "paging MB/token" ลง `/v1/stats` ต่อ model = เทียบ
ได้โดยตรงว่า expert stream มาจาก RAM หรือ disk (สำคัญมากสำหรับ EXP-012
DS V4 Flash ที่ RAM ไม่พอ)

### D. Config reader refuses-to-guess + byte-exact shard verify
เราทำครึ่งหนึ่งแล้ว: `_wait_ready()` ตรวจ /props กัน stale server, hub ตรวจ
Content-Length ครบก่อน done. เขาเพิ่มระดับ: ตรวจ **ทุก tensor name/dtype/shape**
+ per-shard size — เอามาใช้กับ hub download ได้ (ตรวจ GGUF tensor table ปลายไฟล์
— backlog EXP-011b item 1 ที่ค้างอยู่!)

### E. O_DIRECT เร็วกว่า buffered (ตรงข้ามความคาด)
บนเครื่องเขา O_DIRECT 3.2 vs buffered 2.3 GB/s → ใช้ O_DIRECT. ควรวัดบนเครื่องนี้
(Windows: ต่าง — ไม่มี O_DIRECT เดียวกัน; แต่หลักการ "วัด disk แบบ engine อ่าน
จริง ไม่ใช่ dd" ใช้ได้) → เพิ่มลง check_clean_environment หรือ harness ก่อน EXP-012

## 4. สิ่งที่เขาพิสูจน์ว่าเป็นไปได้ (ผลต่อแผนเรา)

1. **Kimi K3 2.78T รันบนเครื่องเดี่ยวได้จริง** — แต่ 0.04 tok/s = ใช้ทำงานไม่ได้
   → ยืนยัน verdict ของ HARDWARE plan: K3 = server-tier (ต้อง 128 GB+ RAM
   ถึงจะ 5.6 s/token ที่ยังช้า) — ไม่ใช่เป้าหมายเครื่องนี้
2. **แนวคิด "keep always-on resident, stream sleeping experts" = ถูกต้อง
   อิสระ** — เขาใช้กับ trunk/experts; เราใช้กับ VRAM tiering — หลักเดียวกัน
3. **โมเดลที่ "ใช้ได้จริง" ต้อง active params เล็กพอ** — K3 104B active ยังช้า
   ต่อให้ memory พอ → ยิ่งตอกย้ำ: **DeepSeek V4 Flash (13B active) คือเป้า
   ที่ถูกต้อง** (EXP-012) — 13B active ≈ 7 GB/token จาก RAM → tok/s ที่
   "ใช้ทำงานได้" บนเครื่องที่มี RAM พอ

## 5. สรุป

- kimi-k3-in-c เป็น **ผลงาน engineering ระดับสุดยอดด้าน memory** (bit-exact
  gates, MXFP4 non-dequant multiply, packed trunk, honest telemetry) —
  ควรศึกษาต่อ แต่ไม่ใช่สิ่งที่เรา "ตาม" — เราไม่ควรเขียน engine เองสำหรับ
  โมเดลเดียว
- **บทเรียนที่นำมาใช้กับเราทันที:** (A) เอา guidance trunk-first ใส่
  auto-tune/quant advisor, (C) expose page-fault เป็น metric ใน stats
  (สำคัญสุดสำหรับ EXP-012), (D) tensor-table verify ใน hub download,
  (B/E) วัด disk แบบ engine อ่านจริงก่อนลุยโมเดล 100GB+
- ตำแหน่งเชิงกลยุทธ์ของเรา (llama.cpp + streaming layer + console) คือ
  **ถูกต้อง** — โมเดลใหม่ออกมา (DS V4 Flash 0731) เราได้ทันทีโดยไม่ต้อง
  เขียน kernel; งานที่เหลือคือ streaming/VRAM/telemetry ให้ฉลาดขึ้นแบบเขา

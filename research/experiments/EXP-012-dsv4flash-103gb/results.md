
## Matrix run 2026-08-10

| config | cold tok/s | warm tok/s | cold faults/tok | warm faults/tok | cold disk MB/tok | warm disk MB/tok | VRAM MiB |
|---|---:|---:|---:|---:|---:|---:|---:|
| cpu-moe t8 | 1.5 | 1.8 | 68009 | 41872 | - | - | - |
| n-cpu-moe 42 t8 | 1.5 | 1.9 | 76548 | 40515 | - | - | - |
| cpu-moe t16 | 1.7 | 1.7 | 64935 | 36229 | - | - | - |
| n-cpu-moe 10 t8 | **FAILED** — HTTP Error 500: Internal Server Error |
| n-cpu-moe 0 t8 | 1.7 | 1.8 | 62933 | 40263 | - | - | - |

Best warm tok/s: **n-cpu-moe 42 t8** = 1.9 tok/s

## การวิเคราะห์ (EXP-012 ผลจริง, 2026-08-10)

**ผลลัพธ์หลัก: DS V4 Flash 104 GB บนเครื่องนี้ (RTX 3060 12 GB + 64 GB RAM)
รันได้ ~1.5–1.9 tok/s — เป็น disk-bound เต็มรูปแบบ** (36–77k
page faults/โทเคน = แต่ละโทเคนต้อง fault working set ~150–300 MB เข้ามาจาก
ดิสก์) — ทำงานได้จริงแต่ไม่ "ลื่นไหล" ตัวเลขนี้คือคำตอบที่ซื่อตรงของ
คำถาม "โมเดลใหญ่กว่า RAM รันได้แค่ไหนบนเครื่องนี้"

### ข้อค้นพบ 4 อย่าง

1. **config แทบไม่ต่างกัน (1.46–1.71 cold)** — bottleneck คือดิสก์ ไม่ใช่
   CPU/GPU → ปรับ threads/offload ได้กำไรแค่ ~15%: cpu-moe t16 ดีสุด cold
   (1.71), n-cpu-moe 42 ดีสุด warm (1.89), n-cpu-moe 0 (auto) ตามติด
   (1.65/1.83)
2. **`n-cpu-moe 0` รันได้ (เซอร์ไพรส์)** — harness ไม่ส่ง `-ngl` (auto) →
   `--n-cpu-moe 0` = ไม่มี layer ถูกบังคับ CPU = placement อัตโนมัติ
   (llama.cpp ใส่ที่พอดี ~7–9 GB ลง GPU) — OOM เฉพาะเมื่อบังคับ `-ngl 99`
   (พิสูจน์ด้วยมือ: cudaMalloc 77,361 MiB fail)
3. **`n-cpu-moe 10` OOM จริง** — 33 layers ของ experts (~74 GB) ถูกบังคับ
   ลง GPU 12 GB → crash ระหว่างโหลด (หลักฐาน: manual run `cudaMalloc
   failed: out of memory`, 50s)
4. **บั๊กที่เจอ + แก้ (commit 71f32ca):** `_wait_ready` timeout 60s สั้นไป
   สำหรับโมเดล >RAM — โหลด 104 GB บน cold cache ใช้ ~69s (วัดจริงด้วยมือ)
   → t16 fail ซ้ำทั้งที่โหลดปกติ แก้เป็น 300s (crash ยัง fail เร็ว เพราะ
   `_wait_ready` ตรวจ process exit ทุก 0.5s)

### ความสะอาดของการวัด

- รอบแรก (matrix + rerun) ตัวเลขสอดคล้องกัน (cpu-moe t8: 1.30/1.59 →
  1.48/1.76, n-cpu-moe 42: 1.44/1.98 → 1.46/1.89) → ไม่มีความผันแปร
  ที่บ่งชี้การปนเปื้อน
- **Jan เปิดตอนเริ่มทดสอบ — ไม่มีหลักฐานปนเปื้อน:** gate ตอนเริ่ม matrix
  พบ `port 8805: free` + ไม่มี llama-server ของ Jan (Jan เปิดแต่ idle ไม่
  spawn inference) · ความล้มเหลวอธิบายได้ครบด้วย OOM + timeout โดยไม่ต้อง
  พึ่งสมมติฐาน Jan · ยังไงก็ตาม re-run ทั้ง matrix บนระบบสะอาด (Jan ปิด)
  เพื่อความมั่นใจ — ผลสอดคล้อง
- `_wait_ready` มี port-collision guard อยู่แล้ว (ตรวจ /props model_path
  ตรงกับโมเดลที่โหลด — กัน server เก่า/Jan ตอบแทน)

### สรุป verdict

- **รันได้จริง: ใช่ (~1.5–1.9 tok/s)** แต่ห่างจาก "ใช้ได้อย่างลื่นไหล" มาก
- **กุญแจที่ไขได้จากตัวเลขนี้:** ต่อโทเคนต้องอ่าน ~150–300 MB จากดิสก์
  (faults × 4 KB) — bottleneck คือ bandwidth ของ disk→RAM→CPU pipeline
  ไม่ใช่ tok/s ของ CPU/GPU → ทางเดียวที่จะ "ขยาย VRAM 12 GB → 100+"
  คือ (ก) เพิ่ม RAM ให้โมเดลอยู่ใน page cache (128 GB RAM = ใส่ทั้งไฟล์ →
  fault เฉพาะรอบแรก) หรือ (ข) เพิ่ม VRAM ให้ experts อยู่ GPU มากขึ้น
  (HARDWARE_100TPS_PLAN) — ดู `phase25-tacotakumi-switch.md` สำหรับ
  เกณฑ์ตัดสินใจหลังตัวเลขนี้

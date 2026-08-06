# Clean-Room Checklist ก่อนวัดผลทุกครั้ง (EXP-009)

> **ที่มา:** EXP-005/006 ถูก invalidate เพราะ process ที่ไม่มีใครสังเกต —
> `weight_stream.server` เก่าบน :8804 ที่ spawn llama-server ไปทับ :8805
> ของเรา + Jan llama-server เก่าแก่ที่ตอบ `/health` แทนเป็นเวลาหลายวัน
> บทเรียน: **ห้ามเริ่มวัดถ้ายังไม่ได้ตรวจ process / port / VRAM**

## วิธีใช้

```bash
# ตรวจอย่างเดียว (ไม่ kill อะไรทั้งสิ้น)
python scripts/check_clean_environment.py

# โหมดเข้ม: warning ทุกอันถูก promote เป็น fail
python scripts/check_clean_environment.py --strict
```

**Exit code:** `0` = CLEAN (วัดได้) · `1` = WARN (อ่าน warning ก่อนวัด)
· `2` = FAIL (ห้ามวัด — ต้องแก้จนกว่าจะผ่าน)

`measure_ctx_scaling.py` และ `measure_ncmoe_matrix.py` เรียกสคริปต์นี้
**อัตโนมัติตอนเริ่ม** และ abort ถ้า verdict เป็น FAIL

## Checklist 6 ข้อ (สิ่งที่สคริปต์ตรวจ)

| # | ตรวจ | ผ่านเมื่อ | ล้มเหลวแปลว่า |
|---|------|---------|--------------|
| 1 | python `weight_stream.server` | มีแค่ตัวที่ตั้งใจ (อยู่บน port API) | มี instance บน port อื่น = เสี่ยง spawn ชน 8805 (กรณี 63152) |
| 2 | `llama-server.exe` | ไม่มีเลย | มี orphan/ตัวค้าง = วัดโดน config คนละตัว (กรณี EXP-008) |
| 3 | port 8765 / 8804 / 8805 | 8765 = server เรา · 8804/8805 ว่าง | port ชน = คำตอบมาจาก process ผิดตัว |
| 4 | VRAM baseline | บันทึกค่าไว้ (วัดเป็น delta) | >1.5 GB = มีอย่างอื่นกิน GPU อยู่ |
| 5 | API `/health` + โมเดลที่โหลด | ตอบ healthy + ไม่มีโมเดลค้าง | โหลดค้าง = วัดปนกับ session เดิม |
| 6 | llama-server binary + `WS_LLAMA_EXTRA_ARGS` | มี binary + env ตรงกับ config ที่ตั้งใจ | flag ผิด = วัด config ผิดทั้งชุด |

## ก่อนวัดทุกครั้ง (สรุปย่อ)

1. รัน `python scripts/check_clean_environment.py` → ต้องได้ **CLEAN** (หรือ WARN ที่ยอมรับได้ + บันทึกเหตุผล)
2. **kill llama-server orphan ถ้ามี:** `taskkill /F /IM llama-server.exe` — ต้องทำก่อน restart server ทุกครั้ง เพราะ Windows **ไม่ kill ลูกตามพ่อ** (EXP-009 ใส่ Job Object กันไว้แล้วสำหรับ server ใหม่ แต่ server เก่าที่ยังรันอยู่ยังไม่มีการ์ดนี้)
3. ยืนยัน **flag จริงบน cmdline ของ subprocess** (ไม่ใช่แค่ env var) — บทเรียน EXP-008 ที่ 3 config ให้เลขเดียวกันเพราะโดน orphan ตอบแทน
4. หลัง load → ตรวจ `/props` ว่า `model_path` ตรงกับโมเดลที่ตั้งใจ (harness มี `verify_backend()` อยู่แล้ว)
5. บันทึก VRAM baseline → คำนวณ delta หลัง generate (KV cache + compute buffer อยู่หลัง gen จริง)

## เมื่อไหร่ต้อง re-run

- ก่อน **ทุก** measurement session (ไม่ว่าจะ EXP ใหม่หรือ re-measure)
- หลัง restart / kill อะไรก็ตามที่เกี่ยวกับ server หรือ llama-server
- เมื่อเห็นตัวเลขแปลก ๆ (เช่น tok/s เดิม ๆ หลาย config) — รันเช็คก่อนฟันธงผล

## หมายเหตุ: `measure_ncmoe_matrix.py` ต้องการเริ่มจาก clean

Matrix ฆ่า orphan เอง **ระหว่าง config** (`kill_llama_servers()` ทุก restart)
แต่ gate จะรันแค่ครั้งเดียวตอนเริ่ม — ดังนั้นถ้าตอนเริ่มมี llama-server ค้างอยู่
(เช่นกำลังแชทกับโมเดลที่โหลดไว้) gate จะ FAIL และ matrix จะ abort
นั่นคือพฤติกรรมที่ตั้งใจ: ถ้าอยากให้ matrix วิ่ง ต้องปลดโมเดล/kill orphan
ก่อน (หรือรัน `check_clean_environment.py` ให้เห็นว่าอะไรค้าง แล้วจัดการ)


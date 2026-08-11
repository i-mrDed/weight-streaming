# Hermeticity Audit — 2026-08-11

> สแกนทั้ง repo หา test / โค้ดที่พึ่งไฟล์นอก repo (path แข็ง `~/…`, `C:/Users/…`, `D:/models/…`,
> ไฟล์โมเดลจริง) และทำรายการสิ่งที่ต้องแก้ให้ hermetic (self-contained, รันได้บนเครื่องใหม่/CI
> โดยไม่พึ่งไฟล์เครื่อง dev)
>
> **วิธีสแกน:** `git grep` กับ committed tree (HEAD) + รัน suite จริงแบบ hermetic
> (`HOME=C:/nohome USERPROFILE=C:/nohome python -m pytest -q`) ตามที่ CI guard ทำ
>
> **ผลการรันจริง (เครื่อง dev, 2026-08-11):** `1 failed, 386 passed, 0 skipped`
> → เทสต์ทุกตัวรวมถึงกลุ่มที่พึ่งโมเดลจริง **รันจริงบนเครื่องนี้** เพราะ path เป็น
> repo-relative/absolute ที่เครื่อง dev มีอยู่ — empty-HOME guard จับได้เฉพาะ leak แบบ `~/…`
> เท่านั้น สิ่งที่ hermetic จริงๆ คือ fresh checkout อย่างเดียว
>
> **งานต่อจากรายงานนี้:** อยู่ใน `TASKS.md` (section `Hermeticity Fixes`)

---

## 🔴 ต้องแก้ — ระดับ 1 (ทำ suite ไม่ deterministic / พึ่งไฟล์นอก repo จริง)

### 1. `tests/test_server.py` — พฤติกรรมขึ้นกับสถานะเครื่อง ✅ แก้แล้ว (2026-08-11)

- ~~Gate การรันคือ "skip ถ้าไม่มี server บน `127.0.0.1:8765`"~~ → เปลี่ยนเป็น **opt-in**
  `WS_E2E=1` — `pytest` รันปกติจะ skip เสมอ ไม่รันต่อ listener แปลกหน้าอีกต่อไป
- เพิ่ม `WS_TEST_SERVER_URL` / `WS_TEST_MODEL` ให้ชี้ target เองได้; แก้บั๊กเดิมที่
  standalone runner เปิด server บนพอร์ต 8383 แต่เทสต์ยิง 8765 (ตอนนี้ใช้พอร์ตเดียวกับ
  SERVER_URL)
- วิธีรัน: `WS_E2E=1 python -m pytest tests/test_server.py` หรือ `python tests/test_server.py`

### 2. `tests/test_split_parser.py:15` — hardcoded path เครื่อง dev ✅ แก้แล้ว (2026-08-11)

- ~~`DEFAULT_DIR = Path(r"C:\Users\<user>\models\UD-IQ3_XXS")`~~ → default เป็น
  `~/models/UD-IQ3_XXS` + `os.path.expanduser()` ตอนอ่านค่า — ไม่รั่ว username, ขยายเป็น home
  ของเครื่องตัวเอง; empty-HOME → skip (ยืนยันแล้ว: 9 ตัว skip)

### 3. `tests/test_gguf.py:8` + `tests/test_split_parser.py` — เทสต์ที่พึ่งไฟล์โมเดลจริง ✅ แก้แล้ว (2026-08-11)

- ~~ทั้งคู่ชี้ไปที่โมเดลจริง (gitignored, มีแค่เครื่อง dev)~~ → `tests/fixtures/synthetic_gguf.py`
  สร้าง GGUF สังเคราะห์จิ๋วตอน test: `build_qwen2moe()` (10 tensors, 6 expert tensors
  Q4_K, mirror Qwen1.5-MoE) + `build_dsv4_shards()` (4 shards จิ๋ว mirror DS V4 Flash) —
  ใช้ `gguf`/`numpy` ซึ่งเป็น runtime dep อยู่แล้ว ไม่ต้องเพิ่ม dependency, ไม่ต้องใช้โมเดลจริง
- parser test ทั้ง 20 ตัว (test_gguf 10 + test_split_parser 10) รันจริงใน CI แล้ว —
  suite hermetic สุดท้าย: **382 passed, 7 skipped, 0 failed** (skip = test_server opt-in เท่านั้น)
- หมายเหตุ: `GGUFWriter` เก็บ dims reversed + byte-shape → ส่ง data shape `(n_experts, cols_bytes, rows)`
  เพื่อให้ reader คืน `(rows, cols_bytes, n_experts)` — อธิบายไว้ใน docstring ของ builder

---

## 🟡 ต้องแก้ — ระดับ 2 (scripts ที่ commit มากับ path เครื่อง dev)

### 4. Smoke scripts — hardcode path + โมเดลจริง ✅ แก้แล้ว (2026-08-11)

- `scripts/test_llama_server.py` / `test_tools.py` → `WS_TEST_MODEL` (default `~/models/...`)
- `scripts/test_tools.py` / `test_mcp.py` / `test_assistants.py` → `WS_DATA_DIR`
  fallback เป็น `tempfile.gettempdir()` (ไม่ hardcode path dev)

### 5. `scripts/measure_*.py` — default ของ `WS_TEST_MODEL` เป็น path เครื่อง dev ✅ แก้แล้ว (2026-08-11)

- 6 scripts (`measure_ctx_scaling`, `measure_threads_scaling`, `measure_expert_census`,
  `measure_ncmoe_matrix`, `measure_dsv4flash`, `measure_mtp_specdecode`) — default
  `D:/models/...` / `<HOME>/...` → `~/models/...` + `os.path.expanduser()` ตอนอ่านค่า
  (convention เดียวกับ `tiering.py`; `~/` ขยายเป็น home ของเครื่องที่รัน)

---

## 🟢 ระดับ 3 — เลือกทำ (historical artifacts, ไม่กระทบ CI)

- **`research/experiments/EXP-0*/bench.json | gate.json | *.md`** (~85 ไฟล์) — บันทึก benchmark
  ที่ฝัง `C:\Users\<user>\...`, `D:\models\...` — เป็นหลักฐานการวัดของเครื่องอ้างอิง เก็บไว้ได้
  แต่รั่ว username → พิจารณาเปลี่ยนเป็น `~/models/...` (มี checklist อยู่แล้วใน
  `docs/GO_PUBLIC_CHECKLIST.md:32`)
- **`docs/MODEL_INVENTORY.md`, `ISSUES.md`** — เอกสารอ้าง `D:\models\...`, `C:\Users\<user>\...`
- **`Qwen3.6-35B-A3B-UD-IQ2_M.gguf.part` (7.9 GB ใน repo root)** — gitignored (`*.gguf.part`)
  จะไม่ถูก push แต่ควรลบออกจาก working tree

---

## ✅ เรียบร้อยแล้ว (ไม่ต้องแก้)

- **`weight_stream/server/tiering.py`** — default เก็บ literal `~/models/...` ขยายแบบ lazy
  (`_expand()` ตอน load/save) + fixture `fake_default_models` ใน `tests/test_p4_tiering.py`
  (fix จาก lesson 2026-08-11 → `research/2026-08-11-lesson-ci-hermetic-tests.md`)
- **`weight_stream/server/config.py`** — `get_model_search_dirs()` เป็น runtime, env-driven
  (`WS_MODELS_DIR`), ไม่มี import-time expansion
- **`tests/test_p4_hub.py`** — offline ล้วน (HTTP inject/monkeypatch)
- **`tests/test_llama_server_stats.py`** — offline ล้วน (mock subprocess); path `OUR`/`STALE`
  เป็น string สำหรับเทสต์ path-matching เท่านั้น ไม่ได้อ่านไฟล์
- **`tests/test_server_config_and_chat.py`, `test_p4_tiering.py`, `test_p4_security_hardening.py`** — fake engine + tmp_path
- **CI guard job** (empty HOME/USERPROFILE) — อยู่ใน `.github/workflows/ci.yml`
- **Gitignored แล้ว:** `.agents/mcp_config.json` (`C:\Users\<user>\...`), `.mcp.json`, `.p2.json`,
  `.proof2.json`, `opencode.jsonc`, `research/models/*.gguf`, `*.gguf.part`, `data/*.log`,
  `data/tiering.json`, `data/usage_history.jsonl`, `data/mcp/`

# 🛠️ P4 BRIEF — Weight Streaming Console: backend endpoints ใหม่ (§10) + pytest

> **สถานะ**: ปล่อยงานโดย PM แล้ว (2026-07-31) · P1+P2+P3 (รวมรอบ polish) เสร็จ + QA PASS + ผู้ใช้ตรวจรับแล้ว · run ต้นทาง `run-1785386652753-35chx9`
> **Source of truth**: `docs/DASHBOARD_THEME_SPEC.md` — โดยเฉพาะ **§10** (backend endpoints ใหม่), §9.1/9.4/9.6/9.8 (หน้าที่พึ่ง endpoint เหล่านี้ = **สร้างใน P5**), §12 (ความเสี่ยง/branch), §13 (workflow/เกณฑ์จบ) · ไฟล์นี้ = brief ย่อยสำหรับ Dev/QA (ถ้าขัดแย้งกัน spec ชนะ)
> **Branch / worktree**: `feature/dashboard-theme` ที่ `D:\.opencode\.worktrees\dashboard-theme\.Weight-Streaming` (HEAD `bf512fd`)

---

## 🎯 เป้าหมาย + ขอบเขตเฟส

**P4 = backend ล้วน + pytest** — เพิ่ม endpoint ใหม่ 9 ตัวแบบ **additive** (ไม่แก้ route เดิม, ไม่กระทบ main flow) ตาม §10 · **ห้ามแตะ frontend ในเฟสนี้** (ทุกหน้าที่ใช้ endpoint เหล่านี้ — Hub, Overview Activity, Settings server-config/log-tail — = **P5**) เพื่อแยก P4 ให้ตรวจด้วย API contract tests + pytest ได้โดยไม่พึ่งเบราว์เซอร์

| กลุ่ม | Endpoint | วัตถุประสงค์ | ความเสี่ยง |
|-------|----------|-------------|-----------|
| **Config** | `GET /v1/config` | ค่า effective + **source (env/default)** ต่อ key + models dirs + issues dir | ต่ำ (read-only) |
| | `PATCH /v1/config` *(v1.1)* | แก้ **safe subset** runtime; ที่เหลือ `409 + snippet` | กลาง (runtime mutation) |
| **Usage** | `GET /v1/usage/history` | ประวัติ generation (ring buffer JSONL 500: ts/model/tokens/tok_s/paging สรุป) `?limit=&since=` | กลาง (storage ใหม่) |
| **Logs** | `GET /v1/logs/tail?lines=` | server log tail (ต้อง**เดินสาย logging ใหม่**) | กลาง (แตะ startup) |
| **Hub** | `GET /v1/hub/search` | proxy HF search กรอง **GGUF เท่านั้น** + parse quant/size จาก filenames (timeout + cache 5 นาที) | กลาง (network) |
| | `POST /v1/hub/download` | เริ่ม download task `{repo_id, filename, target_dir?}` — HTTP Range, **atomic (tmp→rename), size guard** | **สูง (เขียนไฟล์จาก internet)** |
| | `GET /v1/hub/downloads` | รายการ tasks + status/progress | ต่ำ |
| | `GET /v1/hub/progress/{id}` | **SSE** ความคืบหน้า (bytes/%/speed/eta/status) | กลาง |
| | `POST /v1/hub/download/{id}/cancel` | ยกเลิก task | ต่ำ |

**ลำดับที่แนะนำ (ตามความเสี่ยง/dependency)**: Config(GET) → Usage → Logs → Hub(search→download→progress→downloads→cancel) → Config(PATCH v1.1 = should-have, ตัดได้ถ้าเสี่ยง/ไม่ทันโดยไม่ fail แกน P4)

---

## 🔒 กฎเหล็ก (ห้ามละเมิด)

1. **Additive เท่านั้น** — ไม่แก้ signature/behavior route เดิม (`/v1/generate`, `/v1/chat/completions`, `/v1/messages`, `/v1/stats`, `/v1/models*`, `/v1/issues*`, WS `/v1/stream`) · regression suite เดิมต้องเขียวยกชุด
2. **Honest telemetry (ADR-003)** — speed/ETA/progress ของ download = **ค่าจริง** (คำนวณจาก bytes/time จริง) ห้ามคงที่/สุ่ม; history = สิ่งที่ generate จริง; config source = ตรวจจาก env จริง; HF unreachable → error ตรงๆ ห้าม fake รายการ
3. **🔐 Security ของ Hub download (สำคัญสุด — §12)**: server **ไม่มี auth + CORS `*`** และ endpoint นี้**เขียนไฟล์จาก internet สู่เครื่อง** ดังนั้น:
   - `target_dir` ต้อง **resolve (`os.path.realpath`) อยู่ภายใน models dirs ที่อนุญาตเท่านั้น** (ใช้ helper `get_model_search_dirs()` เดียวกับ scan) — ปฏิเสธ path traversal (`../`, absolute นอกขอบเขต, symlink escape) ด้วย `400/403`
   - **atomic**: เขียน `<name>.part` (หรือ tmp ใน dir เดียวกัน) แล้ว `os.replace` → ไฟล์ปลายทาง
   - **size guard**: เทียบ `Content-Length` กับเพดาน/พื้นที่; filename ปลายทางต้องลงท้าย `.gguf` + sanitize (ห้าม `..`/`/`/`\` ในชื่อ)
   - auth = out-of-scope v1 (§14) — แต่ต้อง enforce target_dir ข้างต้น + บันทึกคำเตือนใน response/Docs (P5)
4. **Offline-first tests** — hub tests **ห้ามยิง HF จริง**: inject/monkeypatch HTTP layer (fake HF responses); download test เขียนลง **tmp models dir**; SSE progress test อ่านจาก stream จริงของ task จำลอง
5. **Dep footprint (§11 เจตนารมณ์ "pip install แล้วรันได้")** — ดู §dep ข้างล่าง; เพิ่ม dep runtime ต้อง flag PM/ผู้ใช้

---

## 📐 การออกแบบที่ตรวจแล้วจากโค้ดจริง (Dev ตั้งต้นจากนี้ได้เลย)

### A. `GET /v1/config` + source tracking
- อ่านจาก `ServerConfig` dataclass (`server/config.py:17`) — fields: `host, port, default_buffer_mb, default_n_ctx, default_n_threads, idle_unload_timeout, max_loaded_models, lower_process_priority, max_concurrent_requests, request_queue_depth, log_level`
- **source ต่อ key**: dataclass อ่าน env ตอนสร้างแต่**ไม่บันทึก source** → endpoint ตรวจ `os.getenv(WS_*)` เอง: มี → `"env"`, ไม่มี → `"default"` (ค่าที่ CLI ยัดผ่าน constructor จะโผล่เป็น effective value; แยก cli/default ไม่ได้นอกเสียจาก instrument เพิ่ม — **บันทึกเป็นข้อจำกัดซื่อๆ**, ไม่ต้องฝืนทำ cli tracking ถ้าไม่คุ้ม)
- **models dirs** ปัจจุบันฝังใน `_scan_gguf_models()` (`api_server.py:264-288`: env `WS_MODELS_DIR` → cwd, `cwd/research/models`, `cwd/models`, `~/models` → Windows เพิ่ม `%APPDATA%\Jan\data\llamacpp\models`) → **แยกเป็น helper `get_model_search_dirs()` (pure, ไม่ trigger scan)** ใช้ร่วมทั้ง `/v1/models/scan` + `/v1/config`
- **issues dir**: `WS_ISSUES_DIR` (default `data/issues`) จาก `issues/store.py:19` → รวมใน payload
- payload เสนอ: `{ "config": {<key>: {"value":…, "source":"env|default"}}, "models_dirs": […], "issues_dir": "…", "version": "0.13.0" }` (version จาก `weight_stream.__version__`)

### B. `PATCH /v1/config` *(v1.1 — safe subset)*
- `ModelManager` **ไม่มี setter** — แก้ field บน `self._cfg` ตรงๆ (`_cfg` เก็บตั้งแต่ `create_app`, `model_manager.py:65`)
- ✅ **safe (มีผลจริง, อนุญาต)**: `idle_unload_timeout` (อ่านสดทุกรอบ cleanup tick :611), `max_loaded_models` (อ่านตอน load :104 — มีผลกับ load ถัดไป)
- ⚠️ **gated (อนุญาต + เตือน)**: `default_buffer_mb / default_n_ctx / default_n_threads` — อ่านเฉพาะตอน load (:98-100) → **มีผลเฉพาะโมเดลที่โหลดภายหลัง** (ตอบพร้อม note นี้)
- 🚫 **`409 + snippet`**: `host/port/log_level` (restart-only), `lower_process_priority` (อ่านเฉพาะ first-load/last-unload :150,178 — ไม่สม่ำเสมอกลางรัน), `max_concurrent_requests/request_queue_depth` (**ไม่เคยถูก enforce** ใน manager :593 = no-op — บอกตรงๆ ว่ายังไม่มีผล + แนะตั้งค่าผ่าน env)
- response 409 เสนอ: `{ "detail": "…", "restart_required": true, "snippet": "WS_IDLE_TIMEOUT=…" }` (snippet generator ฝั่ง server — ตรงกับที่ Settings P3 สร้างฝั่ง client อยู่แล้ว)

### C. `GET /v1/usage/history` — hook ที่ ModelManager
- ทุก generation ผ่าน 4 method ของ `ModelManager` = คอขวดเดียว (ครอบคลุม native `/v1/generate`, OpenAI/Anthropic compat, WS): `generate()` (:273-320), `generate_stream()` (:322-381 — เรียก `get_stats()` :372), `chat_completion()` (:438-490), `chat_completion_stream()` (:492-545)
- ⚠️ **ช่องโหว่**: done-event ของ `chat_completion_stream()` (:539-543) มีแค่ `token_count` นับเอง **ไม่เรียก `get_stats()`** → ต้องเติมเพื่อให้ history มี tok_s/paging ครบ
- แหล่งข้อมูลจริง: backend `_last_gen_stats` (`llama_cpp.py:347-352`: `token_count, elapsed, tokens_per_sec, prompt[:50], paging?`) → ผ่าน `get_stats()` key `generation` (:719-754)
- **สร้าง `UsageRecorder` ใหม่** (ยังไม่มี storage ใด — `_last_gen_stats` เป็น slot เดียวถูกทับทุก รอบ): ring buffer in-memory 500 + persist **JSONL** `data/usage_history.jsonl` (ต่อท้าย, ตัดที่ 500) · record: `{ts, model, tokens, tok_s, elapsed_s, paging?}` (paging สรุปสั้นๆ) · inject เข้า `ModelManager` (constructor หรือ setter) · `?limit=&since=` (since = epoch ms)
- honest: stream path ที่ไม่มี stats จริง (compat stream adapters `openai_compat.py:84/100`, `anthropic_compat.py:91/102`) → บันทึกเท่าที่มี (tokens นับเอง, tok_s = `null` ถ้าไม่มี) ห้ามเติมเลข

### D. `GET /v1/logs/tail?lines=` — เดินสาย logging ใหม่ (ของเดิม dead)
- ปัจจุบัน: `logging.basicConfig` อย่างเดียว 3 จุด (`server/__main__.py:73-76`, `cli/main.py:212,454`) — **console handler เท่านั้น, ไม่มี FileHandler, ไม่มี `data/server.log`**; `recent_errors` (`api_server.py:66`) เขียน nowhere อ่านที่ :548/:558 → ส่ง `[]` เสมอ = **dead**; `WS_LOG_LEVEL`→`ServerConfig.log_level` (`config.py:69`) แต่**ไม่มีใครอ่าน** = dead
- **ทำ**:
  1. **ring-buffer `logging.Handler`** ที่ append formatted record เข้า `recent_errors` (cap ~200) → **แก้ dead recent_errors** ให้ `/v1/debug/context` `log_tail` เป็นจริง (bonus honest-telemetry) + เป็นแหล่งของ `/v1/logs/tail?lines=` (อ่านจาก ring, default 100, cap 1000)
  2. **FileHandler → `data/server.log`** (สร้าง `data/` ถ้ายังไม่มี — ปัจจุบันมีแต่ `data/issues`) ให้ tail จากไฟล์ได้ + persist ข้าม restart
  3. **wire `WS_LOG_LEVEL` จริง** (apply `config.log_level` ตอน startup) — เคลียร์ dead env var อย่างซื่อ (หรือจะลบก็ได้ แต่ wire คุ้มกว่าเพราะแตะ logging อยู่แล้ว)
- ⚠️ **ความเสี่ยง**: server รันใต้ **uvicorn** — อย่า double-configure หรือไปปิด uvicorn logging; attach handler ที่ root/app logger อย่างระมัดระวัง + เทสต์ว่า log ยังออก console เหมือนเดิม

### E. Hub (`/v1/hub/*`) — raw HTTP ไป HuggingFace API (ไม่มี dep ใหม่)
- **ยืนยันแล้ว: ไม่มี `huggingface_hub`/HF ใดในโค้ด/dep** → มติ §10 ใช้ **raw HTTP** คง footprint ต่ำ
- **ADR ย่อย (บันทึกใน PR)**: ใช้ **stdlib `urllib.request` ผ่าน `asyncio.to_thread`** (search = JSON เล็ก; download = stream read เป็น background task, chunked, รายงาน progress) = **0 runtime dep ใหม่** · *fallback*: ถ้า urllib สำหรับ streaming+Range+cancel เจ็บเกินไป → `httpx` async (แต่จะ**เพิ่ม runtime dep → ต้อง flag PM/ผู้ใช้ก่อน**)
- `GET /v1/hub/search?q=&sort=downloads|likes|recent&limit=` → HF `https://huggingface.co/api/models?search=…&filter=gguf&sort=…` · **timeout ~10 วิ + cache in-memory 5 นาที** (key = q+sort+limit) · กรอง **GGUF เท่านั้น** · parse filenames → quant/size ต่อไฟล์ (ใช้ logic คล้าย `guessQuant` ฝั่ง frontend)
- `POST /v1/hub/download {repo_id, filename, target_dir?}` → spawn background task (asyncio task + registry) · HTTP Range (resume robust; v1 = retry ใหม่ตาม §9.6) · atomic + size guard + target_dir guard (§กฎเหล็ก 3)
- `GET /v1/hub/progress/{id}` → **SSE** (ใช้ `sse-starlette` ที่มีอยู่แล้ว — ดู pattern `StreamingResponse` เดิม `api_server.py:643`) · `{bytes, total, percent, speed_bps, eta_s, status}` คำนวณจริง · status: `queued|downloading|done|failed|cancelled`
- `GET /v1/hub/downloads` → รายการ tasks + สถานะล่าสุด · `POST /v1/hub/download/{id}/cancel` → set cancel flag + cleanup `.part`
- HF unreachable → `502/503 + detail` ตรงๆ (frontend P5 จะแสดง banner + ลิงก์ huggingface.co — §9.6)

---

## 📦 Dep (ซื่อๆ)
- **Runtime**: เพิ่ม **0 ตัว** (ใช้ stdlib `urllib` + `sse-starlette`/`fastapi` ที่มีแล้ว) — *เว้นแต่* Dev จำเป็นต้องใช้ `httpx` สำหรับ HF streaming → **flag ก่อน** (ถือเป็น dep ใหม่)
- **Test-only**: เพิ่ม **`httpx`** สำหรับ `fastapi.testclient.TestClient` (ปัจจุบันไม่มี TestClient/httpx ใน tests) → ใส่ใน optional-dependencies group ใหม่ `test = ["httpx", "pytest"]` (หรือ `[dependency-groups] dev`) · **ไม่กระทบ runtime install** · บันทึกใน PR

---

## 🧪 กลยุทธ์ tests (ตาม pattern เดิม + เพิ่ม HTTP contract)
- **คง baseline**: `98 passed / 6 skipped / 9 errors` (9 errors = fixture GGUF `test_gguf.py:11-14` ชี้ `research/models/Qwen1.5-MoE-A2.7B_Q2_k.gguf` ที่ไม่มีจริง → FileNotFoundError; **ห้ามแตะ test_gguf ใน P4** เพื่อรักษา baseline ให้เทียบง่าย — ถ้าจะแก้ให้ turn เป็น skip แยกตั๋วต่างหาก)
- **API contract tests ใหม่**: ใช้ `TestClient(create_app(config))` (ต้องมี httpx) — เทสต์ status codes (`200/400/404/409/502`), payload shape, SSE frame ของ progress
- **Manager-direct tests** (pattern เดิม `test_server_config_and_chat.py` — fake models ยัด `manager._models` ผ่าน helper): เทสต์ `UsageRecorder` บันทึกจริงหลัง `generate`/`chat_completion` (+ stream), PATCH safe-subset มีผล/409 ถูกตัว
- **Hub offline**: monkeypatch HF HTTP layer (fake search JSON / fake file stream) — **ห้าม network จริง**; download เขียนลง tmp dir; progress SSE อ่านจาก task จำลอง; cancel หยุด + ลบ `.part`
- **Security tests**: `target_dir` traversal (`../../../etc`, absolute นอก models dirs, symlink) → `400/403` + ไม่มีไฟล์ถูกเขียน; filename sanitize
- mypy default ต้องยัง clean (0 errors / 43+ files) — เพิ่ม type hints ครบในไฟล์ใหม่

---

## ✅ เกณฑ์จบ P4 (QA gates, §13 — "API contract tests · download progress จริง · history ring buffer · ไม่กระทบ endpoint เดิม")

1. **Config**: `GET /v1/config` คืนค่าจริงทุก key + source env/default ถูก (ตั้ง env แล้วตรวจ) + models_dirs ตรง `get_model_search_dirs()` + issues_dir + version 0.13.0 · `PATCH` safe subset (`idle_unload_timeout`,`max_loaded_models`) มีผลจริง; gated keys มี note; ที่เหลือ `409 + snippet`
2. **Usage**: generate จริง (fake model ใน test) → `/v1/usage/history` มี record (ts/model/tokens/tok_s) ครบ; ring ตัดที่ 500; persist JSONL; `?limit=&since=` ทำงาน; stream path ที่ไม่มี tok_s = `null` (ไม่แต่ง)
3. **Logs**: `/v1/logs/tail?lines=` คืน log จริง (เขียน log แล้วตรวจ); `recent_errors` ไม่ว่างอีกต่อไป → `/v1/debug/context` `log_tail` เป็นจริง; `data/server.log` ถูกสร้าง; `WS_LOG_LEVEL` มีผล; console log เดิมไม่หาย
4. **Hub**: search คืน GGUF-filtered results (จาก fake HF) + quant/size parse; cache 5 นาที + timeout; download → atomic `.part→rename` + progress SSE ค่าจริง (bytes/%/speed/eta) + cancel ได้; **target_dir guard ผ่าน adversarial tests**; HF unreachable → error ตรงๆ ไม่ fake
5. **Regression**: endpoint เดิมไม่เปลี่ยน (contract เดิมเขียว) · **pytest baseline เขียว (98/6/9) + tests ใหม่ passed เพิ่ม** · `/app` 0 diff vs main (P4 ไม่แตะ frontend/static) · reproducible build frontend ยังเดิม (ไม่ได้ build ใหม่) · mypy clean
6. **Honest-telemetry audit**: ไม่มี speed/ETA/progress/history/config-source ปลอม; capability/restart-required บอกตรงๆ

---

## 📌 พกต่อ / ข้อเสนอ (ไม่ใช่แกน P4 — ต้องถามผู้ใช้ก่อนทำ)

1. **`dashboard_server.py` = fake metrics จริง** (`METRICS_CACHE` hardcoded hit_rate 0.85/4200MB/s, `update_metrics()` ไม่มีใครเรียก) **ขัด honest telemetry โดยตรง** — แต่ยังเป็น **CLI subcommand `dashboard`** (`cli/main.py:94-96,172-173,503-506` + `cli/__init__.py:21,55-57`) → **การลบ = เอา CLI command ออก (behavior change) → PM ต้องถามผู้ใช้ก่อน** (ตัวเลือก: ลบ / ทำให้ดึงค่าจริง / ปล่อยไว้). **ค่าเริ่มต้น P4 = ไม่แตะ**
2. (carry-over เดิม) `/health`+`FastAPI(version=)` ยัง `0.11.0` vs `__version__` 0.13.0 — P4 แตะ `api_server.py` อยู่แล้ว ถ้าแก้ด้วย `from weight_stream import __version__` (เหมือน `/api` :123) = ปลอดภัย + ซื่อขึ้น (**optional, ทำได้เลยถ้าไม่เสี่ยง** — ไม่ใช่ gate)
3. (carry-over เดิม) registry §4.2 · EN faults/tok · scan timeout/cancel · mobile btn<44px · bundle ~112.5kB → P5

---

## ▶️ สร้าง/รัน/ตรวจ
```bash
cd <worktree>/.Weight-Streaming
pip install -e ".[server,test]"        # เพิ่ม test extra (httpx) — ครั้งเดียว
PYTHONPATH=. python -m weight_stream.server --port 8799   # ทดสอบ (main 8765 ห้ามแตะ)
pytest tests/ -q                        # baseline 98/6/9 + tests ใหม่
# ตรวจ endpoint (ตัวอย่าง):
curl http://127.0.0.1:8799/v1/config
curl "http://127.0.0.1:8799/v1/hub/search?q=qwen&limit=5"
curl -N http://127.0.0.1:8799/v1/hub/progress/<task_id>
```
- **main ของผู้ใช้รันที่ 8765 — ห้ามแตะ** (คนละ branch/งาน) · ทดสอบที่ **8799**
- frontend **ไม่ต้อง build ใหม่** ใน P4 (ไม่แตะ frontend) → `/console` เดิมจาก `bf512fd` ยังใช้ได้; `/app` ต้อง 0 diff

## ลำดับ
`Dev สร้าง (เรียงตามความเสี่ยง §ขอบเขต) → self-verify ตาม gates + pytest → commit (conventional) → QA ตรวจอิสระ (contract tests + security adversarial + offline hub) → PM ตรวจ spec + รายงานผู้ใช้` วนจน gate ผ่าน แล้วค่อย **P5** (หน้า Hub + เดินสาย Settings/Overview ใช้ endpoint P4 + polish + full TH sweep)

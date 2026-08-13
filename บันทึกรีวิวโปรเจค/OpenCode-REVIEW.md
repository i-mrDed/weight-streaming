# 📋 Review Report — weight-streaming

> **Repo:** https://github.com/i-mrDed/weight-streaming
> **เวอร์ชันที่รีวิว:** v0.14.0 (HEAD ของ main, git clone 2026-08-10)
> **วันที่รีวิว:** 10 สิงหาคม 2026 (Mon Aug 10 2026)
> **วิธีรีวิว:** clone อ่านโค้ดจริง (ไม่ติดตั้ง dependencies/รัน) + Spawn 5 agents หลายสายงาน parallel (สถาปัตยกรรม, code review, security, frontend, planner) + ตรวจสอบยืนยัน findings สำคัญด้วยตัวเอง + ทดสอบ path traversal จริงบน FastAPI/Starlette
> **Status:** ✅ เสร็จสมบูรณ์ (ทุกมิติ) — ⚠️ ไม่ได้รันเทส/browser จริง (เป็น static + code-path review)

---

## 🎯 ภาพรวมโปรเจค

**weight-streaming** คือแพลตฟอร์ม local inference สำหรับรัน LLM ขนาดใหญ่ (100B–3T+ parameters, โดยเฉพาะ MoE) บนเครื่อง consumer (RAM 32–64 GB) โดยใช้ **NVMe เป็น extension ของ RAM** — ผ่าน memory-mapping + OS page cache + telemetry ที่ซื่อตรง (faults/token, disk MB/token) แทนการ "อ้างว่า" รันได้แบบไม่ต้องแลกอะไร

**ผลวัดจริง (EXP-012):** DeepSeek-V4-Flash 104 GB รันได้จริงบน i9-9900KF + RTX 3060 12 GB + 64 GB RAM ที่ **1.48–1.89 tok/s** (disk-bound) — พิสูจน์ด้วย fault telemetry 36–77k faults/token ≈ 150–300 MB อ่านจากดิสก์ต่อ token

**องค์ประกอบ:** API server (OpenAI/Anthropic-compatible + SSE), Web console (React SPA), dual backend (llama-cpp-python CPU + llama-server GPU subprocess), Hub ดาวน์โหลด GGUF จาก Hugging Face, MCP host, Assistants, Issue system, CLI/TUI/Gradio, ~290 tests, CI green.

---

## ✅ จุดเด่น (Strengths)

### 1. ค่านิยม "Honest Telemetry" ฝังในโค้ดจริง ไม่ใช่สโลแกน
- ทุกตัวเลขบน stats page มาจากการวัดจริง หรือแสดง `n/a` — **ห้ามเลขปลอม** (เช่น `paging: None`, `disk_demand_source` ระบุที่มา, GPU properties คืน None ซื่อตรง)
- เคยลบ `dashboard_server.py` ทิ้งเพราะเสิร์ฟค่าปลอม (CHANGELOG 0.14.0) — พิสูจน์ความจริงใจระดับโค้ด
- Stats ระบุ source ชัดเจน: `major_faults` (ของการ OS) vs `residency_growth_estimate` (ประมาณการ) — ไม่ปนกัน

### 2. Empirical discipline เข้มงวดมาก (หายาก)
- design ถูกพลิกกลับหลายครั้งตามข้อมูลจริง: "predictive streaming" → "mmap + วัดผลตามจริง" (ADR-003)
- Clean-room gate (`check_clean_environment.py`) — กันผลวัดปนเปื้อน (เคยจับได้ว่า EXP-005/006 วัดบน stale server)
- ปิด dead end อย่างตรงไปตรงมา 4 เส้นทาง: EXP-010 (spec-decode), EXP-015 (MTP), EXP-016 (expert census), EXP-017 (CPU lane) — รู้จัก "พอ" ไม่เสียเวลาต่อ

### 3. วิศวกรรม platform คุณภาพสูง
- **`_iter_blocking`** worker-thread bridge: cancellation สะอาด, backpressure, sentinel, re-raise error, `finally: stop.set()` — ออกแบบดีจริง (วัด health ≤ 28 ms ระหว่าง generation)
- Subprocess lifecycle ครบ: Windows Job Object กัน orphan, port-collision guard + stale-owner sweep, readiness 300s สำหรับ >RAM model
- CPU etiquette: inference child วิ่ง below-normal priority → desktop/browser/IDE ยังใช้ได้ตอน model 100GB ทำงาน (วัด: CPU 56.2%→22.6%)
- Dual backend abstraction (ABC) + fallback chain ทำงานจริง

### 4. Hub download ปลอดภัยและแข็งแรงมาก
- Filename sanitize (reject `..`, absolute, NUL), realpath containment + symlink-TOCTOU ป้องกันด้วย `O_EXCL|O_NOFOLLOW`, atomic `.part`→`os.replace`, resume ตรวจ Content-Range offset, free-space gate, **GGUF structural gate** (byte-count parity + header/tensor-table parse) ก่อน rename — ระดับนี้หาได้ยากในโปรเจค open-source

### 5. ฟีเจอร์ product ครบวงจร
- API 3 ตระกูล (OpenAI/Anthropic/SSE), Hub ดาวน์โหลด sharded repos + resume, MCP host, Assistants, Issue tracking, i18n TH/EN (666 keys), theme registry, quant advisor, CLI 9 subcommands, TUI, Gradio

### 6. เอกสาร/research หนาแน่น
- CI green (~290 tests), docs/ARCHITECTURE.md + ADR + DECISIONS, research experiments 17 ฉบับ (EXP-001..017), HARDWARE_100TPS_PLAN กับราคาจริง 2026-08, CHANGELOG เล่า story การตัดสินใจครบ

---

## ❌ จุดด้อย (Weaknesses)

### 🔴 ระดับ High (ต้องแก้ก่อนปล่อย/public)

| # | ปัญหา | ตำแหน่ง | ผลกระทบ |
|---|---|---|---|
| W1 | **Deadlock ใน `load()` eviction** — `async with self._dict_lock` แล้วเรียก `unload()` ที่ครอบ lock เดิมซ้ำ (asyncio.Lock ไม่ reentrant) | `server/model_manager.py:143-178, 234` | โหลด model เกิน `max_loaded_models` → request ค้างถาวร + list/stats/unload ทั้งหมดค้าง (server ใช้ไม่ได้) ✅ verified |
| W2 | **CORS `allow_origins=["*"]` + `allow_credentials=True` + ไม่มี auth** | `server/api_server.py:226-233` | เว็บเพจใดก็ได้ส่ง credentialed request มาที่ localhost ได้: ลบไฟล์ model, load/unload, ตั้งค่า config, สั่ง MCP (→ RCE) ✅ verified |
| W3 | **MCP server รับ `command`/`args` อิสระ → arbitrary local command execution (RCE)** | `server/mcp_host.py:103-123` + `api_server.py:1233-1246` | `POST /v1/mcp/servers` {"command":"cmd.exe","args":[...]} → spawn กระบวนการจริง ไม่มี allowlist ✅ verified |
| W4 | **GGUF parse ล้มเหลว → mmap ไฟล์ >100GB + fd รั่ว** — exception path ไม่ปิด `_mmap`/`_file` (ต่างจาก Step 4 ที่ปิดครบ) | `backends/llama_cpp.py:148-153` | ทุกครั้งที่โหลด GGUF เสีย → mmap 104GB ค้าง + fd รั่ว จน resource exhaustion ✅ verified |
| W5 | **Path traversal บน Windows (confirmed)** — `assistant_id`/`issue_id` ต่อเข้า `os.path.join` ไม่ validate | `server/assistants.py:54-55`, `issues/store.py:49-53` | ทดสอบจริง: `%5C` (encoded backslash) ผ่าน → escape directory → อ่าน/เขียน/ลบไฟล์ .json นอก dir ได้ (Starlette block `%2F` แต่ **ไม่ block `%5C`**) ✅ tested |

### 🟠 ระดับ Medium

| # | ปัญหา | ตำแหน่ง | ผลกระทบ |
|---|---|---|---|
| W6 | `StreamingBuffer` ไม่มี lock แต่ถูกใช้จาก prefetch thread + main thread | `core/buffer.py` + `core/prefetcher.py` | race บน OrderedDict → corrupt LRU, stats ผิด |
| W7 | งาน sync หนักบน generation thread: `sample_resident_pages()` สร้าง array ~1.7MB / `_prefetch_layer_experts` อ่าน mmap เต็ม bite | `backends/llama_cpp.py:308-314`, `io/win_perf.py:113-165` | latency กระตุกเป็นวินาทีต่อ token (โดยเฉพาะไฟล์ 104GB) |
| W8 | `_OWNED_PIDS` TOCTOU + pid ไม่ cleanup | `backends/llama_server.py:432-442, 578-620` | server ใหม่ถูกฆ่าแบบ racing / stale server รอด |
| W9 | MCP SSE `url` → SSRF; hub repo_id ตาม redirect อิสระ → SSRF | `mcp_host.py:111-114`, `hub.py:1081-1083` | อ่าน cloud metadata / โจมตี internal service |
| W10 | `/v1/models/scan?dir=` path อิสระ; `/v1/models/load` ไม่ validate path + ไม่มี upper bound (`n_ctx`/`buffer_mb`) | `api_server.py:566-657, 659-688` | directory enumeration, file-read primitive, OOM/DoS |
| W11 | `global lock` ครอบตลอด load หลายนาที (ผูกกับ W2 ด้วย) | `model_manager.py:751-770` | server freeze ระหว่างโหลด model ใหญ่ |
| W12 | `WS_HUB_MAX_BYTES` default 0 (unlimited) + ไม่ cap concurrency | `hub.py:1078, 1052-1054` | disk exhaustion / DoS |
| W13 | **Identity crisis** — product จริง (llama-server wrapper + console) ต่างจาก positioning (speculative weight streaming); `total_accesses = 0` gap ยังไม่ปิด — thesis วิจัยยังพิสูจน์ไม่จบ | `pyproject.toml`, `ARCHITECTURE.md:80` | สับสน direction, research value ยังค้าง |

### 🟡 ระดับ Low (บันทึกเป็น known issues)
- Frontend: thinking-block markers ถูก corrupt (`" thinking"` แทน `<thinking`) → ข้อความที่มีคำว่า "thinking" ในโพรซีถูกกลืนเป็น block + XML tags ของ Qwen3/DeepSeek ไม่ถูก normalize (thinks.ts:24-33) — **กระทบกฎ "ไม่ render ต่างจากข้อมูลจริง"**
- Frontend: side effects ระหว่าง render (ChatPage.tsx:180-212), re-parse markdown ทุก frame 60fps (ChatPage.tsx:642-686), race `loadLatest` (HubPage.tsx:161-186), theme auto-mode ไม่ re-apply เมื่อ OS เปลี่ยน (theme/manager.ts:57-62)
- Backend: `prefetcher._queue` ไม่มีอยู่จริง → `queued: 0` ตลอด (telemetry ปลอมเงียบ), `_warm_predictor` ฉีด history ปลอม, `close()` early-return ซ่อน leak, cleanup task race, `send()` กลืน Exception กว้าง, fallback template กลบ error จริง
- Security: browse dialog spam, stale-sweep kill, Windows case-sensitivity, `_write` ไม่ atomic

---

## 🌍 ผลกระทบ (Impact)

### ต่อผู้ใช้ (User impact)
- **บวก:** ได้เครื่องมือ "ลองโมเดล 100B+ บนเครื่อง 64GB" ตัวเดียวที่เปิดเผยราคาจริง (1.5–1.9 tok/s) — ไม่มีสัญญาเกินจริง; ใช้เป็น honest meter ก่อนลงทุน hardware
- **เสี่ยง:** ถ้าเปิด server bind อื่น/มีเว็บเปิดอยู่ → drive-by RCE/MCP + file deletion (W2/W3/W5) — **ห้ามใช้แบบไม่แก้ security ก่อน**
- **เสี่ยง:** load เกิน max models → deadlock ต้อง restart (W1)

### ต่อนักพัฒนา (Dev impact)
- **บวก:** โค้ดอ่านง่าย, docs ครบ, ADR ชัด, tests เยอะ — onboard ง่าย
- **ลบ:** `api_server.py` ~1300 บรรทัด monolith; core buffer/predictor/prefetcher เป็น dead weight ใน GPU path — ต้องแยกให้ชัดว่าจะเป็น research หรือ product

### ต่อวงการ/community (Ecosystem impact)
- **บวก:** contribution จริงคือ "honest measurement methodology + platform" — เผยแพร่ตัวเลขที่ทุกคนโกหกกัน (พulsar benchmark 8–11 tok/s บน 2×16GB GPU ยืนยัน thesis)
- **โอกาส:** K3 2.8T บน consumer HW = novelty ที่ยังไม่มีใครทำสำเร็จ (ทุกคนอยู่ 0.07–4 tok/s ตาม EXP-014)

### ต่อเป้าหมายโปรเจค (Goal alignment)
- ✅ เป้าหมาย Phase 4 (2.5–4 tok/s software-only) align กับฟิสิกส์จริง (bytes/token ↓ → resident ↑)
- ⚠️ Thesis หลัก "predictive streaming ดีกว่า mmap" ยังไม่เคยถูกพิสูจน์ — ทุกวัดจนถึงตอนนี้คือ mmap + OS cache

---

## 📦 วิธีติดตั้ง (Installation)

> ⚠️ อ้างอิงจาก README ของ repo — ยังไม่ได้รันจริงในการรีวิวนี้ (ติดตั้งจริงแนะนำให้ทำใน venv)

```bash
# 1. ต้องการ Python >= 3.11
# 2. ติดตั้ง (server extras: fastapi/uvicorn; test: pytest/httpx/requests)
pip install -e ".[server,test]"

# 3. ตัวเลือก enhancement (ตามความต้องการ)
pip install -e ".[llama-cpp]"   # CPU backend (llama-cpp-python)
pip install -e ".[gradio]"      # Gradio UI
pip install -e ".[tui]"         # Textual TUI
pip install -e ".[mcp]"         # MCP host (P7.4)
```

**ข้อควรรู้ก่อนติดตั้ง:**
- GPU backend ใช้ binary `llama-server` — โค้ดค้นหาในโฟลเดอร์ Jan Desktop (`%APPDATA%\Jan\...`) ก่อน; ผู้ใช้ที่ไม่มี Jan จะ fallback ไป CPU binding (ช้ามากกับ model 100GB) — ดู roadmap ข้อ D6/D9
- ไฟล์ model 104GB ดาวน์โหลดผ่าน hub ในตัว (resume ได้ ปลอดภัย) — ตรวจสอบพื้นที่ดิสก์ก่อน

---

## 🚀 วิธีใช้งาน (Usage)

```bash
# 1. เริ่ม API server + web console (default port 8765)
weight-streaming server            # หรือ python -m weight_stream.server --port 8765
# เปิด http://localhost:8765/console/

# 2. CLI ตรง
weight-streaming run model.gguf -p "Hello"
weight-streaming benchmark model.gguf --max-tokens 256

# 3. UI อื่น
weight-streaming tui --server http://127.0.0.1:8765   # Textual TUI
weight-streaming ui                                    # Gradio web UI

# 4. ต่อ API แบบ OpenAI-compatible (ใช้กับ IDE/agents)
#    POST http://localhost:8765/v1/chat/completions
```

**Env vars สำคัญ (WS_*):** `WS_PORT/WS_HOST`, `WS_MODELS_DIR`, `WS_N_THREADS` (default ครึ่งหนึ่งของ cores), `WS_N_CTX`, `WS_GPU_LAYERS` (`-1` auto / `0` CPU / `N`), `WS_KV_CACHE_TYPE` (เช่น `q8_0`), `WS_BUFFER_MB` (64), `WS_IDLE_TIMEOUT`, `WS_LOWER_PRIORITY` (1), `WS_LLAMA_EXTRA_ARGS` (เช่น `--cpu-moe`, `--n-cpu-moe 42`)

**ตัวอย่างใช้กับ 104GB model:** `WS_LLAMA_EXTRA_ARGS="--cpu-moe -t 8" weight-streaming server` → ได้ ~1.48–1.89 tok/s (EXP-012)

---

## 💎 การนำไปใช้ให้เกิดประโยชน์สูงสุด (Maximization)

### ใครได้ประโยชน์มากที่สุด
1. **ผู้มี RAM 32–64GB + GPU 12GB** อยากลองโมเดล 100B+ (DS V4 Flash 104GB) — งานไม่เร่ง: draft เอกสาร, batch summarize, โครงเรื่อง
2. **นักวิจัย/นักศึกษา MoE inference** — simulator + telemetry เป็นเครื่องมือเรียนคอขวด (bandwidth wall) โดยไม่ต้องมี hardware ใหญ่
3. **ผู้ใช้ IDE/agent ท้องถิ่น** — OpenAI/Anthropic-compat endpoints ต่อ Claude Code/Cursor/Continue กับโมเดลใหญ่แบบ offline
4. **Community ผู้มี 3090/4090/128GB RAM** — เป็น benchmark leaderboard (เลข DS V4 Flash บนเครื่องแรง = หลักฐาน "ใช้งานได้จริง")

### วิธีใช้ให้ได้คุณค่าสูงสุด
- **ใช้วินัยเดียวกับ EXP:** `benchmark` + `auto-tune` + clean-room → รายงานชุด metric เดียวกัน (tok/s, faults/tok, disk MB/tok, resident %) เปรียบเทียบข้ามเครื่องได้
- **RAM 32GB:** เลือก quant เล็ก (IQ2_XXS/IQ1_M) — bytes/token เป็นตัวตั้งราคาความเร็ว
- **ใช้ SPA stats เป็น honest meter** — เห็นคอขวด disk/CPU/GPU ก่อนซื้อ hardware
- **ใช้ hub integrity gate** เป็น safe path ดาวน์โหลด 104GB (resume + structural gate)
- **ก่อนเปิดใช้สาธารณะ:** แก้ security findings (W2/W3/W5) ก่อน — ดู "แนวทางพัฒนาต่อ"

---

## 📊 การประเมินคะแนนในมิติต่างๆ (Scorecard)

| มิติ | คะแนน /10 | ระดับ | เหตุผลหลัก |
|---|---|---:|---:|---|
| **แนวคิด & นวัตกรรม** | **8.5** | 🟢 สูงมาก | เป้าหมายกล้า (100B–3T+ บน consumer HW), thesis ชัด, honest measurement = contribution จริง; หักที่ thesis ยังพิสูจน์ไม่จบ |
| **สถาปัตยกรรม** | **7.0** | 🟡 ดี | Dual backend + abstraction ฉลาด; แต่ api_server monolith, identity crisis, core module dead weight |
| **วิศวกรรมซอฟต์แวร์** | **7.5** | 🟡 ดี | worker bridge/cancellation/process mgmt ดีมาก; แต่ deadlock (W1), leak (W4), concurrency gaps |
| **ความปลอดภัย** | **4.5** | 🔴 ต่ำ | RCE ผ่าน MCP (W3), CORS*+no-auth drive-by (W2), path traversal Windows (W5) — ต้องแก้ก่อน public; hub ตัวเองแข็งแรงมาก |
| **UI/UX & Frontend** | **7.5** | 🟡 ดี | polish สูง, honest display, i18n/theme ดี; แต่ marker bug thinks.ts + perf markdown re-parse |
| **Performance (ผลลัพธ์จริง)** | **5.5** | 🟡 กลาง | ประเมินตามเป้าหมาย: 104GB @ 1.48–1.89 tok/s = พิสูจน์แนวคิดได้ ยังไกลจาก "ใช้ทำงานจริง"; ใกล้เคียงเป้าหมาย Phase 4 (2.5–4) ยังต้องทำ |
| **Testing & CI** | **7.5** | 🟡 ดี | ~290 tests, CI green (Windows + frontend); หักที่ Python CI ครอบแค่ Windows, ขาด test ครอบ deadlock/leak/concurrency |
| **Documentation** | **8.5** | 🟢 สูงมาก | README/ARCHITECTURE/ADR/ROADMAP/CHANGELOG/research 17 EXP — ครบและเล่า story ชัด |
| **Research Rigor** | **8.5** | 🟢 สูงมาก | clean-room, cold/warm, dead-end ปิดตรงไปตรงมา, ตัวเลขอ้างอิงได้ |
| **ความพร้อมผลิตภัณฑ์ (Release-ready)** | **5.0** | 🟡 กลาง | ฟีเจอร์ครบ แต่ PyPI ยังไม่ release, dependency บน Jan binary, security ก่อน public |
| **ความสามารถ scale/maintain** | **6.0** | 🟡 กลาง | โครงสร้างชัด + docs ดี; แต่ monolith, mypy --strict baseline 225, Linux ไม่มีหลักฐาน |
| **โอกาสทางวิจัย/community** | **7.0** | 🟡 ดี | K3 = novelty สูง, honest benchmark = ทรัพย์สาธารณะ; ต้อง native core + paper ถึงจะเก็บเกี่ยว |

### 🏆 คะแนนรวม (Weighted)
| หมวด | น้ำหนัก | คะแนน | รวม |
|---|---:|---:|---:|
| วิศวกรรม (code/arch/security) | 30% | 6.3 | 1.89 |
| วิจัย/นวัตกรรม (thesis/rigor) | 25% | 8.5 | 2.13 |
| Product (UX/features/ready) | 25% | 5.8 | 1.45 |
| Community/docs/scale | 20% | 7.5 | 1.50 |
| **คะแนนรวม** | 100% | | **6.97 / 10** |

> **สรุปภาพรวม: โปรเจคระดับ "น่าจับตามองมาก" (Solid Beta / Research-Grade v0.14)** — จุดแข็งคือวินัยการวัดจริง + วิศวกรรม platform ที่คิดลึก; จุดที่ดึงคะแนนลงคือความปลอดภัย (ต้องแก้ก่อน public) และ identity crisis ระหว่าง research thesis กับ product จริง

---

## 🗺️ แนวทางพัฒนาต่อ (Development Path) เพื่อบรรลุเป้าหมาย

### Priority สูงสุด — ความปลอดภัย (ทำทันที, ก่อนปล่อย/ก่อนเปิด bind อื่น)
1. **CORS/Origin hardening** — allowlist `localhost:*`, ปิด `allow_credentials`, ตรวจ Host header กัน DNS rebinding (W2)
2. **MCP command allowlist** — รับ command/args เฉพาะจากไฟล์ config ที่ user ตั้งเอง ไม่ใช่ API; ห้ามเปลี่ยนหลัง setup (W3)
3. **Path validation** — regex `^[A-Za-z0-9_-]+$` สำหรับ assistant_id/issue_id + ปิด `%5C` traversal (W5)
4. **Fix deadlock** `load()` eviction (W1) + **fix mmap/fd leak** exception path (W4)
5. Upper bounds: `n_ctx` ≤ 262144, `buffer_mb` จำกัด, cap hub concurrency + default `WS_HUB_MAX_BYTES` (W10/W12)

### Priority รอง — เป้าหมาย performance (2.5–4 tok/s software-only)
6. **EXP-018: IQ2_XXS** บน DS V4 Flash (lever สุดท้ายที่เหลือ — ลด bytes/token) — สคริปต์มี `--variant iq2m` แล้ว
7. **Calibrate simulator** ด้วย physics model (BW ÷ bytes/token) → ใช้พยากรณ์ K3 ได้
8. **ปิด gap `total_accesses = 0`** — instrumented llama.cpp หรือ native core แรก (นี่คือหัวใจ thesis)
9. **Benchmark discipline มาตรฐาน** + นิยาม Phase 4 metrics (P50/P95 tok/s, TTFT, fault MB/tok)

### Priority ต่อ — Product & Community
10. **PyPI release v0.15.0** (หลัง security fix) + ลด dependency บน Jan binary (document/auto-download llama-server)
11. Linux CI + smoke test; mypy --strict ลด baseline 225
12. **Kimi-Linear 48B PoC** (stepping stone ไป K3) → K3 support (MXFP4, 896-expert routing) → Paper
13. HW decision point: 3090 24GB + RAM 128GB → ยืนยัน 120–140 tok/s (ผลคูณทุกอย่าง)

### Quick wins (2–4 สัปดาห์แรก)
- EXP-018 IQ2_XXS · simulator calibration · PyPI prep · Phase 4 metrics · Kimi-Linear 48B first run

> รายละเอียดเต็ม: `research/05-roadmap-plan.md` (D1–D19 + dependencies + KPI + gates)

---

## ⚠️ สิ่งที่ยังไม่ได้ตรวจสอบ (ตรงไปตรงมา)
- ไม่ได้รันเทส/ติดตั้งจริง; ไม่ได้ browser-test — findings จาก static + code-path analysis + การทดสอบ path-traversal จริง 1 จุด
- Frontend บางหน้า (Stats/Models/Settings/MCPSection/Assistants/Docs), components บางตัว, locale files, gguf/parser.py, tools/*, io/*, scripts/* — ยังไม่ครบทุกบรรทัด
- ไม่ได้ grep secrets ใน git history เต็ม (shallow clone)
- ไม่ได้เทียบ API contract ระหว่าง SPA กับ server อย่างละเอียด
- ตัวเลข benchmark ใน README อ้างอิงจาก repo (ไม่ได้วัดซ้ำ)

---

## 🖋️ ผู้รีวิว & หลักฐาน

| บทบาท | ผู้รีวิว | วันที่/เวลา |
|---|---|---|
| **หัวหน้าทีมรีวิว / ผู้สังเคราะห์** | OpenCode Agent (DeepSeek-V4-Flash-0731) · ตรวจ verified findings + ทดสอบ path traversal จริง | 2026-08-10 |
| สถาปัตยกรรม & Goal Alignment | Agent: synthesizer (docs/architecture) | 2026-08-10 |
| Code Review (Python/Backend) | Agent: reviewer | 2026-08-10 |
| Security Audit | Agent: security-auditor | 2026-08-10 |
| Frontend/UX Review | Agent: reviewer (frontend focus) | 2026-08-10 |
| Roadmap & Maximization | Agent: planner-plus | 2026-08-10 |

**เวลาเสร็จสิ้นรีวิว:** 10 สิงหาคม 2026, เวลา ~16:00 น. (ICT)

---
*Generated by multi-agent review workflow — 5 agents parallel + main-agent verification. รายงานฉบับเต็มรายมิติในโฟลเดอร์ `research/` (01–05) และ HTML report: `report.html`*
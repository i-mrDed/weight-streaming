# Task Board — Speculative Weight Streaming

> **用途:** ติดตามงานค้าง งานกำลังทำ งานเสร็จ — ทั้งระยะสั้นและระยะยาว  
> **รูปแบบ:** 📥 Backlog → 🔄 In Progress → ✅ Done  
> **ต้องทำ:** อัปเดตทุกครั้งที่เริ่ม/จบ task

---

## 🔄 Chat Agent Tools — filesystem access สำหรับแชท (2026-08-11) — แผน: docs/AGENT_TOOLS_PLAN.md

| สถานะ | Task | Priority | Notes |
|-------|------|----------|-------|
| ✅ | Phase 1: Agent loop ใน ChatPage — ส่ง tools (MCP ∪ built-in) + execute tool_calls + loop (cap 10 รอบ) + tool card UI | 🔴 | 2026-08-11: `core/chat.ts` (buildWireMessages/formatToolResult/truncateToolResult) + vitest 14; agent mode ใช้ non-stream tool turns (ได้ tool_calls ครบจาก P7.3 path เดิม) + tool cards; toolState running/done/error |
| ✅ | Phase 2: Built-in workspace tools ฝั่ง server — `workspace_tools.py` (list_directory/read_file/workspace_info) + path guard (commonpath+realpath, symlink, size cap 256KB) + routes `/v1/agent/*` + state `data/agent.json` | 🔴 | 2026-08-11: 16 hermetic tests ผ่าน (escape ../ / abs นอก root / symlink → 403; too-large → 400; config round-trip) |
| ✅ | Phase 3: Settings → Agent & Workspace section — workspace root + enabled toggle + รายการ tools | 🟡 | 2026-08-11: `AgentSection.tsx` + locale en/th + CSS |
| ✅ | Phase 4: E2E สด — restart server → ทดสอบแชท agent (MCP filesystem + built-in) + injection probe | 🔴 | 2026-08-12: server :8765 โค้ดใหม่ + Qwen3-0.6B — agent loop ครบวงจร (workspace_info ✓ / list_directory("/") → 403 ✓ / read_file ✓ → ตอบสรุป) · MCP filesystem จริง (npx) 14 tools + read_file/list_directory ผ่าน · injection probe PASS (payload ถูก treat เป็น data, ไม่มีไฟล์หลุด/รัน) · fixes จาก E2E: chat_template_kwargs forward + mcp_host stdio/sse 1.27 + .gitignore data/agent.json — pytest hermetic **401/7/0** · vitest 51/51 ✓ · typecheck ✓ · i18n ✓ · build ✓ |

---

## ✅ Console: per-tier n_ctx/max_tokens + Models load extra_args (2026-08-11)

| สถานะ | Task | Priority | Notes |
|-------|------|----------|-------|
| ✅ | Settings → Auto-tiering: แก้ n_ctx/max_tokens ต่อ tier | 🟡 | UI (TieringSection) + validation ใน `tiering.py` + tests round-trip; route อ่านค่าเดิมอยู่แล้ว (EXP-023) |
| ✅ | Models load form: ช่อง extra llama-server args | 🟡 | `/v1/models/load` รับอยู่แล้ว; auto-detect MTP draft ตอน pick scan result / swap quant |
| ✅ | `setTier` เก็บ n_ctx/max_tokens ต่อ tier ตอน pin | 🟡 | `core/tiering.ts` — re-pin ไม่ reset ค่า tier; ต่างโมเดลยัง clear extra_args กัน draft ค้าง |
| ✅ | vitest: tiering pin (n_ctx/max_tokens) + models (extra_args payload, MTP draft auto-detect) | 🟡 | `core/tiering.test.ts` (4) + `core/models.test.ts` (6) — mock แค่ apiJSON, ไม่ต้อง DOM; suite 30/30 |

---

## ⬜ Hermeticity Fixes (2026-08-11) — รายงาน: docs/HERMETIC_AUDIT.md

| สถานะ | Task | Priority | Notes |
|-------|------|----------|-------|
| ✅ | `tests/test_server.py` — opt-in (`WS_E2E=1`) ไม่ auto-run ต่อ live server | 🔴 | 2026-08-11: gate เป็น WS_E2E; เพิ่ม WS_TEST_SERVER_URL/WS_TEST_MODEL; แก้พอร์ต 8383 vs 8765 ใน standalone runner |
| ✅ | `tests/test_split_parser.py` — default path แข็ง → `~/models/...` (expand ตอนเรียก) | 🔴 | 2026-08-11: ไม่รั่ว username แล้ว; empty-HOME → skip 9 ตัว |
| ✅ | Fixture GGUF สังเคราะห์สำหรับ `test_gguf.py` + `test_split_parser.py` | 🔴 | 2026-08-11: `tests/fixtures/synthetic_gguf.py` สร้าง qwen2moe + DSV4 4-shard จิ๋วตอน test (gguf+numpy เป็น runtime dep อยู่แล้ว); parser test 20 ตัวรันจริงใน CI — hermetic suite 382 passed / 7 skipped (skip = test_server opt-in เท่านั้น) |
| ✅ | Smoke scripts (`test_llama_server.py`, `test_tools.py`, `test_mcp.py`, `test_assistants.py`) — path เป็น env-driven | 🟡 | 2026-08-11: `WS_TEST_MODEL` + `WS_DATA_DIR` fallback เป็น temp dir |
| ✅ | `scripts/measure_*.py` — default `WS_TEST_MODEL` จาก `D:/models/...` → `~/models/...` | 🟡 | 2026-08-11: 6 scripts; `os.path.expanduser` ตอนอ่านค่า (convention เดียวกับ tiering.py) |
| ✅ | Experiment artifacts (`research/experiments/EXP-0*/`) + `docs/MODEL_INVENTORY.md` — ～-ize paths | 🟢 | 2026-08-11: 20 ไฟล์ (`C:/Users/dedch/...`, `C:\Users\dedch\...`, `D:/models`, `D:\models`) → `~/models/...`; audit doc ใช้ `<user>` placeholder; JSON ตรวจ parse ผ่าน; `git grep dedch` ใน research+docs สะอาด |
| ✅ | ลบ `Qwen3.6-35B-A3B-UD-IQ2_M.gguf.part` (7.8 GB) ออกจาก working tree | 🟢 | 2026-08-11: ยืนยันเป็น download ค้าง 73% (mtime ค้าง 7.5h, hub task = 0, ไม่มีโค้ดอ่านไฟล์นี้; โมเดลเต็มอยู่ที่ D:/models แล้ว) → ลบ — Hermeticity Fixes ปิดครบทุกข้อ |

---

## ✅ Dependabot vulnerabilities (2026-08-11)

| สถานะ | Task | Priority | Notes |
|-------|------|----------|-------|
| ✅ | dompurify ≤3.4.12 (moderate XSS) → 3.4.13 | 🟡 | `^3.4.13`; API เดิม (sanitize + addHook) ไม่เปลี่ยน |
| ✅ | nanoid <3.3.17 (high) → 3.3.18 | 🟡 | transitive ผ่าน vite→postcss; `npm audit fix` ภายใน range เดิม |
| ✅ | sharp <0.35.0 (high libvips CVEs) → 0.35.3 | 🟡 | dev-only (gen-icons.mjs); API ใช้เหมือนเดิม; favicon.ico re-encode ด้วย libvips ใหม่ |
| ✅ | `npm audit` 0 vulnerabilities | 🟡 | ตรวจแล้ว 2026-08-11 |
| ✅ | CI guard: `npm audit --audit-level=moderate` ใน frontend job | 🟡 | 2026-08-11: เพิ่ม step หลัง `npm ci` — vulnerability ระดับ moderate+ ใหม่ทำ CI แดงทันที |

---

## ✅ P7 + EXP-009…013 + Repo Release Prep (2026-08-04 → 2026-08-10)

| สถานะ | Task | Priority | Notes |
|-------|------|----------|-------|
| ✅ | P7.1b LlamaServerBackend (GPU) | 🔴 | spawn llama-server: `-ngl`/`--n-cpu-moe`, reasoning mode, date injection, subprocess page-fault telemetry, readiness 300s |
| ✅ | P7.2 Assistants CRUD + UI | 🔴 | `/v1/assistants` + AssistantsPage + assistant-ref guards on hub delete/clear |
| ✅ | P7.3 tool calling + P7.4 MCP host | 🔴 | `tools`/`tool_calls` protocol + stdio/SSE MCP mgmt + settings UI |
| ✅ | P7.5 GPU load options | 🔴 | `gpu_layers`/`kv_cache_type` (ModelLoadRequest + Settings) + quant advisor `/v1/hardware` |
| ✅ | EXP-009 KV q8 no-op · EXP-010 spec-decode dead end | 🟡 | clean-room gate (check_clean_environment.py) + EXP-005/006 re-validated (contaminated) |
| ✅ | EXP-011 IQ1_M 72–78 tok/s + Thai tonal quality | 🟡 | IQ1_M vs IQ2_M: 8/9 dimensions equal, Thai tonal broken |
| ✅ | EXP-012 DS V4 Flash 104 GB | 🔴 | 1.48–1.89 tok/s disk-bound; harness + download script + fixes (priority, disk-gate resume, timeout) |
| ✅ | EXP-013 kimi-k3-in-c deep-research | 🟡 | scored 87/120 vs theirs 71/120; takeaways → hardware plan |
| ✅ | Repo restructure + GitHub CI green | 🔴 | project at repo root (`i-mrDed/weight-streaming`); Python (Windows) + frontend CI; deps declared |

---

## ✅ Current Operational Reliability — SPA Chat (2026-07-28 → 2026-07-29)

| สถานะ | Task | Priority | Notes |
|-------|------|----------|-------|
| ✅ | Propagate server configuration to SPA-loaded models | 🔴 | `ModelManager` receives the factory config; default threads = half logical cores |
| ✅ | Keep local chat model loaded by default | 🔴 | `idle_unload_timeout = 0`; positive timeout opts in to reclamation |
| ✅ | Use native GGUF chat template + expose `top_p` | 🔴 | `create_chat_completion()` first; manual formatter is fallback only |
| ✅ | Move blocking token iterator off the asyncio event loop; batch SPA token rendering | 🔴 | Worker-thread bridge (`ModelManager._iter_blocking`: bounded queue + cooperative cancel); SPA renders via `requestAnimationFrame` + `textContent`; verified `/health` ≤ 28 ms during generation (Qwen1.5-MoE Q2_K, 14–15 tok/s) |
| ✅ | Route SPA chat through public `WeightStreamModel` streaming wrapper and real telemetry | 🔴 | `WeightStreamModel.stream_chat()` public wrapper (native template → fallback, real stats incl. cancelled runs, page-cache sampling, no synthetic prefetch); server no longer touches `model._llm` for chat; SPA stats panel de-faked (n/a instead of fabricated values, heatmap without random firing) |
| ✅ | Validate CPU, cancellation, template quality, and telemetry with a real GGUF + SPA | 🔴 | Real end-to-end with `Qwen1.5-MoE-A2.7B_Q2_k.gguf` + live SPA in Chrome: 3/3 checks passed; cancellation releases lock (regen 540 ms after abort); raw results in `docs/verification/`. Llama-family GGUF not available locally — native-template check covers Qwen only |

---

## ✅ Real-Use Reliability Round (2026-07-30, from user live testing)

| สถานะ | Task | Priority | Notes |
|-------|------|----------|-------|
| ✅ | วินิจฉัย 3–4 tok/s (Kimi R37 F16 / Ornith Q6_K) | 🔴 | physics ไม่ใช่ bug: bandwidth-bound (tok/s ≈ BW ÷ bytes/token); F16 4.2B อ่าน 8.4 GB/tok → วัด 2.8 ตรงคำทำนาย; ทุกจุดบนเส้น ~23–35 GB/s เดียวกัน |
| ✅ | แก้ CPU saturation | 🔴 | พบบั๊ก n_threads=None→16 threads + เพิ่ม below-normal priority (`io/process_priority.py`, WS_LOWER_PRIORITY); วัด: 56.2%→22.6% process, 80.1%→37.0% system, tok/s 2.8→2.5 |
| ✅ | THR control รายโมเดลใน SPA | 🟡 | ช่อง THR + วัด trade-off: THR=4 → 16.0% CPU / 2.3 tok/s |
| ✅ | แยก Thinking ออกจากคำตอบในแชท | 🟡 | ` think ` tags (streaming-safe) + verbal "Thinking Process:" heuristic; ยืนยันสดใน Chrome กับ Kimi R37 (screenshot ใน docs/verification/) |
| ✅ | คู่มือเลือกโมเดล + เตือน F16 | 🟡 | `docs/MODEL_GUIDE.md` + scan `quant` field + SPA ⚠️ warning + README section |
| ✅ | แก้ `/v1/models/scan` บล็อก event loop | 🔴 | pre-existing; พบตอนสแกน Jan folder — ย้ายเข้า executor; ระหว่างสแกน 113s health 45/45 OK; เพิ่ม Jan path ใน default scan |
| ✅ | Calibrate simulator ด้วย physics model (BW ÷ bytes/token) + multi-model data | 🟡 | EXP-025: `simulator/physics.py` (BW = bytes/token × tok/s, calibrated ต่อ tier: cpu-ram 19.18 / gpu-vram 61.09 / disk-mmap 0.38 GB/s) + `calibrate.py` CLI; TimingConfig derive จาก physics (814.7ms ตรง EXP-004 0.08%); 10 hermetic tests; workflow `calibrate-simulator` ใน MongoModel |

---

## 📋 Phase 1: Research Review

| สถานะ | Task | Priority | Notes |
|-------|------|---------|-------|
| ✅ | Define concept + feasibility | 🔴 | v0.1.0 |
| ✅ | Survey: Speculative Decoding | 🔴 | 8 papers |
| ✅ | Survey: MoE Routing Prediction | 🔴 | 10 papers |
| ✅ | Survey: Out-of-Core Execution | 🔴 | 8 projects |
| ✅ | Survey: Near-Storage Compute | 🟡 | 5 papers |
| ✅ | Survey: Kimi K3 Architecture | 🔴 | Deep dive |
| ✅ | Setup documentation system | 🔴 | SESSION_LOG, ADR, GLOSSARY, TASKS, WORKFLOW |
| ⬜ | Read PreScope paper (full) | 🟡 | arXiv 2509.23638 |
| ⬜ | Read EAGLE-3 paper (full) | 🟡 | arXiv 2503.01840 |
| ⬜ | Test llama.cpp expert offloading | 🟡 | ต้องมี hardware |

---

## 📋 Phase 2: Architecture Design

| สถานะ | Task | Priority | Notes |
|-------|------|---------|-------|
| ✅ | Design data layout (NVMe sharding) | 🔴 | Shard-based, popularity layout, O(1) index |
| ✅ | Design Weight Predictor architecture | 🔴 | MLP (PreScope-style), 3 options, fallback |
| ✅ | Design Pre-fetch Scheduler | 🔴 | Priority queue, I/O batching, timing model |
| ✅ | Design Streaming Buffer management | 🔴 | LRU+priority, 256 MB default, cold start |
| ✅ | Design Execution Engine interface | 🔴 | BufferReader, MmapFallback, ComputeOrch |
| ✅ | Design abstraction layer (MoE vs Dense) | 🟡 | Plugin architecture, common interface |
| ✅ | **สรุปเป็น docs/ARCHITECTURE.md** | 🔴 | 6 components + interfaces + roadmap |

---

## 📋 Phase 3: Prototype

| สถานะ | Task | Priority | Notes |
|-------|------|---------|-------|
| ✅ | Create simulator framework | 🔴 | access_pattern, buffer, predictor, timing, run |
| ✅ | EXP-001: Buffer size + eviction policy | 🔴 | LFU 512 MB → 78.2% hit rate (confirmed) |
| ✅ | EXP-002: Predictor accuracy impact | 🟡 | LFU flat (76.2%), LRU+P clogging, compute-bound |
| ✅ | EXP-003: Timing + overlap efficiency | 🔴 | 76.7% overlap, 2.74 tok/s |
| ✅ | Update ARCHITECTURE.md with EXP-002 findings | 🟡 | Note เดิม stale (LFU default เป็นผลก่อน real-timing) — สรุปสุดท้ายคือ plain LRU (Phase 3b + ADR-003); เพิ่ม §0 As-Built summary + inline annotations ใน ARCHITECTURE.md แล้ว (2026-07-30) |
| ⬜ | Select small MoE model for PoC | 🟡 | Mixtral? Qwen MoE? |
| ✅ | Estimate real compute time for K3 on consumer HW | 🔴 | Qwen benchmark → K3: 815ms compute, ~92% compute-bound |
| ✅ | Update simulator with real K3 timing (815ms compute) | 🔴 | Done (config.py timing) |
| ✅ | Phase 3b: Re-run EXP-001/002/003 with real timing | 🔴 | LRU wins, predictor not critical |
| ✅ | Update ARCHITECTURE.md with real HW findings | 🟡 | ADR-003 มีอยู่แล้ว (2026-07-27) — เพิ่ม addendum ผล real-model validation (Qwen1.5-MoE 2026-07-29: 17.9 tok/s, health ≤ 23.3 ms, residency 4.6%, buffer gap total_accesses=0) + ARCHITECTURE.md §0 (2026-07-30) |
| ✅ | Build streaming buffer abstraction prototype | 🔴 | EXP-026: `simulator/buffer_abstraction.py` — protocol `BufferBackend` + `SimulatorBufferAdapter` (หุ้ม buffer เดิมไม่แตะ behavior) + `TelemetryBufferObserver` (แปลง OS signals ที่ ship แล้วเป็น buffer stats); predicted tok/s จาก EXP-025 calibrated BW — **warm spike 22.02 vs measured 21.88 tok/s (Δ+0.6%)**; 9 hermetic tests; ปิด open gap ใน ARCHITECTURE.md §0 แล้ว |
| ✅ | Measure OS paging demand during real generation (spike) | 🔴 | `scripts/spike_page_faults.py`: cold ≈ 175 MB/token → warm ≈ 0.55 MB/token (300× drop) — OS working set ถือ hot set จริง; raw: `docs/verification/spike_page_faults_2026-07-30.json` |
| ✅ | Ship paging-demand telemetry in `/v1/stats` | 🟡 | `weight_stream/io/page_faults.py` (Win psapi / POSIX rusage) + `generation.paging` ใน stats ของ `stream_chat()`/`generate()`; SPA card "PAGING DEMAND" + hard/soft split (`disk_demand_mb`) เสร็จวันเดียวกัน — cold 7.86 vs warm 0 MB/tok disk |
| ✅ | Public streaming wrapper สำหรับ plain-prompt path | 🟡 | `WeightStreamModel.stream_prompt()` — server code ไม่มี `_llm` เหลือเลย (chat + completions ผ่าน wrapper หมด); ยืนยัน live กับ Llama-3.2-1B |
| ✅ | MyPy type check pass | 🟡 | non-strict clean 0 errors / 43 files + `[tool.mypy]` ใน pyproject; strict baseline 225 (legacy annotations) → งาน gradual |
| ✅ | Validate: real throughput matches simulator | 🟡 | EXP-025: Qwen1.5-MoE-A2.7B Q2_K จริง (CPU pure, ผ่าน server) วัด warm เฉลี่ย 20.76 tok/s vs physics prediction 22.73 → **−8.7% (ใน tolerance ±15%)**; implied BW 17.51 GB/s; รายละเอียดใน EXP-025 results.md |
| ✅ | Phase 3b: Test with real MoE model on consumer HW | 🔴 | EXP-027: Qwen1.5-MoE-A2.7B Q2_K CPU pure วัดจริง — compute 43.8–44.0 ms/token คงที่ (ตรง physics 0.844GB/19.18GB/s), I/O stall แค่ 1.9–9.7 ms warm (ratio 13:1+) = **compute-bound** เมื่อพอดี RAM; K3 (>RAM) = **I/O-bound** ที่ 5% miss (stall 2056ms > compute 774ms) ยืนยัน EXP-004; 6 hermetic tests |

---

## 📋 Phase 4: Evaluation

| สถานะ | Task | Priority |
|-------|------|---------|
| ⬜ | Define evaluation metrics | 🟡 |
| ⬜ | Benchmark: hit rate | 🟡 |
| ⬜ | Benchmark: latency distribution | 🟡 |
| ⬜ | Benchmark: throughput | 🟡 |

---

## 📋 Phase 5: Paper / Publication

| สถานะ | Task | Priority |
|-------|------|---------|
| ⬜ | Draft paper outline | 🟢 |
| ⬜ | Write: Introduction | 🟢 |
| ⬜ | Write: Related Work | 🟢 |
| ⬜ | Write: Architecture | 🟢 |
| ⬜ | Write: Evaluation | 🟢 |

---

## 🔥 Legend

| สัญลักษณ์ | ความหมาย |
|----------|---------|
| 🔴 High | ต้องทำก่อน — blocking task |
| 🟡 Medium | ควรทำ แต่ไม่ blocking |
| 🟢 Low | Nice to have |
| ✅ | เสร็จแล้ว |
| 🔄 | กำลังทำ |
| ⬜ | ยังไม่เริ่ม |
| ❌ | ยกเลิก |

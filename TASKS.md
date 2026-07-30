# Task Board — Speculative Weight Streaming

> **用途:** ติดตามงานค้าง งานกำลังทำ งานเสร็จ — ทั้งระยะสั้นและระยะยาว  
> **รูปแบบ:** 📥 Backlog → 🔄 In Progress → ✅ Done  
> **ต้องทำ:** อัปเดตทุกครั้งที่เริ่ม/จบ task

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
| ⬜ | Calibrate simulator ด้วย physics model (BW ÷ bytes/token) + multi-model data | 🟡 | ข้อมูลวัดพร้อมแล้วใน docs/verification/ |

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
| 🔄 | Build streaming buffer abstraction prototype | 🔴 | ทิศทางจาก spike 2026-07-30: ไม่ intercept การอ่านของ llama.cpp (ADR-003 no-fork) — StreamingBuffer เป็น tracker ของ simulator + native core อนาคต (`core/native/`); telemetry production = สัญญาณ OS (residency + page faults) ซึ่ง ship แล้ว |
| ✅ | Measure OS paging demand during real generation (spike) | 🔴 | `scripts/spike_page_faults.py`: cold ≈ 175 MB/token → warm ≈ 0.55 MB/token (300× drop) — OS working set ถือ hot set จริง; raw: `docs/verification/spike_page_faults_2026-07-30.json` |
| ✅ | Ship paging-demand telemetry in `/v1/stats` | 🟡 | `weight_stream/io/page_faults.py` (Win psapi / POSIX rusage) + `generation.paging` ใน stats ของ `stream_chat()`/`generate()`; SPA card "PAGING DEMAND" + hard/soft split (`disk_demand_mb`) เสร็จวันเดียวกัน — cold 7.86 vs warm 0 MB/tok disk |
| ✅ | Public streaming wrapper สำหรับ plain-prompt path | 🟡 | `WeightStreamModel.stream_prompt()` — server code ไม่มี `_llm` เหลือเลย (chat + completions ผ่าน wrapper หมด); ยืนยัน live กับ Llama-3.2-1B |
| ✅ | MyPy type check pass | 🟡 | non-strict clean 0 errors / 43 files + `[tool.mypy]` ใน pyproject; strict baseline 225 (legacy annotations) → งาน gradual |
| ⬜ | Validate: real throughput matches simulator | 🟡 | |
| ⬜ | Phase 3b: Test with real MoE model on consumer HW | 🔴 | Measure actual compute vs I/O ratio |

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

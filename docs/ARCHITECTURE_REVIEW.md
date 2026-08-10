# Architecture Review — Weight Streaming

> **วันที่:** 2026-05-08  
> **ขอบเขต:** monorepo ทั้งหมด (`weight_stream/`, `frontend/`, `simulator/`, `tests/`, docs)  
> **เวอร์ชันอ้างอิง:** v0.14.0  
> **ประเภท:** structural review (module boundaries / coupling / layering / scalability)  
> **ไม่ใช่:** line-by-line code review หรือ security audit เต็มรูป

---

## สารบัญ

1. [บทสรุปผู้บริหาร](#1-บทสรุปผู้บริหาร)
2. [แผนที่สถาปัตยกรรม as-built](#2-แผนที่สถาปัตยกรรม-as-built)
3. [Module boundaries](#3-module-boundaries)
4. [Data flow & Control flow](#4-data-flow--control-flow)
5. [Coupling & Layering findings](#5-coupling--layering-findings)
6. [Scalability & Maintenance risks](#6-scalability--maintenance-risks)
7. [คำแนะนำเชิงโครงสร้าง (ranked)](#7-คำแนะนำเชิงโครงสร้าง-ranked)
8. [ลำดับการลงมือ (ไม่ rewrite ทีเดียว)](#8-ลำดับการลงมือไม่-rewrite-ทีเดียว)
9. [สิ่งที่ทำได้ดีอยู่แล้ว](#9-สิ่งที่ทำได้ดีอยู่แล้ว)

---

## 1. บทสรุปผู้บริหาร

โปรเจกต์นี้วิวัฒนาการจาก **research prototype (speculative weight streaming)** ไปเป็น **full local platform** (API server + SPA console + Hub + Issues + MCP + dual backend) ภายใน package เดียว

| มิติ | สถานะ | หมายเหตุสั้น |
|------|--------|--------------|
| **Core research path** | บางส่วนหลุดจาก runtime | `StreamingBuffer.access()` / `Prefetcher.on_access()` ไม่ถูกเรียกตอน inference จริง (ADR-003 gap) |
| **Product platform** | โตเร็ว | server + SPA ครอง bulk ของ codebase |
| **Layering intent** | ชัดใน docs | `core → backends → server → clients` |
| **Layering practice** | รั่วหลายจุด | god-modules, dual-backend type lie, interface ไม่ครบ |
| **Monorepo hygiene** | กลาง | SPA build เข้า package; simulator แยกจาก core; docs drift |

**ใจความหลัก:** ความเสี่ยงใหญ่ไม่ใช่ “เขียนผิด” แต่เป็น **boundary erosion** — ไฟล์ใหญ่สะสมหลาย responsibility, abstract interface ตามไม่ทัน usage จริง, และ dual-backend ทำให้ product path หลัก (GPU/`llama-server`) **ข้าม weight-streaming core** ไปเลย

---

## 2. แผนที่สถาปัตยกรรม as-built

### 2.1 ขนาดโค้ด (LOC โดยประมาณ)

| พื้นที่ | LOC | บทบาท |
|---------|----:|--------|
| `weight_stream/` (Python) | ~10.1k | library + server + CLI + TUI + Gradio + tools |
| `frontend/src` (TS/CSS) | ~13.4k | Console SPA 2.0 |
| `simulator/` | ~1.1k | Phase 3a research sim (แยกจาก runtime) |
| `tests/` | ~2.8k | unit/API contract tests |

**Top hotspots (Python):**

| ไฟล์ | LOC | บทบาท |
|------|----:|--------|
| `server/api_server.py` | 1047 | FastAPI app + ~40 routes ในไฟล์เดียว |
| `backends/llama_cpp.py` | 936 | composition root ของ streaming path |
| `server/model_manager.py` | 766 | lifecycle + generate + chat + usage |
| `server/hub.py` | 762 | HF search/download |
| `cli/main.py` | 640 | CLI commands |
| `backends/llama_server.py` | 429 | GPU subprocess backend (P7.1b) |

**Top hotspots (Frontend):**

| ไฟล์ | LOC |
|------|----:|
| `styles/pages.css` | 1236 |
| `pages/settings/SettingsPage.tsx` | 1047 |
| `pages/hub/HubPage.tsx` | 880 |
| `pages/chat/ChatPage.tsx` | 727 |
| `pages/models/ModelsPage.tsx` | 616 |

### 2.2 Intended layering (จาก docs + package layout)

```
┌─────────────────────────────────────────────────────────────┐
│ Clients                                                      │
│  frontend/ (SPA) · tui/ · ui/gradio · cli/ · external IDE    │
└───────────────────────────┬─────────────────────────────────┘
                            │ HTTP / WS (intended contract)
┌───────────────────────────▼─────────────────────────────────┐
│ server/                                                      │
│  api_server · model_manager · openai/anthropic · hub · …     │
│  issues/ (side system)                                       │
└───────────────────────────┬─────────────────────────────────┘
                            │ Python API
┌───────────────────────────▼─────────────────────────────────┐
│ backends/                                                    │
│  WeightStreamBackend ABC                                     │
│  ├── llama_cpp.WeightStreamModel   ← uses core + io + gguf   │
│  └── llama_server.LlamaServerBackend ← HTTP subprocess only  │
└───────────────────────────┬─────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────┐
│ core/ + gguf/ + io/                                          │
│  buffer · predictor · prefetcher · exceptions                │
│  GGUFParser · page_faults · win_perf · process_priority      │
└─────────────────────────────────────────────────────────────┘
```

### 2.3 Actual runtime topology (สำคัญ)

```
                    ┌── LlamaServerBackend (preferred ถ้ามี binary)
ModelManager._create_backend ─┤
                    └── WeightStreamModel (fallback CPU binding)
                              │
                              ├── StreamingBuffer + Prefetcher + HeuristicPredictor
                              ├── dual mmap (own + llama.cpp)
                              └── WindowsPageMonitor / page_faults
```

**ผลกระทบ:** เมื่อมี `llama-server` (กรณี GPU/Jan binary) path หลักของ product **ไม่ผ่าน core streaming เลย** — core กลายเป็น fallback path มากกว่า product spine

---

## 3. Module boundaries

### 3.1 สรุปราย package

| Module | ขอบเขตที่ตั้งใจ | ขอบเขตจริง | คะแนน boundary |
|--------|------------------|------------|----------------|
| `core/` | buffer/predict/prefetch pure-ish | เล็ก ชัด ไม่ import ขึ้น | ดี |
| `gguf/` | metadata parser | ใช้จาก backends เท่านั้น | ดี |
| `io/` | platform telemetry/priority | ถูก backends + model_manager เรียก | ดี (platform-specific) |
| `backends/` | inference adapters | ABC ไม่ครบ; llama_cpp = god object | อ่อน |
| `server/` | HTTP + lifecycle | god module routes; หลาย side features | อ่อน |
| `issues/` | issue tracking domain | แยกดี; mount ที่ api_server | ดี |
| `cli/tui/ui` | clients ผ่าน API | TUI/Gradio ผ่าน HTTP; **CLI import backend ตรง** | ปานกลาง |
| `frontend/` | SPA console | build artifact เข้า `server/static/console` | ผูก deploy |
| `simulator/` | research | **fork logic** ของ buffer/predictor ไม่ share กับ core | drift risk |
| `tools/` | bench/repack/auto-tune | ใช้ core ได้ถูกต้อง | ดี |

### 3.2 Public API surface

```python
# weight_stream/__init__.py
from .backends.llama_cpp import WeightStreamModel   # concrete only
from .core.exceptions import ...
```

- Public entry ผูก **concrete backend** ไม่ใช่ ABC / factory
- `stream_chat` / `stream_prompt` / `get_capabilities` เป็น **de-facto contract** ของ server แต่ **ไม่อยู่ใน `WeightStreamBackend` ABC**
- Type hint ใน `ModelManager._models: Dict[str, WeightStreamModel]` เป็น **type lie** — เก็บ `LlamaServerBackend` ได้ด้วย

### 3.3 Dependency direction (ที่พบ)

| From → To | ถูก/ผิด | หมายเหตุ |
|-----------|---------|----------|
| backends → core/gguf/io | ✅ | ถูกต้อง |
| server → backends | ✅ | ถูกต้อง |
| server → issues | ✅ | side domain ผ่าน package boundary |
| server → io (process_priority) | ⚠️ | server รู้ platform detail; ยอมรับได้ชั่วคราว |
| cli → backends (ตรง) | ⚠️ | ข้าม server; ขัด “frontends only via API” ใน FULL_PLATFORM_ARCHITECTURE |
| frontend types ↔ server schemas | ⚠️ | hand-synced; ไม่มี OpenAPI codegen |
| simulator ↛ core | ⚠️ | duplicate concepts |
| capabilities อยู่ใน server/ | ⚠️ | backends ใช้ logic นี้ — ควรอยู่ shared/domain ไม่ใช่ server-only |

---

## 4. Data flow & Control flow

### 4.1 Chat / generate (product path หลัก)

```
SPA ChatPage
  │  POST /v1/chat/completions  (SSE)  หรือ native generate stream
  ▼
api_server.chat_completions
  │
  ▼
openai_compat.handle_chat_completion
  │
  ▼
ModelManager.chat_completion_stream
  │  asyncio.Lock per model_id
  │  _fit_messages_to_context
  │  _iter_blocking(worker thread + queue)
  ▼
backend.stream_chat(messages, …)
  │
  ├─[LlamaServerBackend]── HTTP SSE → llama-server subprocess → GPU/CPU binary
  │                         (ไม่มี buffer/prefetch)
  │
  └─[WeightStreamModel]──── llama_cpp.Llama / create_chat_completion
                            + round-robin layer expert prefetch (opaque routing)
                            + page-fault / residency sampling
  ▼
token deltas → SSE → SPA store → UI
  │
  finally: model.get_stats() → UsageRecorder
```

**Control points สำคัญ**

| จุด | กลไก | ผล |
|-----|------|-----|
| Per-model lock | `asyncio.Lock` | 1 generate/model พร้อมกัน |
| Event-loop safety | `_iter_blocking` | /health, /stats ไม่ค้างระหว่าง generate |
| Cancel | queue stop flag ~0.25s | cooperative stop |
| Idle unload | background task | reclaim RAM |
| Backend select | `_create_backend` at load | เลือกครั้งเดียวตอน load |

### 4.2 Model load lifecycle

```
POST /v1/models/load
  → ModelManager.load
      → enforce max_loaded_models (evict oldest idle)
      → run_in_executor(_create_backend)
          → prefer LlamaServerBackend if binary found
          → else WeightStreamModel (mmap + buffer + prefetcher.start)
      → lower_process_priority (first model)
      → start _auto_cleanup task
```

### 4.3 Weight-streaming path (research/product intent) — **reality check**

**ที่ design บอก:**

```
access shard → buffer.access → predictor.observe → prefetcher.on_access → OS prefetch
```

**ที่ code ทำจริงใน `WeightStreamModel.generate/stream_*`:**

```
llama.cpp อ่าน mmap ภายใน C++ (opaque)
  → Python เห็นแค่ token chunk
  → ทุก N token: _prefetch_layer_experts(round-robin layer)
  → buffer stats ส่วนใหญ่ไม่ขยับจาก access() จริง
  → page_faults / QueryWorkingSetEx = telemetry ทางอ้อม
```

**หลักฐาน structural:**

- `buffer.access()` ถูกเรียกจาก `tools/benchmark_suite.py` เท่านั้น
- `prefetcher.on_access()` ไม่มี caller นอก definition
- ADR-003 / ARCHITECTURE §0 บันทึก `total_accesses = 0` บน real model แล้ว

→ **core pipeline เป็น “armed but not wired into the hot path”**  
→ telemetry ที่เชื่อถือได้ตอนนี้คือ OS paging + generation timing ไม่ใช่ buffer hit_rate

### 4.4 Hub download flow

```
SPA HubPage → POST /v1/hub/download
  → DownloadManager (hub.py)
  → background task + progress map
  → GET /v1/hub/progress/{id}
  → files ลง model search dirs
  → SPA Models scan เห็นไฟล์ใหม่
```

ขอบเขตของ `hub.py` ใหญ่ (security-hardened writes, HF API, progress) — แยกจาก inference ดีแล้ว แต่ยัง mount แน่นใน `api_server`

### 4.5 Issues flow

```
SPA Issues → /v1/issues* → IssueService → IssueStore (data/issues/)
debug context: collect_debug_context() จาก server state
```

domain แยก package ชัด — แบบอย่างที่ดีสำหรับ feature อื่น

---

## 5. Coupling & Layering findings

จัด severity ตามผลกระทบต่อ maintainability / correctness of architecture

### F1 — Critical: Backend ABC ไม่สะท้อน contract จริง

**อาการ**

- ABC กำหนดแค่ `generate` / `close` / `get_stats`
- Server พึ่ง `stream_chat`, `stream_prompt`, `get_capabilities` ผ่าน duck typing / `getattr`
- `_models: Dict[str, WeightStreamModel]` แต่เก็บได้ทั้งสอง backend

**ผล**

- type checker ช่วยน้อย
- backend ใหม่พังตอน runtime ถ้าลืม method
- documentation ของ “abstraction-first” ไม่ตรงของจริง

### F2 — Critical: Dual backend แยก product value ออกจาก core thesis

**อาการ**

- Default path = `LlamaServerBackend` เมื่อเจอ binary (รวม Jan-bundled path)
- Path นี้ไม่มี StreamingBuffer / Prefetcher / page monitor แบบเต็ม

**ผล**

- Product ที่ user ใช้เร็ว (GPU) ≠ research claim (speculative weight streaming)
- Stats/dashboard บางส่วนกลายเป็น n/a หรือ shape ต่างกัน
- ทดสอบ core บน CPU binding ไม่สะท้อน production default

**Trade-off ที่เข้าใจได้:** P7 ต้องการ GPU + tools + reasoning flags เร็ว — แต่ต้องทำให้ **explicit** ว่ามี 2 product modes ไม่ใช่ backend เดียวกันในสายตาผู้ใช้/API

### F3 — High: God modules

| ไฟล์ | ปัญหา |
|------|--------|
| `api_server.py` (~1047) | factory + CORS + static + 40 routes + config policy + browse helpers |
| `llama_cpp.py` (~936) | load, mmap, streaming, chat templates, reasoning strip, caps, prefetch, stats, warmup |
| `model_manager.py` (~766) | lifecycle + async bridge + context fitting + chat + usage + cleanup |
| `SettingsPage.tsx` / `HubPage.tsx` / `ChatPage.tsx` | UI + data + policy ในหน้าเดียว |

**ผล:** review/test/parallel work ยาก; regression กระจาย

### F4 — High: Weight-streaming core หลุดจาก hot path

ดู §4.3 — เป็น architectural honesty gap ที่ docs รู้แล้ว แต่ codebase ยังคง API/stats surface ราวกับ buffer ทำงาน

**ความเสี่ยง:** decision ผิดจาก metrics หลอก (hit_rate ≈ 0 หรือ stale); effort ไปที่ UI stats แทน wiring จริง

### F5 — Medium: CLI ข้าม API layer

`cli/main.py` import `WeightStreamModel` ตรง — ขัดหลัก “all frontends → API only”

**ผล**

- behavior ต่างจาก server path (ไม่มี ModelManager lock/usage/idle)
- ยาก guarantee parity (chat template, reasoning, backend choice)

### F6 — Medium: Frontend–server contract drift

- Hand-written TS interfaces ใน `core/api.ts` mirror Pydantic
- ไม่มี OpenAPI export / generated client
- Build output ฝังใน Python package (`server/static/console`)

**ผล:** เปลี่ยน schema ฝั่งเดียวพังเงียบ; versioning frontend แยก deploy ยาก

### F7 — Medium: Feature logic วางชั้นผิดที่

| Logic | อยู่ที่ | ควรอยู่ |
|-------|---------|---------|
| Chat template / thinking strip | `llama_cpp.py` (+ บางส่วน manager) | shared formatting module หรือ backend protocol |
| Capability detection | `server/capabilities.py` | `weight_stream/capabilities` หรือ `gguf/` |
| Context window fitting | `model_manager` | shared chat policy |
| Config mutation policy | constants ใน `api_server` | `config.py` |

### F8 — Medium: Simulator / research code drift

- `simulator/buffer.py` + `predictor.py` แยกจาก `core/`
- `core/eagle_dual_predictor.py`, `core/native/` = research leftovers ใน runtime package
- Docs (`ARCHITECTURE.md` sections 1–9) ยังเล่า MLP/io_uring design ยาว — as-built อยู่ §0 เท่านั้น

**ผล:** onboarding สับสนว่าอะไร ship / อะไร research

### F9 — Low–Medium: Dead / thin modules

- `server/streaming.py` มี helpers แต่ routes หลายเส้น implement เอง
- `max_concurrent_requests` / `request_queue_depth` ใน config = documented no-op (api_server reject reasons)
- หลาย frontend (legacy static, Gradio, TUI, SPA) เพิ่ม surface โดยไม่เท่ากันใน feature parity

### F10 — Tests vs architecture

| ครอบคลุมดี | บาง/ขาด |
|------------|---------|
| buffer unit, exceptions, gguf, hub, config, usage, issues, process_priority | dual-backend selection matrix |
| server chat/config contracts | LlamaServerBackend integration |
| | core wiring ใน real generate (access path) |
| | frontend component/contract tests |
| | OpenAPI schema freeze |

---

## 6. Scalability & Maintenance risks

### 6.1 Scalability (runtime)

| ความเสี่ยง | รายละเอียด | ระดับ |
|------------|------------|--------|
| Single-process model | FastAPI + models ใน process เดียว; multi-user จริงยังไม่ใช่เป้า | รับได้สำหรับ local |
| One generate per model | lock ถูกต้องสำหรับ CPU/GPU memory แต่ throughput จำกัด | ตั้งใจ |
| llama-server fixed port default | `DEFAULT_SERVER_PORT = 8805` — หลาย model พร้อมกันชน port | **สูง** ถ้า multi-model GPU |
| max_loaded_models | มี แต่ evict ตอน load ใหม่; ไม่มี memory budget จริง | กลาง |
| Hub downloads | in-process tasks; restart หาย | กลาง |
| No request queue enforcement | config keys เป็น no-op | ต่ำตอนนี้ / ระเบิดตอน multi-client |

### 6.2 Scalability (engineering)

| ความเสี่ยง | รายละเอียด |
|------------|------------|
| File size growth | api_server / llama_cpp / หน้า SPA ใหญ่เกิน review unit (~300–1000 LOC guidance) |
| Feature velocity บน god module | P4/P5/P7 ต่อ route ใน api_server → merge conflict + regress |
| Docs sprawl | briefs เยอะ; as-built กระจัด; ROADMAP ยังพูด win_iocp ที่อาจไม่ตรง ship |
| Two issue systems | `ISSUES.md` vs `data/issues/` — ตั้งใจแยก แต่ cognitive load |
| Windows-first io | `win_perf`, Jan path ใน APPDATA — Linux/macOS path ยังบาง |

### 6.3 Maintenance “time bombs”

1. **Jan binary discovery** ใน `llama_server.py` — coupling กับ third-party install layout  
2. **Round-robin expert prefetch** — ดูเหมือน smart แต่ไม่ผูก actual routing → หลอกว่ามี streaming intelligence  
3. **Stats shape ต่างกันข้าม backend** — UI ต้อง defensive; ง่ายพลาด  
4. **SPA CSS monolith** (`pages.css` 1.2k+) — theme/token แยกแล้วแต่ pages ยังรวมก้อน

---

## 7. คำแนะนำเชิงโครงสร้าง (ranked)

จัดอันดับด้วย **Impact × (1/Effort)** และระบุ trade-off — **ไม่แนะนำ big-bang rewrite**

### R1 — ขยาย Backend Protocol ให้ตรง usage จริง  
**Impact: สูง | Effort: ต่ำ | Priority: P0**

**ทำอะไร**

```text
WeightStreamBackend (ABC)
  + stream_chat(...)
  + stream_prompt(...)
  + get_capabilities() -> dict
  + optional: start()/is_ready
ModelManager._models: Dict[str, WeightStreamBackend]
```

**ได้**

- type safety, backend ใหม่ชัด
- ปิด F1 ทันที

**Trade-off**

- ต้อง touch tests + ทั้งสอง backend  
- ยังไม่แก้ dual-path semantics (ทำคู่ R2)

**อย่า** rewrite manager ทั้งก้อน — แค่ type + abstract methods

---

### R2 — แยก Product Mode ให้ชัด: `streaming` vs `server`  
**Impact: สูง | Effort: ต่ำ–กลาง | Priority: P0**

**ทำอะไร**

- API/status รายงาน `backend_type`: `weight_stream` | `llama_server`
- Config explicit: `WS_BACKEND=auto|binding|llama-server` (มีอยู่บางส่วนแล้ว → ทำให้ first-class ใน /v1/models + SPA)
- Docs/README: ตาราง “what you get per mode” (prefetch stats เฉพาะ binding)

**ได้**

- ซื่อสัตย์กับ user และ research narrative
- ลดการ optimize ผิด path

**Trade-off**

- UX ซับซ้อนกว่านิด (ต้องเลือก/เห็น mode)
- ไม่ merge สอง backend เป็นหนึ่ง (และไม่ควรในระยะนี้)

---

### R3 — แตก `api_server.py` เป็น routers  
**Impact: สูง | Effort: กลาง | Priority: P1**

**โครงสร้างเสนอ**

```text
server/
  app_factory.py          # create_app, middleware, lifespan, static
  routes/
    health.py
    models.py
    generate.py
    chat_compat.py        # openai + anthropic thin
    hub.py
    issues.py
    assistants.py
    mcp.py
    config_usage_logs.py
```

**ได้**

- parallel work, review เล็กลง, ทดสอบ router แยกได้

**Trade-off**

- move-only PR เสี่ยง conflict ถ้าทำพร้อม feature  
- ควรเป็น **PR ย้ายอย่างเดียว** ไม่เปลี่ยน behavior

**อย่า** ใส่ business logic ใหม่ระหว่างย้าย

---

### R4 — แตก `WeightStreamModel` เป็น composition  
**Impact: สูง | Effort: กลาง | Priority: P1**

**แยกเป็น**

| Module ใหม่ | ย้ายจาก |
|-------------|---------|
| `backends/chat_format.py` | `_format_chat_prompt`, thinking strip |
| `backends/gen_telemetry.py` | page fault / residency / _last_gen_stats packing |
| `backends/llama_cpp_loader.py` | mmap + Llama ctor + gguf expert map |
| `llama_cpp.py` | thin façade: generate/stream_* only |

**ได้**

- ทดสอบ format/telemetry โดยไม่โหลดโมเดล
- ลด god object

**Trade-off**

- ต้องระวัง circular import  
- ไม่เปลี่ยน behavior ภายนอก

---

### R5 — ตัดสินใจครั้งเดียวเรื่อง core wiring  
**Impact: สูง (strategic) | Effort: สูง ถ้า wire จริง / ต่ำ ถ้า demote | Priority: P1**

มี 2 ทาง — **เลือกอย่างใดอย่างหนึ่ง** อย่าค้างกลางคัน:

| ทาง | งาน | เมื่อไหร่ |
|-----|------|----------|
| **A. Wire จริง** | native hook / llama.cpp callback / buffer-abstraction prototype (ตาม TASKS Phase 3) ให้ `access/on_access` เห็น real reads | ถ้า research thesis ยังเป็นเป้าหลัก |
| **B. Demote อย่างซื่อสัตย์** | ย้าย buffer/predictor ไป `research/` หรือ mark experimental; stats เอา OS paging เป็น primary; เลิกโชว์ hit_rate หลอก | ถ้า product = local LLM platform บน llama-server เป็นหลัก |

**Trade-off**

- A = ตรง ADR-001 vision แต่ cost สูง + ต้อง C++/native  
- B = ลด confusion เร็ว แต่ต้องอัปเดต marketing/README ให้ตรง

**แนะนำระยะสั้น:** B บน product surface + คง A เป็น explicit experimental track (อย่าโชว์เป็น default metric)

---

### R6 — ย้าย shared domain ออกจาก server  
**Impact: กลาง | Effort: ต่ำ–กลาง | Priority: P2**

```text
weight_stream/capabilities.py   ← จาก server/capabilities.py
weight_stream/chat/context.py   ← fit_messages_to_context
weight_stream/chat/templates.py ← format helpers
```

backends + server + cli ใช้ชุดเดียวกัน

**Trade-off:** package root โตขึ้นเล็กน้อย; คุ้มเพราะลด duplication ข้าม backend

---

### R7 — Contract lock: OpenAPI → TS types  
**Impact: กลาง | Effort: กลาง | Priority: P2**

- export OpenAPI จาก FastAPI ใน CI  
- generate `frontend/src/core/api-types.ts`  
- fail CI เมื่อ drift

**Trade-off:** toolchain เพิ่ม; ลด bug ประเภท field rename เงียบ

---

### R8 — CLI ให้พูดผ่าน HTTP (opt-in local)  
**Impact: กลาง | Effort: กลาง | Priority: P2**

- default: `weight-streaming run` → client ต่อ local server  
- หรือ `--direct` สำหรับ offline script ที่รู้ว่าข้าม manager

**Trade-off:** ต้อง server ขึ้นก่อน; DX ช้าลงเล็กน้อยแต่ parity ดีขึ้น  
ทางเลือกถูกกว่า: แชร์ “facade” Python เดียวกับ ModelManager โดยไม่ผ่าน HTTP แต่ **ห้าม** เรียก `WeightStreamModel` ตรงจาก CLI ยาว ๆ

---

### R9 — Multi-model llama-server ports + process registry  
**Impact: กลาง–สูง (เมื่อ multi GPU model) | Effort: กลาง | Priority: P2**

- dynamic port / port pool  
- registry ใน ModelManager  
- health check subprocess ตาย

**Trade-off:** ซับซ้อนกว่า fixed port; จำเป็นก่อนโฆษณา multi-model GPU

---

### R10 — Frontend page splits + CSS modularization  
**Impact: กลาง | Effort: กลาง–สูง | Priority: P3**

- แยก Settings/Hub/Chat เป็น features/ + hooks/ + presentational  
- แยก `pages.css` ตาม route

**Trade-off:** churn UI สูง; ทำทีละหน้าคู่กับ feature อย่าแยก PR มหาศาล

---

### R11 — Simulator ใช้ core หรือ mark archival  
**Impact: ต่ำ–กลาง | Effort: ต่ำ | Priority: P3**

- import `StreamingBuffer` จาก core ใน sim **หรือ**  
- ย้าย `simulator/` + `eagle_dual_predictor` + `core/native` → `research/` package ชัดเจน

**Trade-off:** เสีย “pure sim without deps” เล็กน้อย; ได้ single source of truth

---

### R12 — อย่าทำตอนนี้ (anti-recommendations)

| อย่า | เหตุผล |
|------|--------|
| Rewrite ทั้ง monorepo เป็น multi-package workspace ทันที | cost สูง, benefit ช้า; ทำ boundary ใน package ก่อน |
| Fork llama.cpp ตอนนี้เพื่อ buffer layer | ADR-003 ปฏิเสธไปแล้วด้วยเหตุผล ship speed; กลับไปเมื่อมี native plan ชัด |
| รวม Gradio+TUI+SPA เป็น UI เดียว | audience ต่าง; ทำให้ thin clients ต่อ API พอ |
| ใส่ MLP predictor กลับเข้า hot path | empirical: ไม่ critical ต่อ throughput บน consumer CPU |
| Big-bang ย้าย frontend ออก repo | static embed ยังเหมาะ local-first; แยกเมื่อมี remote deploy จริง |

---

## 8. ลำดับการลงมือ (ไม่ rewrite ทีเดียว)

แนะนำ **incremental slices** ที่ ship ได้ทีละชิ้น ระบบไม่พัง:

```text
Slice 0 (½–1 วัน)  — R1 Backend protocol + type fixes + tests
Slice 1 (½ วัน)    — R2 backend_type in API/stats + SPA badge + README honesty
Slice 2 (1–2 วัน)  — R3 split api_server routers (move-only)
Slice 3 (1–2 วัน)  — R4 split llama_cpp helpers
Slice 4 (½–1 วัน)  — R5 decision doc + metric demotion OR native spike charter
Slice 5 (1 วัน)    — R6 move capabilities + chat helpers
Slice 6 (1–2 วัน)  — R7 OpenAPI codegen in CI
Slice 7 (ตามความต้องการ multi-model) — R9 ports
ongoing            — R10 ทีละหน้าเมื่อแตะ feature นั้น
```

**กฎทองแต่ละ slice**

1. หนึ่งเป้าหมาย structural ต่อ PR  
2. ห้ามผสม feature ใหม่  
3. ทดสอบเดิมเขียวก่อน/หลัง  
4. อัปเดต ADR สั้น ๆ เมื่อเปลี่ยน boundary

---

## 9. สิ่งที่ทำได้ดีอยู่แล้ว

อย่า refactor ทิ้งของดีเหล่านี้:

1. **ADR-003 as-built honesty** ใน `ARCHITECTURE.md` §0 — หายากและมีค่า  
2. **`_iter_blocking` design** — แยก blocking inference ออกจาก event loop ชัด  
3. **issues/ เป็น package แยก** — แบบอย่าง feature isolation  
4. **optional deps ใน pyproject** (`server`, `llama-cpp`, `mcp`, …) — install surface ดี  
5. **frontends ส่วนใหญ่ (TUI/Gradio/SPA) ผ่าน HTTP** — หลักการถูก; ขยายให้ CLI ตาม  
6. **Usage choke-point** ใน ModelManager — observability รวมทางเดียว  
7. **Process priority etiquette** — product thinking ที่ mature สำหรับ daily-driver machine  
8. **Core modules เล็กและอ่านง่าย** (`buffer` 172 / `predictor` 122 / `prefetcher` 175) — รักษานี้ไว้ อย่ายัด logic กลับเข้า core โดยไม่จำเป็น

---

## ภาคผนวก A — Coupling sketch (ย่อ)

```
                    ┌──────── frontend (TS) ────────┐
                    │  hand types ←→ Pydantic        │
                    └───────────────┬────────────────┘
                                    │ HTTP
cli ──direct──┐                     │
              ▼                     ▼
         WeightStreamModel    api_server (god)
         LlamaServerBackend ←─ model_manager
              │                     │
              ├─ core/*        issues/, hub, mcp, …
              ├─ gguf/*
              └─ io/*
```

## ภาคผนวก B — ไฟล์ “อย่าให้โตต่อ” โดยไม่แยก

| ไฟล์ | เพดานแนะนำก่อน split |
|------|----------------------|
| `server/api_server.py` | หยุดเพิ่ม route — แยก router ก่อน |
| `backends/llama_cpp.py` | หยุดเพิ่ม chat/policy — แยก module ก่อน |
| `server/model_manager.py` | หยุดเพิ่ม compat formatting — ดึง chat policy ออก |
| `frontend/.../SettingsPage.tsx` | แยก sections เป็น components ก่อน feature ใหม่ |
| `frontend/src/styles/pages.css` | แยกต่อ page |

## ภาคผนวก C — คำศัพท์สั้น

| ศัพท์ | ความหมายในรายงานนี้ |
|-------|---------------------|
| **God module** | ไฟล์/คลาสรวมหลาย responsibility จนเป็นจุดรวมทุก change |
| **Type lie** | type annotation ไม่ตรง runtime value |
| **Hot path** | ทางที่ execute ทุก token/request |
| **Boundary erosion** | layer เริ่ม import/รู้เรื่องข้ามชั้น |
| **Demote** | ลดสถานะจาก product-critical → experimental/research |

---

*จบรายงาน — สำหรับอภิปราย priorization กับทีม ก่อนลงมือ Slice 0–1*

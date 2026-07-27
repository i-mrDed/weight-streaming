# Weight-Streaming: Full-System Architecture Plan

> **Based on:** v0.10.1 codebase — `WeightStreamModel` class, CLI, 43 passing tests  
> **Date:** 2026-07-27  
> **Scope:** API Server + 4 Frontends + Agentic IDE Vision + Marketing Site  
> **Status:** Planning phase — pending user approval before implementation

---

## Table of Contents

1. [Overall Architecture](#1-overall-architecture)
2. [API Server Design](#2-api-server-design)
3. [API Contract](#3-api-contract)
4. [Frontend: TUI (Textual)](#4-frontend-tui-textual)
5. [Frontend: Gradio Web UI](#5-frontend-gradio-web-ui)
6. [Frontend: FastAPI + SPA](#6-frontend-fastapi--spa)
7. [Frontend: Desktop GUI (PyQt6)](#7-frontend-desktop-gui-pyqt6)
8. [Presentation / Marketing Website](#8-presentation--marketing-website)
9. [Agentic IDE Roadmap](#9-agentic-ide-roadmap)
10. [Build Order Recommendation](#10-build-order-recommendation)
11. [Risk Notes & Open Decisions](#11-risk-notes--open-decisions)
12. [Summary: All Packages & Dependencies](#12-summary-all-packages--dependencies)

---

## 1. Overall Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                               FRONTENDS                                     │
│                                                                             │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────┐  ┌──────────────────┐   │
│  │   TUI    │  │  Gradio  │  │  FastAPI + SPA   │  │  Desktop GUI     │   │
│  │ (Textual)│  │ (Web UI) │  │ (Vanilla JS)     │  │ (PyQt6)          │   │
│  └────┬─────┘  └────┬─────┘  └────────┬─────────┘  └────────┬─────────┘   │
│       │             │                 │                      │             │
│       └─────────────┴─────────────────┴──────────────────────┘             │
│                                  │  HTTP/WS                                 │
└──────────────────────────────────┼─────────────────────────────────────────┘
                                   │
┌──────────────────────────────────┼─────────────────────────────────────────┐
│                     API SERVER   │   (fastapi)                              │
│                                  ▼                                          │
│  ┌────────────────────────────────────────────────────────────────────┐    │
│  │  weight_stream/server/                                              │    │
│  │                                                                    │    │
│  │  POST /v1/generate     →  ModelManager.generate()                  │    │
│  │  GET  /v1/stats        →  ModelManager.get_stats()                 │    │
│  │  GET  /v1/models       →  ModelManager.list_models()               │    │
│  │  WS   /v1/stream       →  Token-by-token streaming                 │    │
│  │  POST /v1/chat/completions → OpenAI-compatible endpoint            │    │
│  │                                                                    │    │
│  │  ┌─────────────────────────────────────────────────────────────┐   │    │
│  │  │  ModelManager                                              │   │    │
│  │  │  • Model lifecycle: load / unload / reload / list           │   │    │
│  │  │  • Multiple model instances (by model ID or path)           │   │    │
│  │  │  • Thread-safe with asyncio.Lock per model_id               │   │    │
│  │  │  • Auto-idle unload after configurable timeout              │   │    │
│  │  └─────────────────────────────────────────────────────────────┘   │    │
│  └────────────────────────────────────────────────────────────────────┘    │
└───────────────────────────────────────────────────────────────────────────┘
                                   │
┌──────────────────────────────────┼─────────────────────────────────────────┐
│                     BACKEND      │  (existing code, no changes)            │
│                                  ▼                                          │
│  ┌────────────────────────────────────────────────────────────────────┐    │
│  │  WeightStreamModel (weight_stream/backends/llama_cpp.py)           │    │
│  │  ┌──────────┐ ┌──────────────┐ ┌──────────┐ ┌────────────────┐   │    │
│  │  │ Buffer   │ │ Prefetcher   │ │Predictor │ │Page Monitor    │   │    │
│  │  │ (LRU)    │ │ (thread)     │ │(heuristic)│ │(QueryWorkingSet)│   │    │
│  │  └──────────┘ └──────────────┘ └──────────┘ └────────────────┘   │    │
│  │  ┌───────────────────────────────────────────────────────────┐   │    │
│  │  │ llama-cpp-python  (C++ inference engine, mmap'd GGUF)     │   │    │
│  │  └───────────────────────────────────────────────────────────┘   │    │
│  └────────────────────────────────────────────────────────────────────┘    │
└───────────────────────────────────────────────────────────────────────────┘
```

**Key architectural decisions:**

| Decision | Rationale |
|----------|-----------|
| **All frontends → API Server only** | Frontends NEVER import `WeightStreamModel` directly. This enforces modularity, makes the API the contract, and enables cloud deployment trivially. |
| **API Server as same-process** | For local dev: same-process (FastAPI + uvicorn in-process is simplest). Run model operations in `asyncio.to_thread()` to avoid blocking. |
| **One ModelManager, many models** | API server tracks a map of `{model_id: WeightStreamModel}`. Load/unload at runtime. Supports switching between GGUF files. |
| **No changes to existing backend** | `weight_stream/` core stays untouched. The API server is a new package `weight_stream/server/` that depends on existing public API. |

---

## 2. API Server Design

### 2.1 Package structure

```
weight_stream/server/
├── __init__.py
├── api_server.py       # FastAPI app, routes, startup/shutdown
├── model_manager.py    # Model lifecycle manager
├── schemas.py          # Pydantic request/response models
├── streaming.py        # SSE and WebSocket streaming helpers
├── openai_compat.py    # OpenAI-compatible endpoint adapter
├── config.py           # Server configuration (host, port, defaults)
└── __main__.py         # python -m weight_stream.server
```

### 2.2 ModelManager (the core abstraction)

```python
class ModelManager:
    """
    Manages multiple WeightStreamModel instances by model_id.
    
    Responsibilities:
    - Load models on demand (lazy or eager)
    - Track loaded models in a dict
    - Unload idle models after TTL
    - Provide generate(), get_stats(), close() delegation
    
    Thread safety: asyncio lock per model_id.
    """
    
    _models: dict[str, WeightStreamModel]   # model_id → instance
    _configs: dict[str, ModelConfig]        # model_id → config (for reload)
    _lock: asyncio.Lock
    _idle_timeout: float                    # seconds before unloading idle model
```

**Key behaviors:**

- `load(model_id, model_path, **kwargs)` — creates `WeightStreamModel`, stores in dict. Returns error if already loaded (or force-reload).
- `unload(model_id)` — calls `model.close()`, removes from dict.
- `reload(model_id)` — unload then load with saved config.
- `generate(model_id, prompt, **kwargs)` — delegates to model, yields token chunks for streaming.
- `get_stats(model_id)` — returns `model.get_stats()`.
- `list_models()` — returns list of `{model_id, model_path, loaded, n_experts, ...}`.
- `auto_idle_unload()` — background task unloads models not used in `idle_timeout` seconds.

### 2.3 Streaming approach

Two parallel streaming mechanisms:

| Mechanism | When to use | Implementation |
|-----------|-------------|----------------|
| **SSE (Server-Sent Events)** | Default for REST clients | `POST /v1/generate?stream=true` → `text/event-stream` |
| **WebSocket** | For IDE/agent integration | `ws://host/v1/stream` — bidirectional |

### 2.4 Server configuration

```python
SERVER_HOST = "127.0.0.1"
SERVER_PORT = 8080
DEFAULT_BUFFER_MB = 64
DEFAULT_N_CTX = 512
IDLE_UNLOAD_TIMEOUT = 300  # 5 minutes
MAX_LOADED_MODELS = 4
```

### 2.5 CLI integration

```bash
# Start API server
python -m weight_stream server --model path/to/model.gguf

# With custom host/port
python -m weight_stream server --host 0.0.0.0 --port 8080 --model model.gguf
```

### 2.6 Dependencies

```toml
[project.optional-dependencies]
server = [
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.32.0",
    "sse-starlette>=2.2.0",
    "websockets>=13.0",
]
```

---

## 3. API Contract

### 3.1 REST Endpoints

#### `POST /v1/generate`

```json
{
  "model": "default",
  "prompt": "The capital of France is",
  "max_tokens": 128,
  "temperature": 0.7,
  "top_p": 0.9,
  "stream": false
}
```

**Response (non-streaming, `stream: false`):**
```json
{
  "model": "default",
  "prompt": "The capital of France is",
  "output": " Paris. It is known for its art, fashion, and culture.",
  "tokens_generated": 10,
  "elapsed_seconds": 3.24,
  "tokens_per_second": 3.09,
  "stats": {
    "buffer": { "hit_rate": 0.0, "hot_shards": 16, "capacity_shards": 16 },
    "prefetcher": { "prefetched": 42, "queued": 3 },
    "page_cache": { "resident_ratio": 0.016, "resident_gb": 0.09, "total_gb": 5.5 },
    "model": { "path": "model.gguf", "arch": "qwen2moe", "n_experts": 60 }
  }
}
```

**Response (streaming, `stream: true`):**
```
data: {"token": " Paris", "index": 0, "done": false}
data: {"token": ".", "index": 1, "done": false}
data: {"token": " It", "index": 2, "done": false}
...
data: {"token": "", "index": 9, "done": true, "stats": {...}}
```

#### `GET /v1/stats`

Returns stats for all loaded models + server status.

#### `GET /v1/models`

```json
{
  "models": [
    {
      "id": "default",
      "path": "/models/qwen.gguf",
      "loaded": true,
      "arch": "qwen2moe",
      "n_experts": 60,
      "buffer_mb": 64,
      "last_used": "2026-07-27T12:34:56Z"
    }
  ]
}
```

#### `POST /v1/models/load`

```json
{ "model_id": "mixtral", "model_path": "/models/mixtral.gguf", "buffer_mb": 128 }
```
→ `{"status": "loaded", "model_id": "mixtral"}`

#### `POST /v1/models/unload`

```json
{ "model_id": "mixtral" }
```
→ `{"status": "unloaded", "model_id": "mixtral"}`

### 3.2 WebSocket Protocol (`ws://host/v1/stream`)

```json
// Client → Server
{ "type": "generate", "model": "default", "prompt": "Hello", "max_tokens": 100 }

// Server → Client (streaming)
{"type": "token", "text": " Hello", "index": 0}
{"type": "token", "text": " world", "index": 1}
{"type": "done", "stats": {...}}

// Server → Client (errors)
{"type": "error", "message": "Model not loaded", "code": "MODEL_NOT_FOUND"}

// Client → Server (cancel / abort)
{"type": "cancel"}
```

### 3.3 OpenAI-Compatible Endpoint

#### `POST /v1/chat/completions`

This is the critical endpoint for Agentic IDE integration. Any tool that speaks OpenAI API can connect.

**Request:**
```json
{
  "model": "default",
  "messages": [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": "What is the capital of France?"}
  ],
  "max_tokens": 100,
  "temperature": 0.7,
  "stream": false
}
```

**Response (matches OpenAI Chat Completion format):**
```json
{
  "id": "chatcmpl-7b8a9c0d1e2f",
  "object": "chat.completion",
  "created": 1722100000,
  "model": "default",
  "choices": [{
    "index": 0,
    "message": { "role": "assistant", "content": "The capital of France is Paris." },
    "finish_reason": "stop"
  }],
  "usage": { "prompt_tokens": 20, "completion_tokens": 8, "total_tokens": 28 }
}
```

> **Note:** Token counts are approximated since we don't have direct tokenizer access from Python. Acceptable for local use — documented as such.

---

## 4. Frontend: TUI (Textual)

### 4.1 Technology Choice: Textual

| Why Textual | Why not alternatives |
|-------------|---------------------|
| Native Python, async-first | `curses` too low-level |
| Hot-reloading during dev | `urwid` older, less maintained |
| Beautiful built-in widgets | |
| Cross-platform (Windows included) | |
| Rich ecosystem | |

Dependencies: `textual>=1.0.0`, `rich>=13.0.0`
Package: `pip install weight-streaming[tui]`

### 4.2 Implementation Stages

| Stage | What | Effort |
|-------|------|--------|
| 1. Basic chat UI | Connect to API server, text input, output display, token counter | 1.5 days |
| 2. Stats dashboard | Live buffer stats, hit rate, page cache chart, tok/s counter | 1 day |
| 3. Model management | List loaded models, load/unload, switch active model | 0.5 day |
| 4. Polish | Themes, keyboard shortcuts, scrollback, config file | 0.5 day |

**Total: ~3.5 days**

### 4.3 Key UX Decisions

- **Default split layout:** Left 60% = chat output, Right 40% = stats panel
- **Bottom bar:** Text input + model selector + connection status
- **Ctrl+N** = new session, **Ctrl+L** = clear, **Ctrl+D** = toggle dashboard
- **Connection indicator:** Green/gray/red dot showing API server reachability
- **Live stats:** Dashboard refreshes every 2 seconds

---

## 5. Frontend: Gradio Web UI

### 5.1 Technology Choice: Gradio 5

| Why Gradio | Why not alternatives |
|------------|---------------------|
| 10 lines = working chat UI | Streamlit requires more boilerplate for streaming |
| Built-in streaming support | Custom Flask/FastAPI SPA takes 5× longer |
| Shareable via `share=True` (LAN tunnel) | |
| Easy theming (HF theme gallery) | |

Dependencies: `gradio>=5.0.0`
Package: `pip install weight-streaming[gradio]`

### 5.2 Implementation Stages

| Stage | What | Effort |
|-------|------|--------|
| 1. Basic chat UI | Textbox + output + submit + streaming display | 0.5 day |
| 2. Stats panel | Accordion with buffer/prefetcher/page stats | 0.5 day |
| 3. Model picker | Dropdown to select, load/unload buttons | 0.5 day |
| 4. Settings | Temperature slider, max tokens, buffer size | 0.25 day |
| 5. Polish | Custom CSS theme, dark mode | 0.25 day |

**Total: ~2 days** (fastest frontend to build)

### 5.3 Key UX Decisions

- **Two-column layout:** Chat on left, controls on right
- **Stats as collapsible section** (not always visible)
- **Model picker at top** with load/unload buttons
- `gr.ChatInterface` as base, custom CSS for branding

---

## 6. Frontend: FastAPI + SPA

### 6.1 Technology Choice: Vanilla JS + Single HTML

| Why vanilla | Why not React/Vue |
|-------------|-------------------|
| Zero build step | React adds 100+ MB in node_modules |
| Fits in 1 HTML file | Overkill for a single-page chat UI |
| Immediate deployment | Requires npm install, build, serve |
| Easy to embed in Python package | |

**Expansion path:** Vanilla JS → Alpine.js + htmx → Preact → React (only if needed)

### 6.2 Implementation Stages

| Stage | What | Effort |
|-------|------|--------|
| 1. Static file server | FastAPI serves `index.html` from `server/static/` | 0.25 day |
| 2. Chat UI | HTML form, JS fetch to `/v1/generate`, streaming via fetch | 1 day |
| 3. Model management | Load/unload form, model list display | 0.5 day |
| 4. Stats dashboard | Poll `/v1/stats`, render as styled cards | 0.5 day |
| 5. Polish | Dark/light toggle, responsive, mobile-friendly | 0.5 day |

**Total: ~2.75 days**

### 6.3 Key UX Decisions

- **Single HTML file** approach (everything inline) for Phase 1
- **Dark mode default** (terminal aesthetic)
- **Streaming via fetch + async iterator** (POST compatible)
- **Stats as a tab** — toggle between "Chat" and "Dashboard" views
- **Responsive:** works on mobile

---

## 7. Frontend: Desktop GUI (PyQt6)

### 7.1 Technology Choice: PyQt6

| Why PyQt6 | Why not alternatives |
|-----------|---------------------|
| Native widgets on Windows | `tkinter` is ugly and limited |
| Rich widget set (tables, trees, tabs) | `wxPython` worse docs |
| QSS styling (like CSS) | `Electron` is 100+ MB for a chat UI |
| System tray support | |

Dependencies: `PyQt6>=6.7.0`
Package: `pip install weight-streaming[gui]`

### 7.2 Implementation Stages

| Stage | What | Effort |
|-------|------|--------|
| 1. Main window + connection | Window, menu bar, API client, status bar | 1 day |
| 2. Chat view | Output display, input box, send button, streaming | 1.5 days |
| 3. Stats panel | Buffer stats table, hit rate progress bar, labels | 1 day |
| 4. Model manager | Model list, load/unload dialog | 1 day |
| 5. Settings dialog | Host/port, buffer, context window, themes | 0.5 day |
| 6. Polish | System tray, minimize to tray, save/restore window state | 0.5 day |

**Total: ~5.5 days** (heaviest frontend)

### 7.3 Key UX Decisions

- **OS-native look:** Windows dark title bar + QDarkStyle
- **Tab layout:** Chat | Stats | Models (QTabWidget)
- **System tray:** Background operation, quick access
- **Connection status:** Green/yellow/red LED in status bar
- **Packaging:** `pyinstaller --onefile` for standalone .exe distribution

---

## 8. Presentation / Marketing Website

### 8.1 Architecture

**Offline-first static site.** Pure HTML/CSS/JS. No build step. No dependencies.

```
website/
├── index.html              # Landing page (hero + features + CTA)
├── pages/
│   ├── features.html       # Deep feature explanations
│   ├── architecture.html   # Architecture diagrams + explanation
│   ├── benchmarks.html     # Performance numbers + charts
│   └── api-docs.html       # API reference
├── assets/
│   ├── css/
│   │   ├── style.css       # Design system (tokens, typography, spacing)
│   │   └── dark.css        # Dark theme
│   ├── js/
│   │   ├── main.js         # Navigation, theme toggle, smooth scroll
│   │   └── charts.js       # Benchmark chart rendering (canvas-based)
│   ├── images/
│   │   ├── hero-bg.svg
│   │   ├── architecture.svg
│   │   └── logo.svg
│   └── data/
│       └── benchmarks.json # Static benchmark data
└── README.md               # How to serve locally
```

### 8.2 Pages & Content

| Page | Content | Priority |
|------|---------|----------|
| **index.html** | Hero: "Run LLMs larger than your RAM." Features grid (4 cards). Architecture preview. Install command. CTA. | 🔴 P0 |
| **features.html** | How weight streaming works (3-step). Comparison table. Supported models. Technical highlights. | 🔴 P1 |
| **architecture.html** | Full architecture diagram (SVG). Component descriptions. Data flow. | 🟡 P2 |
| **benchmarks.html** | Interactive charts. Throughput comparison. Table: Models tested, hardware, results. | 🟡 P2 |
| **api-docs.html** | Endpoints table. Request/response examples. WebSocket protocol. OpenAI compatibility. Code examples (Python, curl, JS). | 🔴 P1 |

### 8.3 Design System

Dark mode first, purple-teal color palette, glassmorphism cards, animated background.

### 8.4 Implementation Stages

| Stage | What | Effort |
|-------|------|--------|
| 1. Design system | CSS tokens, typography, colors, layout | 0.5 day |
| 2. Landing page | Hero, features grid, CTA, footer | 1 day |
| 3. Features page | Deep explanations, comparison table | 0.5 day |
| 4. API docs page | Endpoint reference, code examples | 1 day |
| 5. Architecture page | SVG diagram, component descriptions | 0.5 day |
| 6. Benchmarks page | Charts from static JSON data | 1 day |
| 7. Polish | Responsive, light mode, animations | 0.5 day |

**Total: ~5 days**

---

## 9. Agentic IDE Roadmap

### Phase 1: Local API Server with OpenAI-Compatible Endpoints (Now)

**What:** The API server, specifically `POST /v1/chat/completions`.

**How IDEs connect out of the box:**

| IDE/Tool | How to connect |
|----------|---------------|
| **VS Code (Continue.dev)** | `"models": [{"provider": "openai", "apiBase": "http://localhost:8080/v1"}]` |
| **Cline / Cursor** | `export OPENAI_BASE_URL=http://localhost:8080/v1` |
| **OpenAI Python SDK** | `client = OpenAI(base_url="http://localhost:8080/v1", api_key="skip")` |
| **LangChain / LlamaIndex** | `ChatOpenAI(model="default", openai_api_base="http://localhost:8080/v1")` |

**Effort:** Included in API Server build (~3 days).

### Phase 2: VS Code Extension (After API is stable)

```
VS Code Extension (TypeScript)
├── extension.ts          # Activation, commands
├── serverManager.ts      # Auto-start/stop/reconnect to weight-streaming server
├── inlineCompletion.ts   # Ghost text provider
├── chatPanel.ts          # Webview-based chat
├── statsProvider.ts      # Tree view for model stats
└── treeView/
    └── StatsTreeProvider.ts
```

**Effort:** ~5 days for MVP.

### Phase 3: Cloud API Deployment (Medium-term)

Cloud deployment of the API server. Options: Render, Fly.io, Azure Container Apps.

> **Note:** Cloud contradicts the core value prop (run on local hardware). Consider as "team access to a shared beefy machine," not a GPU cloud replacement.

### Phase 4: Standalone Agentic IDE (Long-term)

**Vision:** A full IDE (like Cursor/Windsurf) with weight-streaming as backend.

```
┌────────────────────────────────────────────────────────┐
│  Weight-Streaming Agentic IDE                          │
│  ├── Monaco Editor                                     │
│  ├── Agent Loop (ReAct + tool-calling)                 │
│  ├── Terminal Emulator (xterm.js)                      │
│  ├── File Explorer + Git integration                   │
│  └── Backend: weight-streaming API Server (local)      │
│      or any OpenAI-compatible provider                 │
└────────────────────────────────────────────────────────┘
```

**Effort estimation:** ~3-6 months for working MVP.

---

## 10. Build Order Recommendation

### Priority Matrix

| Component | Effort | Impact | Dependency | Priority |
|-----------|--------|--------|------------|----------|
| **API Server** | 3 days | 🔴 Critical | None | **1st** |
| **Marketing Site** | 5 days | 🟢 Medium | None | **Parallel** |
| **Gradio Web UI** | 2 days | 🟡 High | API Server | **2nd** |
| **TUI (Textual)** | 3.5 days | 🟡 High | API Server | **3rd** |
| **SPA** | 2.75 days | 🟡 High | API Server | **4th** |
| **Desktop GUI** | 5.5 days | 🟢 Medium | API Server | **5th** |
| **VS Code Extension** | 5 days | 🟢 Medium | API Server | **6th** |

### Timeline

```
Week 1:  [API Server] ──────────── 3 days
         [Marketing Site] ───────── 5 days (parallel, no dep)

Week 2:  [Gradio Web UI] ────────── 2 days
         [TUI] ──────────────────── starts 3.5 days

Week 3:  [SPA] ──────────────────── 2.75 days

Week 4:  [Desktop GUI] ──────────── 5.5 days

Week 5:  [VS Code Extension] ────── 5 days
```

---

## 11. Risk Notes & Open Decisions

### Risks & Mitigations

| Risk | Impact | Likelihood | Mitigation |
|------|--------|-----------|------------|
| **API server blocks during generation** | Frontends freeze | High | Use `asyncio.to_thread()` for model operations |
| **WeightStreamModel not thread-safe** | Race conditions | Medium | `asyncio.Lock` per model_id |
| **Multiple simultaneous requests** | Conflicts | Medium | Queue with max depth 3, or return 503 if busy |
| **WebSocket disconnect mid-generation** | Stale generation | Medium | Track connections, cancel on disconnect |
| **Textual TUI on Windows PowerShell** | Rendering issues | Medium | Recommend Windows Terminal |
| **Gradio share=True security** | Exposes local inference | Low | Default: share=False, add --share flag with warning |

### Open Decisions (need user input)

1. **Same-process or subprocess for API Server + Model?**
   - *Recommendation:* Same-process with `asyncio.to_thread()`. Subprocess adds IPC complexity that isn't justified yet.

2. **Queue or reject concurrent requests to one model?**
   - *Recommendation:* Queue max 3, return 503 if full. Simple for Phase 1.

3. **Where to put the `server/` package?**
   - *Recommendation:* `weight_stream/server/` inside existing package. Same versioning.

4. **Website: same repo or separate?**
   - *Recommendation:* `website/` at repo root. Can be deployed independently.

5. **SPA: Vanilla JS now or framework from start?**
   - *Recommendation:* Vanilla JS in single HTML file. No build step. Migrate to Alpine.js if needed.

---

## 12. Summary: All Packages & Dependencies

```
weight-streaming v0.11.0+  (current: 0.10.1)
│
├── base package (no changes)
│   ├── backends/
│   ├── core/
│   ├── gguf/
│   └── io/
│
├── [server] extra: weight_stream/server/
│   └── fastapi, uvicorn, sse-starlette, websockets
│
├── [tui] extra: tui/
│   └── textual, rich
│
├── [gradio] extra: ui/gradio_app.py
│   └── gradio
│
├── [gui] extra: gui/
│   └── PyQt6
│
├── website/  (static files, no pip install)
│   └── index.html + assets/
│
└── [all] extra: installs everything
```

### pyproject.toml additions

```toml
[project.optional-dependencies]
server = [
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.32.0",
    "sse-starlette>=2.2.0",
    "websockets>=13.0",
]
tui = ["textual>=1.0.0", "rich>=13.0.0"]
gradio = ["gradio>=5.0.0"]
gui = ["PyQt6>=6.7.0"]
all = [
    "weight-streaming[server,tui,gradio,gui]",
    "weight-streaming[llama-cpp]",
]
```

---

> **Status:** Pending user approval before implementation begins.  
> **Last updated:** 2026-07-27

# Product Roadmap — Speculative Weight Streaming

> **เป้าหมาย:** Product ที่ให้任何人都สามารถรันโมเดล LLM ขนาด >RAM ของตัวเองได้
> โดยใช้ NVMe เป็น extension of RAM

---

## Phase 4 (ปัจุบัน, 2026-08-10): Constraint-Bound Optimization

**ข้อจำกัดคงที่ (เพิ่ม HW ไม่ได้):** i9-9900KF + RTX 3060 12 GB + 64 GB RAM + Windows

**เป้าหมายซื่อตรง:** DS V4 Flash 104 GB 1.5–1.9 → **2.5–4 tok/s** (ใช้แบบอดทนได้) ด้วย software-only · K3 2.8T ตั้งความคาดหวังไว้ที่ 0.3–0.5 tok/s (รันได้พิสูจน์แนวคิด — ยังไม่ใช่ใช้ทำงานจริง)

> อ้างอิง: [EXP-014](research/experiments/EXP-014-2026-08-consumer-moe-landscape/) — landscape 2026-08 + pulsar deep-dive (engine ที่พิสูจน์ thesis เรา: GLM-5.2 743B @ 2.7 tok/s บน 2×16GB GPU)

| # | โครงการ | ผลที่คาด | สถานะ |
|---|---------|---------|-------|
| 1 | ~~Expert popularity census → auto `n-cpu-moe` tiering~~ | ❌ ปิดแล้ว (EXP-016): ไม่มี hot layer — traffic flat ข้ามทุก layer, กำไรขึ้นกับ bytes บน GPU ล้วนๆ → `--n-cpu-moe 0` optimal อยู่แล้ว | ❌ No additional win |
| 2 | CPU lane ตาม host-cache residency | เลือก CPU/GPU ต่อ expert ตาม residency จริง | 📋 วางแผน |
| 3 | วัด IQ2_XXS (`--variant iq2m`) บน DS V4 Flash | bytes/token ↓ → resident ↑ → tok/s ↑ | 🟢 script พร้อมแล้ว |
| 4 | ~~Speculative decoding บน GPU backend~~ | ❌ ปิดแล้ว: EXP-015 MTP head ช้าลง 11–18% (ไฟล์ MTP ใหญ่เกิน VRAM 12 GB + draft step รัน expert เต็ม) | ❌ Dead end |
| 5 | วินัย benchmark (census + warm-run + value-aware flags) | ตัวเลขเชื่อถือได้ทุกตัว | 🔄 ทำอยู่แล้ว |

---

## Phase 3c: MVP — `weight-streaming` Python Library

**เป้าหมาย:** `pip install weight-streaming` แล้วใช้ได้เลย

### Architecture (abstraction-first, ไม่ lock-in กับ backend ใด)

```
User Code
    |
weight-streaming (Python package)
    |
    ├── core/
    │   ├── buffer.py      # LRU buffer (64MB default, shard-based)
    │   ├── prefetcher.py  # Predict + prefetch (PrefetchVirtualMemory)
    │   └── predictor.py   # Heuristic predictor (frequency + temporal)
    |
    ├── backends/          # Abstraction layer
    │   ├── _base.py       # Backend interface (ABC)
    │   ├── llama_cpp.py   # llama-cpp-python adapter
    │   └── gguf.py        # GGUF metadata reader
    |
    ├── io/
    │   └── win_iocp.py    # Windows IOCP async I/O
    |
    └── cli/
        └── main.py        # python -m weight_stream ...
```

### Key Design Decisions (from research findings)

| Finding | Product Decision |
|---------|-----------------|
| ~92% compute-bound | Buffer = RAM reduction. Not throughput accelerator. |
| LRU 64MB = 93.8% hit | Default buffer = 64MB, LRU eviction. No MLP predictor needed. |
| Predictor not critical | Heuristic predictor (frequency + temporal). Cold start only. |
| mmap is free streaming | Use mmap for weight access. Our role = smart prefetching. |
| K3 = 896 experts, MXFP4 | Shard = 4MB expert. 896 shards tracked by LRU. |

### Implementation Plan

| Step | Task | Files | Effort |
|------|------|-------|--------|
| 0 | ADR-003 + update ARCHITECTURE.md | `docs/` | ~30min |
| 1 | Create package structure | `weight_stream/` skeleton | ~15min |
| 2 | Implement LRU buffer (real I/O) | `core/buffer.py` | ~1hr |
| 3 | Implement GGUF reader + prefetcher | `core/prefetcher.py`, `backends/gguf.py` | ~1hr |
| 4 | Implement llama-cpp-python adapter | `backends/llama_cpp.py` | ~1hr |
| 5 | Implement Windows IOCP I/O | `io/win_iocp.py` | ~1hr |
| 6 | CLI + demo script | `cli/main.py` | ~30min |
| 7 | Validate: Qwen benchmark → 1.22 t/s | `scripts/validate.py` | ~30min |
| 8 | Package: PyPI + GitHub | `pyproject.toml`, `README.md` | ~30min |

### Validation Criteria (MVP)

```
Model: Qwen1.5-MoE-A2.7B (GGUF Q2_K, 5.88 GB)
Buffer: 64MB LRU
Expected: 1.22 tok/s (matches EXP-004 prediction)
Compare: full-RAM baseline = 1.23 tok/s
Gap: <1% throughput loss for 99.5% RAM savings
```

---

## Phase 6: Production Hardening — Full End-to-End Readiness

> **เป้าหมาย:** Product พร้อมใช้งานจริง — security, reliability, observability, documentation ครบ

### Scope (8 dimensions)

| # | Dimension | Detail | Files Impacted |
|---|-----------|--------|----------------|
| 1 | **Security** | Scan git history for secrets, safe mmap flags, credential hygiene, path injection prevention | All (audit), .git (cleanup) |
| 2 | **Architecture** | Abstract backend interface (`_base.py`), clean module boundaries, consistent API | `backends/_base.py` (new), `backends/llama_cpp.py` |
| 3 | **Error Handling** | Custom error types, graceful degradation, cleanup on all paths, context manager contracts | `core/exceptions.py` (new), all modules |
| 4 | **Logging** | Structured logging, correct levels, performance telemetry | `io/logging.py`? All modules |
| 5 | **CLI** | Help text, progress bars, pretty tables, actionable error messages | `cli/main.py` |
| 6 | **Testing** | Integration tests, edge cases (corrupt file, OOM), stress (repeated cycles) | `tests/test_integration.py`, `tests/test_edge_cases.py` |
| 7 | **Documentation** | README.md, API reference, inline docstrings, usage examples | `README.md` (new), all modules |
| 8 | **Packaging** | pyproject.toml review, classifiers, PyPI readiness | `pyproject.toml` |

### Implementation Plan

| Step | Task | Effort |
|------|------|--------|
| 0 | Define Phase 6 in roadmap | ~15min |
| 1 | Security: scan + fix secrets, safe mmap | ~30min |
| 2 | Architecture: `_base.py` + interface cleanup | ~45min |
| 3 | Error handling: exceptions + graceful paths | ~45min |
| 4 | Logging: overhaul | ~30min |
| 5 | CLI: polish | ~30min |
| 6 | Testing: integration + edge cases | ~1hr |
| 7 | Docs: README + docstrings | ~1hr |
| 8 | Packaging: pyproject.toml | ~15min |
| 9 | Final verification: all tests pass, clean git | ~15min |

### Exit Criteria

```
✅ No secrets/tokens in git history or codebase
✅ All modules have clean error handling (no bare except:)
✅ `python -m weight_stream --help` shows clear usage
✅ All 43+ tests pass
✅ README.md documents install, usage, API
✅ pyproject.toml ready for PyPI
✅ git status clean, no untracked artifacts
✅ 4 frontends complete (SPA, Gradio, TUI, CLI)
✅ API Server with REST + WS endpoints
✅ OpenAI-compatible endpoint (IDE integration)
✅ Anthropic-compatible endpoint (Claude Code)
✅ Marketing website (5 pages, offline-first)
✅ Port 8765 verified conflict-free
```

**Status: ✅ Feature scope delivered; SPA streaming reliability validated on a real model (updated 2026-07-30)**

The platform endpoints and frontends exist. Real SPA use exposed reliability gaps (default CPU saturation, destructive idle unloading, template fidelity, event-loop blocking during stream, incomplete wrapper telemetry) — all five are now fixed and validated end-to-end on `Qwen1.5-MoE-A2.7B` Q2_K (2026-07-29, raw data in `docs/verification/`). Contract and acceptance criteria: `docs/HANDOFF_STREAMING_RELIABILITY.md` (marked COMPLETED).

---

## Post-Phase 6: SPA Streaming Reliability

| Status | Work | Validation required |
|--------|------|---------------------|
| ✅ | Propagate `ServerConfig` to `ModelManager`; cap default threads at half logical cores | SPA-loaded model receives requested thread count |
| ✅ | Disable local idle unloading by default; add explicit timeout option | Model remains loaded during an idle SPA session |
| ✅ | Use native GGUF chat templates and forward `top_p` from SPA | Qwen/Llama responses contain no leaked template tokens |
| ✅ | Move blocking generation iterator to a worker thread and batch browser token rendering | `/health` avg 5.7 ms / max 23.3 ms during 17.9 tok/s generation (58 polls); SPA paints once per animation frame |
| ✅ | Route SPA streaming through a public `WeightStreamModel` wrapper | `stream_chat()` wrapper: real generation stats + OS page-cache sampling; prefetch accuracy shows `n/a` until real routing evidence exists |
| ✅ | Run before/after performance and quality tests on a real GGUF | Qwen1.5-MoE Q2_K: 17.9 tok/s, 4.6% residency during generation, cancel in 0.73 s — `docs/verification/items_45_2026-07-29_raw.txt` (no "before" baseline: old code already replaced) |

Implementation contract and acceptance criteria: `docs/HANDOFF_STREAMING_RELIABILITY.md`.

---

## Phase 3d: Cross-Platform I/O

| Feature | Detail |
|---------|--------|
| Windows | IOCP (completed) |
| Linux | io_uring |
| macOS | GCD / POSIX aio |

---

## Phase 3e: K3 Native Support

| Feature | Detail |
|---------|--------|
| MXFP4 dequant | Custom dequant kernel |
| 896-expert routing | GGUF metadata mapping |
| KDA Quantile Balancing | Predictor integration |

---

## Phase 4: Distribution

| Platform | Detail |
|----------|--------|
| PyPI | `pip install weight-streaming` |
| GitHub | MIT license, CI/CD, docs |
| Commercial | Enterprise: custom quant, support, private deployment |

---

## Milestone Timeline

```
Phase 3c (MVP)     ─── ████████████████  →  ปลาย July 2026
Phase 3d (I/O)     ───       ████████████████  →  Mid Aug 2026
Phase 3e (K3)      ───             ████████████  →  Sep 2026
Phase 4 (Release)  ───                   ████████  →  Oct 2026
```

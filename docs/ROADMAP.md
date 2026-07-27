# Product Roadmap — Speculative Weight Streaming

> **เป้าหมาย:** Product ที่ให้任何人都สามารถรันโมเดล LLM ขนาด >RAM ของตัวเองได้
> โดยใช้ NVMe เป็น extension of RAM

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
☐ No secrets/tokens in git history or codebase
☐ All modules have clean error handling (no bare except:)
☐ `python -m weight_stream --help` shows clear usage
☐ All 22+ tests pass
☐ README.md documents install, usage, API
☐ pyproject.toml ready for PyPI
☐ git status clean, no untracked artifacts
```

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

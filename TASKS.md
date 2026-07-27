# Task Board — Speculative Weight Streaming

> **用途:** ติดตามงานค้าง งานกำลังทำ งานเสร็จ — ทั้งระยะสั้นและระยะยาว  
> **รูปแบบ:** 📥 Backlog → 🔄 In Progress → ✅ Done  
> **ต้องทำ:** อัปเดตทุกครั้งที่เริ่ม/จบ task

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
| ⬜ | Update ARCHITECTURE.md with EXP-002 findings | 🟡 | LFU default, remove priority boost, reduce prediction emphasis |
| ⬜ | Select small MoE model for PoC | 🟡 | Mixtral? Qwen MoE? |
| ✅ | Estimate real compute time for K3 on consumer HW | 🔴 | Qwen benchmark → K3: 815ms compute, ~92% compute-bound |
| ✅ | Update simulator with real K3 timing (815ms compute) | 🔴 | Done (config.py timing) |
| ✅ | Phase 3b: Re-run EXP-001/002/003 with real timing | 🔴 | LRU wins, predictor not critical |
| ⬜ | Update ARCHITECTURE.md with real HW findings | 🟡 | ADR-003 needed |
| ⬜ | Build streaming buffer abstraction prototype | 🔴 | Abstraction-first, llama.cpp as backend |
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

# Changelog — Speculative Weight Streaming

> รูปแบบ: [Semantic Versioning](https://semver.org/)  
> ทุกการเปลี่ยนแปลงต้องบันทึกในไฟล์นี้

---

## [0.10.0] - 2026-07-27

### 🔬 Phase 4a: GGUF Parser — Expert-Aware Tensor Mapping

- **New Module**: `weight_stream/gguf/` — wraps official `gguf` library with expert-aware features
- **GGUFParser**: Parses GGUF metadata + maps tensor names → file offsets
- **Expert-aware API**:
  - `get_expert_map()` → `{layer_id: {expert_idx: [ExpertRange(gate, up, down)]}}`
  - `get_expert_tensors()` → list of 72 expert tensors (24 layers × 3 projections)
  - `get_tensor(name)` → file offset + size + quantization type
- **Expert size analysis (Qwen1.5-MoE-A2.7B)**:
  - Per-expert: down=1.43MB, gate=0.77MB, up=0.77MB (total ~2.9MB/expert)
  - Layer-0 prefetch: loads all 60 experts on init (cold start acceleration)
- **Backend update**: `WeightStreamModel` uses GGUF parser + prefetches layer experts during generation
- **Prefetcher update**: New `prefetch_experts()` and `prefetch_token_experts()` methods
- **Tests**: 9 new GGUF parser tests (22 total, all passing)

#### ไฟล์ที่สร้าง/แก้ไข
- `weight_stream/gguf/__init__.py` — new module
- `weight_stream/gguf/parser.py` — GGUF parser wrapper (135 lines)
- `weight_stream/backends/llama_cpp.py` — GGUF integration + expert prefetch + page monitor init
- `weight_stream/core/prefetcher.py` — expert-aware prefetch methods + buffer tracking
- `tests/test_gguf.py` — 9 tests
- `CHANGELOG.md` — อัปเดต

---

## [0.10.1] - 2026-07-27

### 🔬 Phase 4b: Windows Page Cache Monitor + Buffer Integration

- **New Module**: `weight_stream/io/win_perf.py` — WindowsPageMonitor using `QueryWorkingSetEx`
  - Samples page cache residency via `QueryWorkingSetEx` API
  - Reports resident ratio: how much of the mmap'd file is in physical RAM
  - Page size detection via `GetSystemInfo`
- **Backend fix**: `WeightStreamModel` now initializes page monitor on startup
  - Uses numpy to extract mmap virtual address for `QueryWorkingSetEx`
  - Monitor is optional — gracefully reports `None` on failure
  - Samples page cache every 5 tokens during generation
- **Prefetcher fix**: `prefetch_experts()` now tracks prefetched shards in the buffer LRU
  - Previously, expert prefetch used direct mmap reads without buffer tracking
  - Now shards are properly tracked: buffer shows 66 prefetches, 16 entries after 10-token gen
- **Cleanup fix**: `WeightStreamModel.close()` releases numpy buffer before closing mmap
- **Benchmark validation** (Qwen1.5-MoE-A2.7B, 5.5GB):
  - Page monitor confirms: 0% → 1.6% resident after cold generation
  - With/without prefetch: within noise (±3%) for small model
  - Prediction: prefetch benefit scales with model size (>68GB needed for visible effect)
- **Tests**: 22/22 passing (no new tests needed — monitor is optional and graceful)

#### ไฟล์ที่สร้าง/แก้ไข
- `weight_stream/io/win_perf.py` — WindowsPageMonitor (new, 189 lines)
- `weight_stream/backends/llama_cpp.py` — page monitor init + close fix
- `weight_stream/core/prefetcher.py` — buffer tracking in prefetch_experts
- `CHANGELOG.md` — อัปเดต

---

## [0.9.0] - 2026-07-27

### 🏗️ Phase 3c: weight-streaming Product (MVP)

- **New Package**: `weight_stream/` — 8 modules, pip-installable product
- **core/buffer.py**: LRU StreamingBuffer — zero-copy mmap, hot-set tracker, hit/miss stats
- **core/predictor.py**: HeuristicPredictor — sequential pattern + co-occurrence, no MLP
- **core/prefetcher.py**: Background thread — speculative prefetch during compute time
- **backends/llama_cpp.py**: WeightStreamModel — wraps llama-cpp-python with mmap overlay
- **cli/main.py**: 3 commands (`run`, `stats`, `benchmark`) + JSON output
- **tests/test_buffer.py**: 13 unit tests — LRU eviction, prefetch, hit rate, zero-copy
- **ADR-003**: Product architecture decision (LRU-only, 64MB, heuristic, mmap-based)
- **End-to-end validation**: Qwen1.5-MoE-A2.7B generates at 13.43 tok/s

#### ไฟล์ที่สร้าง/แก้ไข
- `weight_stream/` — new package (11 files)
- `weight_stream/__init__.py` — public API
- `weight_stream/__main__.py` — `python -m` entry
- `weight_stream/core/buffer.py` — LRU buffer tracker
- `weight_stream/core/predictor.py` — heuristic predictor
- `weight_stream/core/prefetcher.py` — background prefetch
- `weight_stream/backends/llama_cpp.py` — llama-cpp-python adapter
- `weight_stream/cli/main.py` — 3 CLI commands
- `weight_stream/io/__init__.py` — I/O abstraction stub
- `tests/test_buffer.py` — 13 unit tests
- `pyproject.toml` — package config
- `docs/DECISIONS.md` — ADR-003 added
- `SESSION_LOG.md` — เพิ่ม S008
- `CHANGELOG.md` — อัปเดต

---

## [0.5.0] - 2026-07-27

### 🧪 Phase 3a: Prototype Simulator

- สร้าง Python simulator framework ครบ 5 modules:
  - `access_pattern.py` — synthetic K3 workload generator (Zipf + temporal)
  - `buffer.py` — cache policy simulation (LRU, LFU, LRU+priority)
  - `predictor.py` — perfect + heuristic prediction models
  - `timing.py` — NVMe I/O + compute timing model
  - `run.py` — main simulation runner + sweeps
- EXP-001: Buffer size sweep (5 sizes × 3 policies) → **LFU 512 MB = 78.2% hit rate**
- EXP-003: Timing analysis → **76.7% overlap efficiency, 2.74 tok/s**
- Findings ที่กระทบ design:
  - ต้องเพิ่ม buffer default จาก 256 MB → **512 MB**
  - เปลี่ยน eviction policy จาก LRU+priority → **LFU**
  - Priority boost ปิด จนกว่า predictor accuracy >30%
  - Predictor accuracy = leverage ที่ใหญ่ที่สุดสำหรับ performance improvement

#### ไฟล์ที่สร้าง/แก้ไข
- `simulator/README.md` — document
- `simulator/config.py` — config dataclasses
- `simulator/access_pattern.py` — workload generator
- `simulator/buffer.py` — buffer simulation
- `simulator/predictor.py` — predictor models
- `simulator/timing.py` — I/O + compute timing
- `simulator/run.py` — main runner
- `research/experiments/EXP-001-buffer-sim/` — setup, results, analysis
- `research/experiments/EXP-002-predictor-sim/` — partial setup
- `research/experiments/EXP-003-timing-sim/` — setup, analysis
- `research/experiments/index.md` — อัปเดต
- `TASKS.md` — อัปเดต
- `SESSION_LOG.md` — เพิ่ม S004

---

## [0.6.0] - 2026-07-27

### 🔬 EXP-002: Predictor Accuracy Sweep

- **Key Findings (เปลี่ยน Architecture Design อย่างมีนัยสำคัญ):**
  - LFU hit rate = 76.2% flat ทุกระดับ accuracy → LFU ไม่ใช้ prediction
  - LRU+priority hit rate แย่ลงเมื่อ accuracy สูงขึ้น → "priority clogging" (29.9% → 15.5%)
  - Throughput flat = 2.73 t/s → compute (350ms/token) ครอบงำ I/O
  - Overlap ดีขึ้น 7.6x (30.9ms → 233.8ms) แต่ไม่ช่วย throughput
- **Design Updates:**
  - predictor accuracy ไม่ critical — heuristic ก็พอ
  - priority boost → OFF for LFU
  - LFU → default eviction policy
  - Weight streaming ≈ RAM reduction tool ไม่ใช่ throughput accelerator
- **New Simulator Capabilities:**
  - shared_experts_per_token mode (K3 realistic, 72/80 layers identical)
  - simulated_accuracy mode (inject controlled prediction errors)
  - timing predictor_confidence affects overlap efficiency
  - sweep-accuracy mode (9 accuracies x 2 policies)

#### ไฟล์ที่สร้าง/แก้ไข
- `simulator/config.py` — shared_experts_per_token, accuracy_level, n_predict=64
- `simulator/access_pattern.py` — shared mode + inter_layer_similarity
- `simulator/predictor.py` — simulated_accuracy predictor
- `simulator/timing.py` — overlap_efficiency = confidence
- `simulator/run.py` — sweep-accuracy
- `research/experiments/EXP-002-predictor-sim/results.md`
- `research/experiments/EXP-002-predictor-sim/analysis.md`
- `research/experiments/index.md` — อัปเดต
- `TASKS.md` — อัปเดต
- `SESSION_LOG.md` — เพิ่ม S005
- `CHANGELOG.md` — อัปเดต

---

## [0.7.0] - 2026-07-27

### 💻 Phase 3b: Real Hardware Benchmark (EXP-004)

- **Key Finding: SYSTEM IS I/O-BOUND (flips previous conclusions)**
  - Qwen1.5-MoE-A2.7B benchmark: 44ms/token, 22.7 tok/s (CPU, 2.7B active params)
  - K3 scaling: estimated 815ms/token compute vs 1786ms NVMe full load
  - **NVMe I/O IS the bottleneck** — buffer and predictor now CRITICAL for throughput
- **Simulator Timing Update:**
  - compute_time_per_token_us: 350,000 → **815,000** (2.3x increase)
  - Bottleneck: compute-bound → **I/O-bound**
- **Design Reversal (based on real data vs simulation):**
  - EXP-002 said predictor doesn't matter — WRONG for real hardware
  - EXP-001/002 conclusions only valid for compute-bound regime
  - I/O-bound regime: predictor accuracy, buffer hit rate, priority boost ALL matter

#### ไฟล์ที่สร้าง/แก้ไข
- `research/models/Qwen1.5-MoE-A2.7B_Q2_k.gguf` — downloaded model (5.88 GB)
- `research/experiments/EXP-004-benchmark/setup.md`
- `research/experiments/EXP-004-benchmark/results.md`
- `research/experiments/EXP-004-benchmark/analysis.md`
- `research/experiments/EXP-004-benchmark/results.json`
- `research/experiments/index.md` — อัปเดต
- `TASKS.md` — อัปเดต
- `SESSION_LOG.md` — เพิ่ม S006
- `CHANGELOG.md` — อัปเดต

---

## [0.8.0] - 2026-07-27

### 🔄 Simulator Update + Re-run (EXP-001/002 v2 with Real Timing)

- **Updated `config.py` timing**: `compute_time_per_token_us`: 350,000 → **815,000** (from EXP-004 real HW benchmark)
- **Re-run EXP-001 (buffer sweep): LRU beats LFU** for shared MoE access pattern
  - LRU 64 MB → 93.8% hit rate (vs LFU 27.2% at same size!)
  - LRU 512 MB → 98.9% hit rate, 1ms stall, 1.23 t/s
  - Shared access pattern (72/80 identical layers) creates extreme temporal locality → LRU dominates
- **Re-run EXP-002 (accuracy sweep):** conclusions unchanged — LFU flat, LRU+P clogging
- **Definitive Bottleneck Analysis:**
  - Compute: 815ms/token (92% of total time)
  - I/O stall range: 0-67ms (0-8% of total time)
  - **System is ~92% compute-bound** → buffer enables inference, not throughput
- **Design Corrections (vs v0.7.0 I/O-BOUND claim):**
  - v0.7.0 said "I/O-BOUND" — CORRECTED: system is compute-bound
  - Initial NVMe estimate (1786ms) was misleading — real I/O is only 67ms stall
  - Predictor/buffer/priority boost do NOT critically affect throughput
  - Their real value: enabling 1.4TB model on 64MB RAM

#### ไฟล์ที่สร้าง/แก้ไข
- `simulator/config.py` — timing 815000us (from EXP-004)
- `simulator/run.py` — sweep-buffer now shows t/s + stall
- `research/experiments/index.md` — อัปเดต v2 findings
- `TASKS.md` — อัปเดต
- `SESSION_LOG.md` — เพิ่ม S007
- `CHANGELOG.md` — อัปเดต

---

### 🏗️ Phase 2: Architecture Design Complete

- ออกแบบระบบ Speculative Weight Streaming ทั้ง 6 components + interface contracts
- สร้าง `docs/ARCHITECTURE.md` — blueprint หลักของระบบ (286 บรรทัด)

#### Components ที่ออกแบบ

| Component | Design Decision | Key Spec |
|-----------|----------------|----------|
| **NVMe Data Layout** | Shard-based, popularity sorted, O(1) index | 4 MB shard, 3 regions (shared/routed/KV) |
| **Weight Predictor** | MLP (PreScope-style, 2-layer, 2M params) | Input 128-256 → Output 896, ~8 MB |
| **Pre-fetch Scheduler** | Priority queue + I/O batching + io_uring/IOCP | MAX_BATCH 64 MB, 3 priority levels |
| **Streaming Buffer** | LRU + priority eviction, 256 MB default | ~64 shards (K3), cold start strategy |
| **Execution Engine** | BufferReader + MmapFallback + ComputeOrch | Framework-agnostic interface |
| **Abstraction Layer** | Plugin architecture | MoE / Dense / Hybrid polymorphism |

#### ไฟล์ที่สร้าง/แก้ไข
- `docs/ARCHITECTURE.md` — เอกสารออกแบบระบบ (ใหม่)
- `TASKS.md` — อัปเดต Phase 2 → ✅ Complete
- `SESSION_LOG.md` — เพิ่ม S003
- `CHANGELOG.md` — ไฟล์นี้

---

## [0.2.0] - 2026-07-27

### 🔭 Phase 1: Research Review Complete

- **ขยายเป้าหมาย** — จาก K3 สู่โมเดลใหญ่ทุกรูปแบบ (MoE, Dense, Hybrid) แต่เริ่มที่ K3
- อัปเดต PROJECT.md และ CONCEPT.md ให้สะท้อนเป้าหมายที่กว้างขึ้น
- ค้นคว้างานวิจัย 4 หมวด + K3 architecture

#### หมวดวิจัยที่ค้นคว้า

| หมวด | # Papers | SOTA | Key Finding |
|------|---------|------|-------------|
| **Speculative Decoding** | 8 | EAGLE-3 (NeurIPS'25) | Draft head <5% params, 2-4x speedup, scaling law |
| **MoE Routing Prediction** | 10 | PreScope (2025) | Expert prediction >90% accuracy ด้วย MLP เล็ก |
| **Out-of-Core Execution** | 8 | flash-moe, llama.cpp | SSD streaming ใช้ได้จริง 1.9-4.4 tok/s แต่ยัง reactive |
| **Near-Storage Compute** | 5 | HILOS (ASPLOS'26) | ยังไม่成熟พอสำหรับ LLM — ควรรอ hardware |
| **Kimi K3 Architecture** | — | เปิด weights 27 ก.ค. 2026 | MXFP4, KDA, Quantile Balancing, 896 experts |

#### ไฟล์ที่สร้าง/แก้ไข
- `PROJECT.md` — ขยายเป้าหมาย + เพิ่ม Dense model case
- `docs/CONCEPT.md` — อัปเดตเป็น architecture-agnostic + เพิ่ม Dense case
- `research/index.md` — สรุปผลวิจัยรวม
- `research/speculative-decoding/README.md` — 8 papers
- `research/moe-routing/README.md` — 10 papers
- `research/out-of-core-execution/README.md` — 8 โครงการ
- `research/near-storage-compute/README.md` — 5 papers
- `research/kimi-k3/README.md` — K3 architecture deep dive
- `research/README.md` — อัปเดต

---

## [0.1.0] - 2026-07-27

### ✨ Initial Concept

- กำหนดแนวคิด **Speculative Weight Streaming** — รันโมเดล 2.8T+ บนเครื่องทั่วไป RAM 32–64 GB
- ออกแบบสถาปัตยกรรม 3-layer: Draft Model → Weight Predictor → Streaming Buffer
- วิเคราะห์ feasibility: bandwidth, latency, memory budget
- ระบุ novel contributions และ open problems
- บันทึกแนวทางเสริม: Computational Storage, Collaborative Inference, MoE Compression

#### ไฟล์ที่สร้าง
- `PROJECT.md` — ภาพรวมโครงการ
- `docs/CONCEPT.md` — Concept ฉบับสมบูรณ์
- `CHANGELOG.md` — ไฟล์นี้

---

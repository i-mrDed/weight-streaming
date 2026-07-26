# Changelog — Speculative Weight Streaming

> รูปแบบ: [Semantic Versioning](https://semver.org/)  
> ทุกการเปลี่ยนแปลงต้องบันทึกในไฟล์นี้

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

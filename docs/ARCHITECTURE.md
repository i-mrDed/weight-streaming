# Architecture Design — Speculative Weight Streaming

> **Phase 2 research design — 2026-07-27**
> เอกสารนี้ครอบคลุมทุก component ของระบบ: Data Layout → Predictor → Scheduler → Buffer → Execution  
> *Based on Phase 1 Research Review (EAGLE-3, PreScope, flash-moe, K3 architecture)*
>
> **Current implementation note (updated 2026-07-30):** This is the original research architecture, not a statement of shipped behavior. See **[§0 As-Built Summary](#0-as-built-summary-adr-003--v0130)** below for the research-design → shipped-product mapping (per ADR-003 in `docs/DECISIONS.md`). The SPA streaming reliability round is COMPLETED and validated on a real model (2026-07-29) — see `docs/HANDOFF_STREAMING_RELIABILITY.md`.

---

## 0. As-Built Summary (ADR-003 → v0.13.0)

> **Sections 1–9 document the Phase 2 research design and are preserved as-is** (design history). The shipped product diverged after empirical results (EXP-001–004, Phase 3b re-runs with real hardware timing). Authoritative decisions: `docs/DECISIONS.md` → **ADR-003**. This section summarizes what was actually built.

### Research design → shipped product

| Component | Research design (section) | Shipped (ADR-003) | Why |
|-----------|---------------------------|-------------------|-----|
| Weight predictor | MLP ~2M params, primary (§3) | **Heuristic only** (frequency + temporal); MLP/EAGLE kept as research code (`core/eagle_dual_predictor.py`) | Phase 3b: LRU alone = 93.8% hit @ 64 MB; predictor not throughput-critical; expert routing is opaque from stock llama.cpp (no Python-visible routing events) |
| Streaming buffer | 256 MB–1 GB, LRU + priority (§5) | **64 MB LRU tracking**, no priority boost; real caching done by the OS page cache over mmap | 93.8% @ 64 MB adequate; priority boost caused clogging (EXP-002); ~92% compute-bound ⇒ buffer is RAM reduction, not a throughput accelerator |
| Weight access | Custom buffer read, mmap fallback (§6) | **mmap primary** (llama.cpp) + `PrefetchVirtualMemory` (Win) / `madvise` (Linux) hints | mmap = free zero-copy streaming; the OS is already the optimal page manager |
| I/O engine | io_uring/IOCP dispatch, core path (§4) | OS-managed; native io_uring/IOCP/SIMD kernels kept as research prototypes (`core/native/`) | Not needed while compute-bound on consumer hardware |
| Integration | Fork llama.cpp (§6.4) | **llama-cpp-python adapter** (`backends/llama_cpp.py` → `WeightStreamModel`) with public `stream_chat()` wrapper | No C++ build dependency; works with any GGUF model |
| Telemetry | Confidence/prediction metrics | **Honest telemetry**: real generation stats, OS page-residency sampling, prefetch accuracy only from real evidence (else `n/a`) | Synthetic values mislead product decisions |

### First real-model validation (2026-07-29)

Model: `Qwen1.5-MoE-A2.7B` Q2_K — 5.48 GB, `qwen2moe`, 60 experts; CPU inference (threads = half of logical cores), 64 GB RAM. Raw data: `docs/verification/items_45_2026-07-29_raw.txt`.

| Metric | Result |
|--------|--------|
| Throughput | 17.9 tok/s (220 tokens / 12.3 s), first token 0.96 s |
| Responsiveness during generation | `/health` avg 5.7 ms / max 23.3 ms, `/v1/stats` max 22.8 ms (58 polls each) |
| OS page residency during generation | 4.6% of the model (0.25 / 5.48 GB) resident — throughput unaffected |
| Cancellation | halted within 0.73 s (8 tokens), model lock released, regeneration immediate |
| **Open gap** | `StreamingBuffer.total_accesses = 0` during real inference — the tracker observes nothing because llama.cpp reads the mmap opaquely (next: buffer-abstraction prototype, TASKS.md Phase 3) |

---

## 📋 สารบัญ

0. [As-Built Summary (ADR-003 → v0.13.0)](#0-as-built-summary-adr-003--v0130)
1. [System Overview](#1-system-overview)
2. [NVMe Data Layout](#2-nvme-data-layout)
3. [Weight Predictor](#3-weight-predictor)
4. [Pre-fetch Scheduler](#4-pre-fetch-scheduler)
5. [Streaming Buffer](#5-streaming-buffer)
6. [Execution Engine](#6-execution-engine)
7. [Abstraction Layer](#7-abstraction-layer)
8. [Interface Contracts](#8-interface-contracts)
9. [Implementation Roadmap](#9-implementation-roadmap)

---

## 1. System Overview

### 1.1 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│ PROCESS (CPU + GPU)                                              │
│                                                                  │
│  ┌─────────────────────┐    ┌──────────────────────────────┐    │
│  │ ① Draft Head        │    │ ③ Pre-fetch Scheduler        │    │
│  │ (EAGLE-3 style)     │───→│ • Priority queue             │    │
│  │ • Predict tokens     │    │ • I/O batching               │    │
│  │ • Predict weights    │    │ • io_uring/IOCP dispatch     │    │
│  └─────────┬───────────┘    └────────────┬─────────────────┘    │
│            │                              │                       │
│            ▼        ② Weight Predictor    ▼                       │
│  ┌─────────────────────┐    ┌──────────────────────────────┐    │
│  │ Feature Extractor   │    │ ④ Streaming Buffer            │    │
│  │ • Router logits      │    │ • LRU + priority eviction    │    │
│  │ • Hidden states      │    │ • 256 MB–1 GB                │    │
│  │ • Attention scores   │    │ • Hit → instant use          │    │
│  └─────────┬───────────┘    │ • Miss → fallback mmap       │    │
│            │                └────────────┬─────────────────┘    │
│            ▼                              │                       │
│  ┌─────────────────────┐                  │                       │
│  │ MLP Predictor       │                  │                       │
│  │ • Predict next       │                  │                       │
│  │   expert/shard IDs  │                  │                       │
│  │ • Confidence scores  │                  │                       │
│  │ • Priority ranking   │──────────────────┘                       │
│  └─────────────────────┘                                          │
│                                                                   │
│  ┌───────────────────────────────────────────────────────────┐    │
│  │ ⑤ Execution Engine                                        │    │
│  │ • Read weights from buffer                                 │    │
│  │ • Fallback to mmap on miss                                 │    │
│  │ • Orchestrate compute (GPU/CPU)                            │    │
│  └───────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│ NVMe SSD (2-4 TB)                                                │
│                                                                  │
│  ┌───────────────────────────────────────────────────────────┐   │
│  │ ⑥ Weights Store (on-disk layout)                         │   │
│  │ • Flat shard blocks (sequential-optimized)                │   │
│  │ • Metadata index (expert/layer → offset)                  │   │
│  │ • Separated by class: attention / shared / routed         │   │
│  └───────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────┘
```

### 1.2 Data Flow

```
Token T:
  ① Draft Head predicts: token T+1..T+5 + weight set W = {w1, w2, ..., wk}
  ② MLP Predictor refines W with confidence scores
  ③ Scheduler: check buffer → pre-fetch missing weights from NVMe
  ④ Buffer: receive pre-fetched weights → update cache state
  ⑤ Execution Engine: read from buffer → compute token T
  ⑥ (overlap) Draft Head + Predictor + Scheduler ทำงานล่วงหน้าขนาน
```

### 1.3 Timing Design

```
Time ──────────────────────────────────────────────────────────────►
                    ╔══════════ overlap ══════════╗
Token T: Compute   ║ ① Draft → ② Predict → ③ Pre-fetch ║→ Token T+1
          ╚══════ compute ══════╝
          ◄─── target: 350-500ms ──►
```

---

## 2. NVMe Data Layout

### 2.1 Design Goals

| Goal | Requirement |
|------|------------|
| **Sequential read** | maximize I/O bandwidth (~14 GB/s PCIe 5.0) |
| **Random access** | minimize seeks (large shard size) |
| **Partial read** | ไม่ต้องอ่านทั้ง block ถ้าต้องการแค่บาง expert |
| **Metadata lookup** | O(1) หรือ O(log N) — หา offset จาก expert+layer ID |

### 2.2 Shard Structure

```
File: model-weights.bin (pre-optimized, contiguous)

┌─────────────────────────────────────────────────────────────┐
│ HEADER (4 KB)                                                │
│ • Magic: "SWSv1"                                             │
│ • Model metadata: n_layers, n_experts, precision, etc.      │
│ • Shard table offset                                         │
│ • Shard count, shard size                                    │
├─────────────────────────────────────────────────────────────┤
│ SHARD TABLE (variable, ~1 MB for K3)                         │
│ • Flat array: [shard_id → offset, size, type]               │
│ • Secondary index: (expert_id, layer_id) → shard_id          │
│ • Type: attention, shared_mlp, routed_expert, embedding      │
├─────────────────────────────────────────────────────────────┤
│ SHARD DATA (main body, ~1.4 TB for K3)                       │
│                                                              │
│  Region A: Shared weights (read every token, ~50 GB)         │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │ • embeddings                                             │ │
│  │ • attention projections (Q, K, V, O)                    │ │
│  │ • shared MLP layers                                      │ │
│  └─────────────────────────────────────────────────────────┘ │
│                                                              │
│  Region B: Routed experts (read sparsely, ~1.35 TB)          │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │ Layout: (expert 0, layer 0) → (expert 1, layer 0) → ...│ │
│  │ → (expert N, layer L) ← sequential within each group   │ │
│  │                                                          │ │
│  │ Grouped by expert popularity:                            │ │
│  │   Hot zone: experts ที่ถูกเรียกบ่อย → front              │ │
│  │   Cold zone: experts ที่ถูกเรียกนานๆ ครั้ง → back        │ │
│  └─────────────────────────────────────────────────────────┘ │
│                                                              │
│  Region C: KV cache offload (optional, ~8-16 GB)              │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │ • KV cache blocks สำหรับ long context                    │ │
│  └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### 2.3 Shard Size

| Type | Size per shard | Read pattern |
|------|---------------|-------------|
| Attention projection | ~2-4 MB | Sequential (ทุก token) |
| Shared MLP | ~2-4 MB | Sequential (ทุก token) |
| Routed expert | ~4 MB (K3 MXFP4) | Random (เฉพาะ expert ที่ activate) |
| Embedding | Variable | Sequential |

**Optimal shard size:** **2-4 MB** — balance ระหว่าง:
- Sequential read efficiency (256 KB+ → near full bandwidth)
- Random read granularity (อ่านเฉพาะที่ต้องการ)
- Alignment กับ buffer unit

### 2.4 Metadata Index

```c
// In-memory metadata (loaded at startup, ~100-200 MB for K3)
struct ShardMeta {
    uint64_t offset;         // byte offset in file
    uint32_t size;           // byte size
    uint16_t type;           // 0=attention, 1=shared_mlp, 2=routed_expert
    uint16_t expert_id;      // for routed experts
    uint16_t layer_id;
};

// Lookup: O(1) via (expert_id * n_layers + layer_id) index
// ถ้า expert_id == -1 → attention/shared (tied to layer)
```

### 2.5 Optimization: Popularity-Based Layout

```
K3 case: 896 experts, expected distribution:
  - Top 10% hot experts → 60% of access →  จัดไว้ contiguous zone
  - Middle 30% → 30% of access
  - Bottom 60% → 10% of access → จัดไว้ท้าย

Benefit: sequential reads สำหรับ hot experts บ่อยขึ้น
```

### 2.6 K3-Specific Parameters

| Parameter | Value |
|-----------|-------|
| Total experts | 896 |
| Layers | ~80 (estimated) |
| Active experts/token | 16 |
| Shard size (MXFP4 expert, 1 layer) | ~4 MB |
| Total shards | ~71,680 |
| Hot zone size | ~72 GB (top 10% experts) |
| Metadata size in-memory | ~2 MB |

---

## 3. Weight Predictor

### 3.1 Design Goals

| Goal | Requirement |
|------|------------|
| **Accuracy** | Top-16 expert prediction >80% hit rate |
| **Latency** | <5 ms prediction (overlap กับ compute) |
| **Size** | <50 MB model weights (อยู่ใน RAM ตลอด) |
| **Adaptability** | Online learning — ปรับปรุงระหว่าง inference |

### 3.2 Architecture Options

| Option | Pros | Cons | Selected |
|--------|------|------|----------|
| **A: Heuristic** (frequency + temporal) | Zero overhead, no training | ~50-60% accuracy, ไม่ adaptive | ❌ |
| **B: MLP** (PreScope-style) | >90% accuracy, lightweight | ต้อง train data, ~5 ms | ✅ **Primary** |
| **C: Extend EAGLE-3 head** | Novel contribution, reuse features | ยังไม่เคยมีใครทำ, เสี่ยง | 🟡 **Future** |

> **As-built (ADR-003):** ตัวเลือก A (heuristic) ถูกเลือกสำหรับ product — Phase 3b (real timing) พบว่า LRU อย่างเดียวได้ 93.8% hit @ 64 MB และ predictor ไม่กระทบ throughput; ตัวเลือก B/C คงไว้เป็น research code ใน `weight_stream/core/`

### 3.3 Selected: MLP Predictor (PreScope-inspired)

```
Input Features (per layer):
  - Router logits จาก layer i-1 (top-32 expert probabilities)
  - Inter-layer affinity vector (expert activation correlation)
  - Popularity score (historical frequency)
  - Token embedding (จาก draft head, ~256 dim)
  
Output:
  - Expert ID scores: [0..895] → probability distribution
  - Confidence score per prediction
  - Top-K ranking (K = 32 → safety margin)

Architecture:
  ┌─────────────┐   ┌──────────┐   ┌──────────────┐
  │ Input       │──→│ MLP      │──→│ Softmax      │
  │ (128-256)   │   │ 2 layers │   │ (896 experts)│
  └─────────────┘   │ 512→1024 │   └──────────────┘
                     │ 1024→896 │
                     └──────────┘
  
  Total params: ~2M → ~8 MB (FP32)
  Inference: ~1-3 ms (GPU) / ~5-10 ms (CPU)
```

### 3.4 Training Strategy

```
Phase 1 (offline):
  - Collect routing traces จาก K3 หรือ MoE model ที่มี
  - Train MLP: cross-entropy loss on expert selection
  - Data augmentation: noise injection, dropout

Phase 2 (online fine-tuning):
  - ระหว่าง inference, บันทึก prediction vs actual
  - Periodic fine-tune (ทุก N tokens)
  - Weighted update: recent misses > old hits
```

### 3.5 Fallback Strategy เมื่อ Predictor Miss

```
เมื่อ predictor miss:
  1. Miss rate < 20% → continue (tolerable)
  2. Miss rate 20-40% → reduce speculative depth
  3. Miss rate > 40% → fallback to heuristic mode
  
  Heuristic mode:
    - Frequency-based: pre-fetch top-32 most popular experts
    - Temporal: pre-fetch experts used in last K tokens
    - Conservative: increase buffer size temporarily
```

---

## 4. Pre-fetch Scheduler

### 4.1 Design Goals

| Goal | Requirement |
|------|------------|
| **Latency hiding** | overlap I/O กับ compute >80% |
| **Bandwidth utilization** | >70% of NVMe sequential bandwidth |
| **Fairness** | high-priority weights ก่อน, low-priority ตามหลัง |
| **Adaptability** | ปรับ priority dynamic ตาม prediction confidence |

### 4.2 Scheduler Pipeline

```
                    Timeline (parallel)
                    ┌───┬───┬───┬───┬───┬───┬───┬───┐
Draft/Predict       │ P │ P │ P │ P │ P │ P │ P │ P │
                    └───┴───┴───┴───┴───┴───┴───┴───┘
Scheduler (I/O)      ╔═══╦═══╦═══╦═══╦═══╦═══╦═══╦═══╗
                     ║ I ║ I ║ I ║ I ║ I ║ I ║ I ║ I ║
                     ╚═══╩═══╩═══╩═══╩═══╩═══╩═══╩═══╝
Execution (compute)   ┌───┬───┬───┬───┬───┬───┬───┬───┐
                      │ C │ C │ C │ C │ C │ C │ C │ C │
                      └───┴───┴───┴───┴───┴───┴───┴───┘
                      ◄─── 1 token time (~350-500ms) ──►

P = predict, I = I/O prefetch, C = compute
Overlap: P+I ทำงานล่วงหน้า → C ไม่ต้องรอ I/O
```

### 4.3 Priority Queue Design

```c
struct PrefetchRequest {
    uint16_t shard_id;       // shard to read
    uint8_t priority;        // 0=critical, 1=high, 2=normal, 3=low
    uint64_t deadline_tick;  // must arrive before this tick
    uint32_t confidence;     // predictor confidence (0-1000)
    void* buffer_addr;       // destination in streaming buffer
};

// Priority ordering:
// 1. deadline_tick (earliest first)
// 2. priority level (if same deadline)
// 3. confidence (if same priority)

// Queue operations:
void scheduler_push(PrefetchRequest req);
bool scheduler_poll(PrefetchRequest* out);  // pop highest priority
void scheduler_emergency_prefetch(uint16_t* shard_ids, int count);
```

### 4.4 I/O Batching Engine

```
Batch formation:
  - เมื่อ queue มี requests ถึง threshold → form batch
  - Batch: sort by file offset → sequential reads
  - Max batch: 64 MB (avoid hogging PCIe)
  - Issue: io_uring (Linux) / IOCP (Windows)

Windows specific:
  - ใช้ OVERLAPPED I/O + I/O Completion Ports
  - Thread pool: N threads (N = NVMe queue depth)
  - Callback เมื่อ I/O complete → buffer ready

Pseudo:
  scheduler_process():
    batch = []
    while len(batch) < MAX_BATCH and queue not empty:
        req = queue.pop()
        batch.append(req)
        if len(batch) >= MIN_BATCH or gap_between_offsets > THRESHOLD:
            break
    
    // Sort by offset for sequential read
    batch.sort(by offset)
    
    // Issue async read
    io_uring_prep_readv(ring, fd, batch.iovs, batch.count, batch.offset)
    io_uring_submit(ring)
    
    // เมื่อ complete → callback แจ้ง buffer
```

### 4.5 Timing Model

```
Target timeline (K3 case, 16 experts/token):

t=0ms   Draft head start → 1-3 ms
t=3ms   Predictor start  → 1-3 ms  
t=6ms   Scheduler start  → form batch → issue I/O
t=6-10ms  NVMe sequential read (16 experts ~64 MB / 14 GB/s = 4.6ms)
t=10ms  Buffer ready → Execution Engine can start
        
Overlap with compute (target 350-500ms):
  - I/O (4.6ms) << Compute (350ms)
  - → I/O latency hidden completely if scheduled early enough
```

### 4.6 Emergency: เมื่อ Predictor Misses

```
Scenario: Predictor says expert #12, #45, #67
            Actual: expert #12, #88, #99

Miss handler:
  1. Detect miss (buffer doesn't have requested shard)
  2. Emergency pre-fetch: skip queue → direct I/O
  3. Fallback compute: micro-batch suspend (wait for I/O)
  4. Penalty: ~5-10ms miss penalty (still << 350ms compute)
```

---

## 5. Streaming Buffer

### 5.1 Design Goals

| Goal | Requirement |
|------|------------|
| **Hit rate** | >80% (target 90%+ with good predictor) |
| **Size** | 256 MB–1 GB (configurable) |
| **Eviction** | LRU + priority-based |
| **Concurrent access** | Thread-safe (read from executor, write from I/O) |

> **As-built (ADR-003):** ค่าจริงที่ ship คือ **64 MB, plain LRU** (ไม่มี priority) — priority eviction ทำให้ cache clogging ใน EXP-002; buffer เป็น tracker/hint layer บน OS page cache ไม่ใช่ private data cache

### 5.2 Buffer Architecture

```
┌──────────────────────────────────────────────────────┐
│ Streaming Buffer                                      │
│ Size: 256 MB (default) ~ 64 shards (K3, 4 MB each)    │
│                                                        │
│  ┌──────┬──────┬──────┬──────┬──────┬──────┬──────┐  │
│  │ S#12 │ S#45 │ S#67 │ S#03 │ S#89 │ S#22 │ ...  │  │
│  ├──────┼──────┼──────┼──────┼──────┼──────┼──────┤  │
│  │ hot  │ hot  │ warm │ warm │ cold │ cold │ evic │  │
│  └──────┴──────┴──────┴──────┴──────┴──────┴──────┘  │
│                                                        │
│  Access pattern:                                       │
│    • Hit → no I/O, instant compute                     │
│    • Miss → emergency pre-fetch + penalty              │
│    • Evict → LRU (updated on every access)             │
│                                                        │
│  Hot set: shards ที่จะใช้ใน ~3 tokens ข้างหน้า            │
│  Warm set: shards ที่ใช้แล้วแต่ยังมี chance reuse        │
│  Cold set: candidates for eviction                     │
└──────────────────────────────────────────────────────┘
```

### 5.3 Data Structures

```c
struct BufferSlot {
    uint16_t shard_id;          // -1 = empty
    uint32_t last_access_tick;  // for LRU
    uint8_t priority;           // 0-3 (boosted by predictor)
    uint8_t refcount;           // 0 = evictable
    void* data;                 // pointer to shard data
};

class StreamingBuffer {
    BufferSlot* slots;           // fixed-size array
    int capacity;                // number of shards
    
    // Fast lookup: shard_id → slot index
    std::unordered_map<uint16_t, int> index;
    
    // Eviction candidates (priority sorted)
    std::priority_queue<EvictionCandidate> evict_queue;
    
public:
    bool get(uint16_t shard_id, void** out_data);
    void put(uint16_t shard_id, const void* data, uint8_t priority);
    void touch(uint16_t shard_id);  // update LRU
};
```

### 5.4 Cache Policy

```
On access:
  if shard in buffer:
      hit → update last_access_tick, maybe boost priority
      return data
  else:
      miss → trigger emergency pre-fetch
      return null (caller waits)

On pre-fetch complete:
  if buffer full:
      evict candidate (lowest priority + oldest access)
  put shard in buffer
  update index

Eviction candidate selection:
  score = α × (current_tick - last_access_tick)  // LRU
         + β × (3 - priority)                     // priority bias
         + γ × (confidence < threshold ? 1 : 0)   // predictor trust
  
  Evict slot with highest score
```

### 5.5 Buffer Sizing

| Buffer size | Shard capacity (K3, 4MB) | Expected hit rate |
|-------------|--------------------------|-------------------|
| 128 MB | 32 | ~60-70% |
| **256 MB** | **64** | **~80% (target)** |
| 512 MB | 128 | ~87% |
| 1 GB | 256 | ~92% |
| 2 GB | 512 | ~95% |

**Default: 256 MB** — sweet spot for RAM usage vs hit rate

> **As-built (ADR-003):** default ที่ ship คือ **64 MB** (93.8% simulated hit ด้วย real timing; ยืนยันแล้วว่าเพียงพอด้วย Qwen1.5-MoE Q2_K — ดู §0)

### 5.6 Cold Start Strategy

```
Token 1-3 (buffer cold):
  - All weights must be fetched from NVMe
  - Target: accept higher latency (~1-2s per token)
  - Run without speculative decoding (reduce complexity)
  
Token 4+ (buffer warming):
  - Predictor เริ่มมีข้อมูล → hit rate improves
  - Speculative decoding เริ่มทำงาน full speed
  
Optimization:
  - Pre-load hot experts ที่รู้จักล่วงหน้า (frequency-based)
  - ใช้ popularity data จาก model profile
```

---

## 6. Execution Engine

### 6.1 Design Goals

| Goal | Requirement |
|------|------------|
| **Buffer-aware** | อ่าน weight จาก buffer เป็นหลัก |
| **Graceful fallback** | ถ้า miss → ใช้ mmap |
| **Framework agnostic** | ไม่ผูกกับ inference framework |
| **Overlap support** | รองรับ async weight loading |

### 6.2 Architecture

```
Execution Engine
    │
    ├── BufferReader ──── Streaming Buffer
    │       │
    │       ▼ (เมื่อ miss)
    │   MmapFallback ──── NVMe (direct mmap)
    │
    ├── ComputeOrchestrator
    │       │
    │       ├── GPU path (CUDA/Metal/Vulkan)
    │       └── CPU path (ggml/llama.cpp)
    │
    └── LifecycleManager
            │
            ├── token_start(token_id)
            ├── load_weights(shard_ids)
            ├── compute_layer(layer_id)
            └── token_end()
```

### 6.3 Interface Definition

```python
# High-level API — execution engine interface

class WeightStreamingEngine:
    def __init__(self, model_path: str, buffer_size_mb: int = 256):
        self.layout = NVMELayout(model_path)     # load shard metadata
        self.predictor = WeightPredictor()        # MLP predictor
        self.scheduler = PrefetchScheduler()
        self.buffer = StreamingBuffer(buffer_size_mb)
        self.draft = EagleDraftHead(model_path)   # or separate draft model
    
    def generate(self, prompt: str, max_tokens: int = 100):
        # Token generation loop
        for step in range(max_tokens):
            # === OVERLAPPED PHASE (parallel) ===
            
            # ① Draft: predict next tokens + weight access
            candidates = self.draft.predict(prompt, n_candidates=5)
            weight_set = self.predictor.predict(candidates, self.draft.hidden_states)
            
            # ② Scheduler: check buffer → pre-fetch
            missing = self.scheduler.schedule(weight_set, self.buffer)
            if missing:
                self._async_prefetch(missing)  # io_uring/IOCP
            
            # ③ Execute current token (from buffer)
            #    (I/O from step ② ทำงาน overlap)
            token = self._compute_next_token()
            
            # ④ Update predictor with actual routing result
            self.predictor.observe(actual_routing, prediction)
    
    def _compute_next_token(self) -> int:
        for layer in range(self.n_layers):
            # Read attention weights
            attn_w = self.buffer.get(layer.attention_shard)
            if not attn_w:
                attn_w = self._mmap_fallback(layer.attention_shard)
            
            # Read expert weights (if MoE layer)
            if layer.is_moe:
                for expert_id in layer.active_experts:
                    exp_w = self.buffer.get(expert_id, layer)
                    if not exp_w:
                        exp_w = self._mmap_fallback(expert_id, layer)
                    # compute expert FFN
            # compute attention + FFN
```

### 6.4 Integration Strategies

| Strategy | Effort | Performance | Recommended for |
|----------|--------|------------|-----------------|
| **Custom inference loop** | สูง | ดีที่สุด | Research prototype |
| **llama.cpp fork** | กลาง | ดี | Quick prototype |
| **vLLM plugin** | กลาง | ดีมาก | Production |
| **SGLang extension** | กลาง | ดีมาก | Production |

**สำหรับ Phase 3 (Prototype):** fork llama.cpp — มี MoE support, mmap, CPU/GPU hybrid

> **As-built (ADR-003):** ไม่ fork — ship เป็น **llama-cpp-python adapter** (`weight_stream/backends/llama_cpp.py`, `WeightStreamModel` + public `stream_chat()`); native C/C++ kernels อยู่ใน `weight_stream/core/native/` ในฐานะ research prototype

---

## 7. Abstraction Layer

### 7.1 Design Goals

| Goal | Requirement |
|------|------------|
| **Model agnostic** | ใช้ได้กับ MoE, Dense, Hybrid |
| **Plugin architecture** | เพิ่ม model type ใหม่โดยไม่แก้ core |
| **Unit polymorphism** | caching unit เปลี่ยนตาม architecture |

### 7.2 Class Hierarchy

```
ModelArchitecture (abstract)
    │
    ├── MoEArchitecture
    │   • caching_unit = "expert"
    │   • shard_id = (expert_id, layer_id)
    │   • predict_routing = predict_experts()
    │   • sparsity_model = per-token expert selection
    │
    ├── DenseArchitecture
    │   • caching_unit = "layer_shard"
    │   • shard_id = (layer_id, shard_offset)
    │   • predict_routing = predict_layer_activity()
    │   • sparsity_model = activation sparsity (ReLU)
    │
    └── HybridArchitecture
        • caching_unit = mixed (expert + layer)
        • shard_id = architecture-specific
        • predict_routing = composite predictor
```

### 7.3 Common Interface

```c
// Every architecture must implement:
class ModelArchitecture {
public:
    // What we cache (experts? layers? projection shards?)
    virtual std::vector<ShardID> get_caching_units() = 0;
    
    // How to predict next weight access
    virtual WeightPrediction predict_next_weights(
        const DraftOutput& draft,
        const History& history) = 0;
    
    // How to compute one token
    virtual void compute_token(
        const TokenID& token,
        BufferReader& buffer,
        TensorPool& pool) = 0;
    
    // Architecture-specific metadata
    virtual ArchitectureInfo get_info() = 0;
};
```

### 7.4 MoE vs Dense Comparison

| Aspect | MoE (K3) | Dense (100B+) |
|--------|----------|---------------|
| **Caching unit** | 1 expert (4 MB) | 1 layer shard (1-2 GB) |
| **Sparsity** | 16/896 experts (1.8%) | Activation sparsity (30-50%) |
| **Predictor task** | Predict which 16 experts | Predict which layers/shod to skip |
| **Buffer size needed** | 256 MB (64 experts) | 1-2 GB (1-2 layers) |
| **Bandwidth requirement** | Low (~128 MB/s) | Higher |
| **Pre-fetch gain** | High (expert-level) | Lower (layer-level) |

---

## 8. Interface Contracts

### 8.1 Internal APIs

```python
# --- Predictor → Scheduler ---
class PredictionOutput:
    shard_priorities: list[tuple[ShardID, float]]  # (shard, confidence)
    speculative_depth: int  # how many tokens ahead predicted
    timestamp: int

# --- Scheduler → Buffer ---
class PrefetchResult:
    shard_id: ShardID
    data: bytes | None  # None if I/O failed
    latency_us: int

# --- Buffer → Execution Engine ---
class BufferAccess:
    shard_id: ShardID
    data: bytes | None  # None = miss
    hit: bool
```

### 8.2 Configuration Interface

```json
{
  "version": "0.3.0",
  "model": {
    "path": "/models/kimi-k3-mxfp4.bin",
    "type": "moe",
    "n_layers": 80,
    "n_experts": 896,
    "active_experts": 16,
    "shard_size": 4194304
  },
  "buffer": {
    "size_mb": 256,
    "eviction": "lru_priority",
    "cold_start_preload": true
  },
  "predictor": {
    "type": "mlp",
    "model_path": "/models/predictor.onnx",
    "fallback": "heuristic",
    "online_learning": true
  },
  "scheduler": {
    "io_engine": "auto",
    "max_batch_mb": 64,
    "min_batch_count": 4,
    "emergency_timeout_ms": 10
  }
}
```

---

## 9. Implementation Roadmap

> **Status (2026-07-30):** Phase 3a เสร็จแล้ว (EXP-001–003) — Phase 3b เบี่ยงเบนจากแผนนี้ตาม ADR-003: adapter แทน fork, Qwen1.5-MoE แทน Mixtral, I/O ปล่อย OS จัดการ; แผนปัจจุบันอยู่ที่ `docs/ROADMAP.md`

### Phase 3a: Simulator (Pure Python)

```
1. NVMeDataLayout — simulate shard storage
   • จำลอง file layout + metadata index
   • Random access timing model

2. StreamingBuffer — pure logic test
   • Eviction policies: LRU, LFU, priority-LRU
   • Measure: hit rate vs buffer size vs workload

3. Predictor (heuristic) — baseline
   • Frequency-based, temporal-based
   • Establish lower bound for accuracy

4. Scheduler — I/O timing simulation
   • จำลอง NVMe bandwidth + latency
   • Measure: overlap efficiency

Deliverable: สถิติ performance bounds (best/worst case)
```

### Phase 3b: Prototype Integration

```
5. Fork llama.cpp — add buffer layer
   • Replace mmap with streaming buffer
   • Add predictor hook
   
6. Test with real MoE model (e.g., Mixtral 8x7B)
   • จำลอง NVMe delay (ถ้า model fit ใน RAM)
   • วัด latency distribution

Deliverable: working prototype + real measurements
```

### Phase 4: Evaluation

```
7. Full evaluation suite
   • Hit rate vs buffer size
   • Latency distribution (P50, P95, P99)
   • Throughput (tokens/second)
   • Energy consumption
```

---

> **References:**
> - PreScope (arXiv 2509.23638) — MLP predictor + cross-layer scheduler
> - EAGLE-3 (arXiv 2503.01840) — draft head architecture
> - flash-moe / llama-cpp-moe-flash — SSD streaming PoC
> - K3 architecture — MXFP4, KDA, Quantile Balancing
> - ADR-001, ADR-002, ADR-003 in docs/DECISIONS.md

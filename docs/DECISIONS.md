# Architecture Decision Records (ADR)

> **用途:** บันทึกการตัดสินใจทางเทคนิค — รู้ที่มา รู้เหตุผล รู้ consequences  
> **รูปแบบ:** [ADR-NNN] — เรียงตามลำดับเวลา  
> **ต้องทำ:** เมื่อมีการตัดสินใจที่กระทบ architecture, approach, หรือ tooling

---

## ADR-001: Speculative Weight Streaming 3-Layer Architecture

| รายการ | รายละเอียด |
|--------|-----------|
| **วันที่** | 2026-07-27 |
| **สถานะ** | ✅ Accepted |
| **Context** | ต้องการรัน LLM ขนาด 100B–3T+ บนเครื่องทั่วไป RAM 32–64 GB |
| **กระทบ** | Architecture ทั้งหมด, I/O engine, execution model |

### ตัวเลือกที่พิจารณา

| ตัวเลือก | ข้อดี | ข้อเสีย |
|---------|------|--------|
| **A) mmap อย่างเดียว** (llama.cpp approach) | ไม่ต้อง implement เพิ่ม, ใช้ OS จัดการ cache | Page fault → reactive → latency spike, ไม่รู้ MoE topology |
| **B) OS swap / virtual memory** | ไม่ต้องแก้ code | ไม่มี control, ไม่รู้ expert patterns, performance ไม่แน่นอน |
| **C) Speculative Weight Streaming** | Structure-aware, predictive, predictable latency | ต้อง implement เองทั้งหมด, complexity สูง |

### การตัดสินใจ

**เลือก C: Speculative Weight Streaming 3-Layer**

```
Layer 1: Draft Model (EAGLE-3 head) → predict tokens + weight access
Layer 2: Weight Predictor → priority queue + pre-fetch scheduling
Layer 3: Streaming Buffer → execute from buffer with LRU eviction
```

### เหตุผล
1. mmap/swap ไม่สามารถแก้ root cause — reactive I/O จะมี stall เสมอ
2. MoE architecture มี structure ให้ exploit — ใช้ draft model ทำนายได้
3. Research แสดงว่า expert prediction ทำได้ >90% accuracy
4. 3 layers overlap ได้ — latency hiding ไม่ใช่แค่ bandwidth hiding
5. ใช้ได้ทั้ง MoE และ Dense (ปรับ unit of caching)

### Consequences
- ✅ Positive: Latency profile predictable, resource-efficient
- ✅ Positive: ใช้ draft model ซ้อน speculative decoding → ไม่เสีย overhead เพิ่ม
- ⚠️ Negative: ต้อง custom I/O engine (ไม่ใช่ mmap ล้วน)
- ⚠️ Negative: Predictor accuracy ต้อง >80% ถึงจะคุ้ม

### Revisit เมื่อ
- มี hardware computational storage ที่ mature
- เมื่อทดสอบ prototype แล้วพบว่า overhead ของ predictor สูงเกินไป

---

## ADR-002: เริ่มต้นที่ Kimi K3 แต่ Framework ต้อง Support Cross-Architecture

| รายการ | รายละเอียด |
|--------|-----------|
| **วันที่** | 2026-07-27 |
| **สถานะ** | ✅ Accepted |
| **Context** | โปรเจคต้องการ target model แรก |

### การตัดสินใจ
- **เริ่มต้น**ที่ K3 (2.8T MoE, เปิด weights 27 ก.ค. 2026)
- ออกแบบระบบให้ **ไม่ผูกติดกับ MoE** — ต้อง support Dense model ด้วย

### เหตุผล
- K3 มี open weights, spec ชัด, sparsity 1.8% → เหมาะเป็น use case แรก
- แต่ dense model ก็ต้องการ solution เดียวกัน (e.g., Llama-400B+)

### Consequences
- ✅ Positive: K3 data เหมาะกับแนวทาง — MXFP4, KDA, 16/896 experts
- ⚠️ Negative: K3 ใช้ Quantile Balancing (ไม่ใช่ Top-k routing) — predictor ต้องปรับ
- ต้องมี abstraction layer สำหรับ architecture-specific logic

---

## ADR-003: Product Architecture based on Real Hardware Findings

| รายการ | รายละเอียด |
|--------|-----------|
| **วันที่** | 2026-07-27 |
| **สถานะ** | ✅ Accepted |
| **Context** | หลังจากการ simulation (EXP-001, 002, 003) + real HW benchmark (EXP-004) ได้ empirical evidence ที่ definitive แล้ว — ถึงเวลาออกแบบ product architecture |

### Key Empirical Findings (สรุปจากทุก experiment)

1. **Bottleneck:** K3 on consumer CPU = ~92% compute-bound (815ms compute, 0-67ms I/O stall)
2. **Eviction:** LRU > LFU สำหรับ shared MoE access pattern (93.8% hit at 64MB vs LFU 27.2%)
3. **Buffer size:** 64 MB sufficient (98.9% at 512MB, but 93.8% at 64MB is adequate)
4. **Predictor:** Not critical for throughput. LRU handles temporal locality. Useful for cold start only.
5. **mmap:** OS memory-mapped files provide free "streaming" — our product adds smart prefetching

### การตัดสินใจ (Architecture changes from ADR-001)

| Component | ADR-001 Design | ADR-003 (Real HW) |
|-----------|---------------|-------------------|
| **Buffer eviction** | LRU+priority, 256MB | **LRU plain, 64MB** |
| **Predictor** | MLP (PreScope, 2M params) | **Heuristic only** (frequency + temporal) |
| **Priority boost** | ON | **OFF** (LRU doesn't need it) |
| **Integration** | Fork llama.cpp | **Abstraction layer** + llama-cpp-python adapter |
| **Weight access** | Custom buffer | **mmap** (OS-managed) + smart prefetching |
| **I/O model** | io_uring/IOCP | **PrefetchVirtualMemory** (Windows) / madvise (Linux) |

### Product Architecture

```
weight-streaming (Python package, pip install)
├── core/           → LRU buffer tracker, prefetcher logic
├── backends/       → llama-cpp-python (first), more in future
├── io/             → IOCP (Windows), io_uring (Linux)
└── cli/            → python -m weight_stream ...
```

### Consequences
- ✅ Positive: Ships fast (Python, no C++ build needed on Windows)
- ✅ Positive: Works with any GGUF model, not just K3
- ✅ Positive: mmap = zero-copy weight access
- ⚠️ Negative: Python overhead for buffer tracking (microseconds per access)
- ⚠️ Negative: Relies on OS page cache (less control than custom buffer)
- ⚠️ Negative: Needs Platform-native I/O for best perf (IOCP Windows, io_uring Linux)

### Addendum — First Real-Model Validation (2026-07-29, v0.13.0)

ตรวจสอบกับโมเดลจริงครั้งแรก: `Qwen1.5-MoE-A2.7B` Q2_K (5.48 GB, `qwen2moe`, 60 experts), CPU inference (threads = half of logical cores), 64 GB RAM. Raw data: `docs/verification/items_45_2026-07-29_raw.txt`

| Finding | Value | ยืนยัน / ท้าทาย design |
|---------|-------|------------------------|
| Throughput | 17.9 tok/s (220 tokens / 12.3 s, first token 0.96 s) | ✅ compute-bound prediction ถือจริง |
| `/health` ระหว่าง generate | avg 5.7 ms, max 23.3 ms (58 polls) | ✅ event-loop offload (worker-thread bridge) ทำงาน |
| Page residency ระหว่าง generate | 4.6% ของโมเดล (0.25 / 5.48 GB) | ✅ mmap + OS page cache ประคอง throughput ได้ด้วย resident set เล็กมาก |
| Cancellation | หยุดใน 0.73 s (8 tokens), lock ปล่อย, regen ทันที | ✅ cooperative stop ผ่าน queue sentinel ใช้ได้จริง |
| Buffer tracker | `total_accesses = 0` | ⚠️ **Gap**: tracker มองไม่เห็นการอ่าน mmap ของ llama.cpp — input ของ buffer-abstraction prototype (TASKS.md Phase 3) |
| Chat template | native `create_chat_completion` ถูกต้อง (Qwen); Llama-family ยังไม่ได้ทดสอบในเครื่อง | 🟡 fallback formatter คงไว้ |

**ไม่เปลี่ยน architecture** — gap ข้อบนเป็นงานถัดไป ไม่ใช่เหตุผลให้ revisit decision นี้

**อัปเดต (2026-07-30):** spike `scripts/spike_page_faults.py` ยืนยันช่อง telemetry ระดับ OS — page-fault demand ระหว่าง generate จริง: cold ≈ 175 MB/token → warm ≈ 0.55 MB/token (ลด 300×) ⇒ OS working set ถือ hot set ไว้ได้จริง (หลักฐานจริงเพิ่มให้ข้อสรุป "predictor ไม่ critical"); `generation.paging` (faults, faults/token, MB/token) ถูกบันทึกใน `stream_chat()`/`generate()` และออกทาง `/v1/stats` แล้ว — gap ปิดในระดับ telemetry; การ track ระดับ shard ยังเป็นงานของ native core ในอนาคต

---

> **Template:**
> ```markdown
> ## ADR-NNN: หัวข้อ
>
> | รายการ | รายละเอียด |
> |--------|-----------|
> | **วันที่** | YYYY-MM-DD |
> | **สถานะ** | ✅ Accepted / 🔄 Proposed / ❌ Superseded |
> | **Context** | ปัญหาหรือสถานการณ์ |
>
> ### ตัวเลือกที่พิจารณา
> - ตัวเลือก A: ...
> - ตัวเลือก B: ...
>
> ### การตัดสินใจ
> เลือก ... เพราะ ...
>
> ### เหตุผล
> 1. ...
> 2. ...
>
> ### Consequences
> - ✅ Positive: ...
> - ⚠️ Negative: ...
>
> ### Revisit เมื่อ
> - เงื่อนไขที่ทำให้ decision นี้ต้อง reappraise
> ```

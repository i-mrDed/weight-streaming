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

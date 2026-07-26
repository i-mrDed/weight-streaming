# Speculative Weight Streaming — Concept

> **บันทึกแนวคิดจากการสนทนา 2026-07-27 / ปรับปรุง 2026-07-27**  
> ที่มา: ต้องการรันโมเดลภาษาขนาดใหญ่ (100B–3T+) บนเครื่องทั่วไป RAM 32–64 GB  
> โดยไม่ต้องโหลด weights ทั้งหมดเข้า RAM แต่ใช้ predictive streaming จาก NVMe แทน  
>
> *เป้าหมาย: ครอบคลุมทุกรูปแบบ (MoE, Dense, Hybrid) — เริ่มต้นที่ Kimi K3 (2.8T, MoE)*

---

## สารบัญ

- [1. ที่มาและแรงบันดาลใจ](#1-ที่มาและแรงบันดาลใจ)
- [2. ปัญหาหลัก](#2-ปัญหาหลัก)
- [3. แนวคิดใหม่ — Paradigm Shift](#3-แนวคิดใหม่--paradigm-shift)
- [4. Speculative Weight Streaming — รายละเอียด](#4-speculative-weight-streaming--รายละเอียด)
- [5. Feasibility Analysis](#5-feasibility-analysis)
- [6. แนวทางเสริม](#6-แนวทางเสริม)
- [7. สิ่งที่ "ยังไม่มีใครทำ" (Novel Contributions)](#7-สิ่งที่-ยังไม่มีใครทำ-novel-contributions)
- [8. คำถามเปิด (Open Problems)](#8-คำถามเปิด-open-problems)
- [9. แผนงานวิจัย](#9-แผนงานวิจัย)
- [10. แนวคิดเพิ่มเติมระหว่างคุย](#10-แนวคิดเพิ่มเติมระหว่างคุย)

---

## 1. ที่มาและแรงบันดาลใจ

วันที่ **27 กรกฎาคม 2026** Moonshot AI ปล่อย open weights ของ **Kimi K3** — โมเดล 2.8T parameters (Mixture-of-Experts, 896 experts, 16 active ต่อ token) พร้อม 1M context window, native vision, และ open license ที่ HuggingFace

ทำให้เกิดคำถาม: **ถ้าเราสามารถรันโมเดลนี้บนเครื่องทั่วไป (RAM 32–64 GB) ได้ แม้จะช้าหน่อย — มันจะเปิดความเป็นไปได้อะไรบ้าง?**

ปัจจุบันโครงสร้างพื้นฐานที่ต้องใช้รันโมเดลขนาดนี้:

| ตัวเลือก | VRAM/RAM ที่ต้องการ | ราคาโดยประมาณ |
|----------|-------------------|--------------|
| 8x H100 (80GB) | 640 GB VRAM | ~$200,000 |
| Mac Ultra (192GB) | 192 GB RAM | ~$8,000 |
| **แนวทางใหม่ของเรา** | **32–64 GB RAM + NVMe** | **~$1,500** |

---

## 2. ปัญหาหลัก

### 2.1 Weight size exceeds RAM

**ปัญหาเป็นสากลสำหรับโมเดลใหญ่ทุกประเภท:**

| Precision | K3 (2.8T, MoE) | Llama-class (100B-400B, Dense) |
|-----------|----------------|-------------------------------|
| FP32 | 11.2 TB ❌ | 400 GB–1.6 TB ❌ |
| FP16/BF16 | 5.6 TB ❌ | 200 GB–800 GB ❌ |
| FP8 | 2.8 TB ❌ | 100 GB–400 GB ❌ |
| MXFP4 (4-bit) | 1.4 TB ❌ | 50 GB–200 GB ❌ |
| 2-bit | 700 GB ❌ | 25 GB–100 GB ❌ |

> RAM 32–64 GB ของเครื่องทั่วไป **ไม่พอสำหรับทั้ง MoE และ Dense** ที่ scale เกิน 100B

### 2.2 Architecture-specific challenges

**MoE (เช่น K3):** sparsity ช่วยลด compute แต่ไม่ลด memory — 896 experts ทั้งหมดยังต้อง accessible

**Dense:** ไม่มี expert routing ให้ใช้ลด bandwidth — ต้องโหลดทั้ง layer หรือ shard

แม้ K3 จะเปิดแค่ 16/896 experts ต่อ token แต่ weights **ทั้งหมด 896 experts** ยังคงต้องถูก accessible — เพราะ API call ต่อๆ ไปอาจเรียก expert คนละชุด

### 2.3 วิธีการที่มีอยู่ไม่ดีพอ

| วิธี | ปัญหา |
|-----|-------|
| mmap (llama.cpp) | Page fault → disk I/O → stall → inference ช้ามาก |
| Swap | OS-level swapping ไม่รู้ MoE topology → prefetch ไม่เป็น |
| Offload (GPU→RAM→Disk) | Layer-by-layer ยังต้องมี weights ใน GPU/RAM อย่างน้อยพอให้รัน 1 forward pass |

---

## 3. แนวคิดใหม่ — Paradigm Shift

### จาก

```
Load-All → Execute
```

### เป็น

```
Predict → Pre-fetch → Stream → Execute
```

**หัวใจสำคัญ:** เปลี่ยนจาก **reactive loading** (รอให้โปรแกรมเรียก แล้วค่อยโหลด → เกิด stall)  
เป็น **predictive/preemptive loading** (เดาล่วงหน้าว่าจะใช้ weights ไหน → โหลดมาก่อน → พร้อมเมื่อถึงเวลา)

---

## 4. Speculative Weight Streaming — รายละเอียด

### 4.1 ภาพรวมสถาปัตยกรรม (MoE case — K3)

```
┌──────────────────────────────────────────────────────────────┐
│ RAM (32-64 GB)                                                │
│                                                              │
│  ┌──────────────────┐     ┌─────────────────────────────┐    │
│  │ Draft Model (3B) │     │ Weight Predictor             │    │
│  │ ─────────────── │     │ ───────────────────────── │    │
│  │ • Speculative    │────→│ • รับ candidate tokens      │    │
│  │   decoding       │     │ • Predict experts/shard    │    │
│  │ • Generate next  │     │ • Priority queue           │    │
│  │   5-10 tokens    │     │ • Dispatch pre-fetch        │    │
│  └──────────────────┘     └──────────┬──────────────────┘    │
│                                      │                       │
│                                      ▼                       │
│  ┌──────────────────────────────────────────────────────┐    │
│  │ Streaming Buffer (~256 MB–1 GB)                      │    │
│  │ ──────────────────────────                           │    │
│  │ • Hot weights (สำหรับ ~10 tokens ข้างหน้า)             │    │
│  │ • LRU eviction                                       │    │
│  │ • 70-90% hit rate (target)                           │    │
│  └──────────────────────┬───────────────────────────────┘    │
│                         │                                    │
└─────────────────────────┼────────────────────────────────────┘
                          │ compute
                          ▼
┌──────────────────────────────────────────────────────────────┐
│ NVMe SSD (2-4 TB)                                             │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐    │
│  │ Model Weights (MXFP4, 0.5–1.4 TB)                    │    │
│  │ ─────────────────────────                              │    │
│  │ • Sharded by expert/layer/shard                       │    │
│  │ • Sequential-layout optimized                         │    │
│  │ • Metadata: weight → offset index                     │    │
│  └──────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────┘
```

### 4.2 ส่วนประกอบหลัก

#### Layer 1: Draft Model (3–7B)

- อยู่ใน RAM ตลอด (RAM ที่ใช้ ~6–14 GB)
- ทำ **speculative decoding** — generate candidate tokens (5–10 tokens)
- **หน้าที่เพิ่มเติมนอกเหนือจาก speculative decode ปกติ:**
  - **MoE:** เก็บ state เพื่อคาดการณ์ **experts** ที่มีโอกาสถูกเรียก
  - **Dense:** คาดการณ์ **layer/shard** access pattern
  - ส่ง prediction ไปให้ Weight Predictor

#### Layer 2: Weight Predictor + Pre-fetch Scheduler

- **Input:** Candidate tokens sequence จาก Draft Model + attention logits
- **Prediction model:** อาจใช้:
  - วิเคราะห์ expert routing logits (MoE) หรือ hidden state patterns (Dense)
  - Small MLP ที่ train เพื่อ predict activation patterns
  - Heuristic-based: usage frequency, temporal locality
- **Output:** ลำดับ weights ที่ควร pre-fetch + priority
- **Scheduler:**
  - จัดคิว I/O request ตาม priority
  - Batch requests ที่อยู่ติดกันใน NVMe (sequential read → bandwidth 14 GB/s)
  - **Early fetch:** โหลดเมื่อเหลือ token gap ที่กำหนด (e.g., 3 tokens ก่อนถึง)

#### Layer 3: Streaming Buffer (RAM ~256 MB–1 GB)

- **Buffer pool:** จอง RAM ~256 MB (MoE) ถึง ~1 GB (Dense) สำหรับ weights ที่ถูก pre-fetch มา
- **Unit of caching:** 1 expert/layer/shard → scale ตาม architecture
- **Eviction:** LRU + priority-based — weights ที่จะใช้ใน token ถัดไป อยู่ใน hot set
- **Miss handling:** ถ้าเกิด miss → fallback เป็น mmap (reactive) แต่คาดหวังว่าน้อยครั้ง
- **Execution:** Read from buffer directly (no disk I/O during compute)

### 4.3 Flow การทำงาน (step-by-step — MoE case)

```
1. Draft Model generate token T+1, T+2, ..., T+N (speculative)
   ↓
2. Weight Predictor วิเคราะห์ → expert #12, #45, #67, #89 จะถูกเรียก
   ↓
3. Scheduler ตรวจสอบ buffer → #12, #45 มีแล้ว → ขอ pre-fetch #67, #89
   ↓
4. NVMe อ่าน expert weights #67, #89 (~6 MB) → buffer → ~0.4 ms
   ↓
5. Main Model execute token T+1 → ใช้ #12, #45 from buffer ✅
   ↓
6. (while main model compute) Draft Model + Predictor ทำงานล่วงหน้าขนาน
   ↓
7. Loop กลับไป step 1
```

> **Dense case:** Flow คล้ายกัน แต่ unit เป็น "layer shard" แทน "expert" — pre-fetch layer weights ล่วงหน้า 2-3 layers

**Key insight:** Draft model + prediction + I/O ทำงาน **overlap** กับ main model compute — latency ซ่อนกัน

---

## 5. Feasibility Analysis

> ⚠️ ตัวเลขด้านล่างเป็นกรณีศึกษาเฉพาะ **K3 (MoE)** — Dense model จะมี bandwidth requirement สูงกว่า

### 5.1 Bandwidth Budget (K3 case)

| Component | Value |
|-----------|-------|
| NVMe PCIe 5.0 sequential read | ~14 GB/s |
| NVMe PCIe 5.0 random read (4KB) | ~7 GB/s |
| Large read (256KB+) | near sequential |
| Expert size (1 layer, MXFP4, 8B active expert) | ~4 MB |
| Experts needed per token | 16 |
| Total weight read per token (buffer miss scenario) | 64 MB worst case |
| **Target latency per token** | **< 500 ms** |
| **Bandwidth needed** | **64 MB / 500 ms = 128 MB/s** ✅ |
| NVMe actual capacity | **7,000–14,000 MB/s** → **เหลือเฟือ 50–100x** |

**สรุป K3:** Bandwidth **ไม่ใช่ bottleneck** — ประเด็นคือ **latency hiding** ต่างหาก

**หมายเหตุ Dense model:** ถ้าเป็น dense ขนาด 100B FP8 (~100 GB), ต้องโหลด 1 layer (~1-2 GB) ต่อ token → bandwidth ที่ต้องการสูงกว่า และอาจต้องใช้ buffer ขนาดใหญ่ขึ้นหรือกลยุทธ์ต่างออกไป

### 5.2 Latency Budget

```
Token timeline (target per token < 500 ms):

  Draft Model:       ██░░░░░░░░   ~50 ms
  Predictor:          ░█░░░░░░░░  ~10 ms  
  I/O (pre-fetch):    ░░████░░░░  ~50 ms (overlapped)
  Main Model:         ░░░░██████  ~300 ms
                      ──────────
  Total wall clock:   ~350 ms  ✅
```

### 5.3 Memory Budget

| Component | RAM Usage | ใน 32GB | ใน 64GB |
|-----------|-----------|---------|---------|
| Draft Model (3B, FP16) | ~6 GB | ✅ | ✅ |
| Weight Predictor | ~1 GB | ✅ | ✅ |
| Streaming Buffer | ~256 MB | ✅ | ✅ |
| KV Cache (1M context, 16 active experts) | ~8 GB | ✅ | ✅ |
| System/OS | ~4 GB | ✅ | ✅ |
| **รวม** | **~19 GB** | **เหลือ 13 GB** | **เหลือ 45 GB** |

---

## 6. แนวทางเสริม

### 6.1 Computational Storage (Near-Storage Computing)

แนวคิดที่ต่างออกไป: **ย้าย compute ไปอยู่ที่ SSD**

```
SSD Controller Board
├── Flash Chips (weights 1.4 TB)
├── FPGA / NPU (ชิปเล็กๆ พลังงานต่ำ)
│   ├── weights อยู่ใน flash — ไม่ต้อง load เข้า host RAM
│   ├── host ส่งคำขอ: "ให้ expert #45, layer 3 × vector X"
│   ├── FPGA ทำ matrix-vector multiply บน SSD เลย
│   └── ส่งผลลัพธ์กลับ (~4 KB)
│
└── Host RAM ใช้แค่ result buffer (~256 MB)
```

**ข้อดี:**
- ไม่ต้องโหลด weights เข้า RAM เลย — ประหยัด bandwidth และ energy
- Latency ต่ำ (internal bus ภายใน SSD)
- แต่ละ SSD expert shard กัน → parallel ได้หลายตัวพร้อมกัน

**ข้อเสีย:**
- ต้องออกแบบ hardware
- FPGA compute power จำกัด
- ต้อง custom SSD controller

### 6.2 Collaborative Inference

ต่อ **หลายเครื่องในบ้าน/ออฟฟิศ** ด้วยกัน:

```
┌──────────┐     ┌──────────┐     ┌──────────┐
│ PC #1    │     │ PC #2    │     │ PC #3    │
│ 64GB RAM │     │ 64GB RAM │     │ 64GB RAM │
│ Expert   │ ←──→│ Expert   │ ←──→│ Expert   │
│ pool A   │     │ pool B   │     │ pool C   │
│ (300     │     │ (300     │     │ (296     │
│ experts) │     │ experts) │     │ experts) │
└────┬─────┘     └────┬─────┘     └────┬─────┘
     │                │                │
     └────────────────┼────────────────┘
                      │
              ┌───────┴───────┐
              │ Orchestrator  │
              │ (Desktop #0)  │
              │ Draft Model   │
              │ + Predictor   │
              └───────────────┘
```

**ข้อดี:** ใช้ hardware ที่มีอยู่, โมเดลทั้งตัว accessible พร้อมกัน  
**ข้อเสีย:** Network latency, complexity เพิ่มขึ้นหลายเท่า

### 6.3 MoE-specific Compression

- **Adaptive precision:** Expert ที่เรียกบ่อย (hot) → FP8/FP16, Expert ที่เรียกนานๆ ครั้ง (cold) → MXFP4 หรือ 2-bit
- **Expert pruning:** Expert routing logits analysis → prune experts ที่ไม่ค่อยได้ใช้
- **Distillation:** Train 3B draft model กับ K3 raw logits → improve prediction accuracy

---

## 7. สิ่งที่ "ยังไม่มีใครทำ" (Novel Contributions)

1. **Weight-aware speculative decoding** — draft model ไม่ได้แค่ predict tokens แต่ยัง predict weight access pattern (expert routing / layer activation)
2. **Structure-aware pre-fetch scheduler** — I/O scheduler ที่เข้าใจ topology ของ model (MoE routing / Dense layer graph)
3. **Streaming execution engine** — compute engine ที่ทำงานได้จาก buffer ที่ weight อาจมาไม่พร้อมกัน (partial availability)
4. **Unified architecture** — รวม speculative decoding + weight streaming + architecture-aware optimization เข้าด้วยกันในระบบเดียว
5. **Cross-architecture weight streaming** — framework เดียวกันปรับใช้ได้ทั้ง MoE และ Dense model

---

## 8. คำถามเปิด (Open Problems)

### 8.1 Accuracy ของ Weight Predictor
- Draft model จะ predict ได้แม่นขนาดไหน?
- MoE: expert routing prediction → hit rate?
- Dense: layer activation prediction → มี sparsity ให้ exploit ไหม?
- ถ้า predict ผิด → miss → stall → latency spike
- **ต้องวัด:** hit rate → latency distribution → usability

### 8.2 Buffer Management
- ขนาด buffer ที่เหมาะสม? (MoE: ~256 MB, Dense: ~1 GB?)
- Eviction policy: LRU? LFU? Priority-based?
- Cold start: tokens แรกจะช้ามากไหม?
- Dense model: ต้อง pre-fetch ทั้ง layer หรือ shard บางส่วน?

### 8.3 Draft Model Selection
- ใช้ distilled version ของ main model (ถ้ามี)?
- Train predictor โดยเฉพาะ (small MLP)?
- หรือใช้ heuristic (frequency-based)?
- Dense case: draft model จะ predict layer access pattern ได้ไหม?

### 8.4 NVMe Endurance
- อ่านหลาย TB ซ้ำๆ ตลอดอายุการใช้งาน
- SSD TBW (Total Bytes Written): ปกติวัดที่ **write** — read ไม่นับ
- แต่ **read-intensive** ก็มีผลต่ออายุเช่นกัน
- ต้องคำนวณ: hours of inference × read rate = ?

### 8.5 mmap vs Custom I/O
- mmap + madvise + prefault → พอเพียงหรือต้อง custom I/O engine?
- io_uring (Linux) → asynchronous I/O ที่ overlap กับ compute ได้ดี
- Windows/IOCP → ต้อง manage ยังไง?

### 8.6 Evaluation Metrics
- ไม่ใช่แค่ tokens/second — ต้องวัด **inter-token latency distribution** และ **user-perceived responsiveness**
- เปรียบเทียบระหว่าง MoE vs Dense architecture กับ framework เดียวกัน

---

## 9. แผนงานวิจัย

### Phase 1: Research Review (Proposed)
- Survey: งานวิจัยเกี่ยวกับ speculative decoding, weight prediction, out-of-core execution, near-storage computing
- **K3 focus:** วิเคราะห์ K3 architecture: expert routing pattern, activation sparsity
- **General:** ดู Dense model behavior — layer activation patterns, attention sparsity
- ดู patents/literature ว่าใกล้เคียงกับแนวทางนี้หรือไม่

### Phase 2: Simulation
- สร้าง simulator ที่จำลอง K3 MoE topology
- ทดสอบ prediction algorithm, buffer policy, scheduler
- Metrics: hit rate, avg latency, p95 latency, stall frequency

### Phase 3: Prototype
- Use smaller MoE model (e.g., Mixtral 8x7B, Qwen2 MoE)
- จำลอง disk latency ด้วย file read delay
- Build real streaming inference engine

### Phase 4: Evaluation
- Benchmark กับ real workloads
- เปรียบเทียบกับ mmap baseline
- วัด power, latency, memory, disk wear

### Phase 5: Publication
- Paper / technical report
- Open source prototype

---

## 10. แนวคิดเพิ่มเติมระหว่างคุย

- **"Execute from streaming buffer"** — compute engine ไม่รอให้ weights มา 100% — เริ่มคำนวณส่วนที่พร้อมได้เลย (partial compute)
- **Draft model architecture:** ใช้ model ที่เล็กกว่า (3B) ที่ train โดยเฉพาะให้ predict expert routing + generate speculative tokens
- **Collaborative inference:** ใช้หลายเครื่องในบ้าน (LAN) แบ่ง experts กัน — orchestrated โดย desktop หลัก
- **Near-storage compute:** FPGA ที่ SSD สำหรับ matrix-vector multiply — ลด data movement ลงอย่างมาก
- **Adaptive precision quantization:** Experts ต่างกันใช้ bit-width ต่างกันตามความถี่ที่ถูกเรียก

---

*บันทึกจาก session: 2026-07-27 | Initiator: user + opencode*

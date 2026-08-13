# Speculative Weight Streaming

> **แนวคิด:** รันโมเดลภาษาขนาดใหญ่ (100B–3T+ parameters) บนเครื่องทั่วไป (RAM 32–64 GB)  
> โดยไม่ต้องโหลด weights ทั้งหมดเข้า RAM — ใช้ predictive streaming จาก NVMe แทน  
>
> *เป้าหมาย: ครอบคลุมโมเดลใหญ่ทุกรูปแบบ (dense, MoE, hybrid)*  
> *เริ่มต้นที่: Kimi K3 (2.8T params, MoE, open weights July 2026)*  
>
> **สถานะปัจจุบัน (2026-08-10):** จากแนวคิดสู่แพลตฟอร์มจริง — ดู [README.md](README.md) (ภาพรวม + ผลวัดจริง EXP-012) และ [research/HARDWARE_100TPS_PLAN.md](research/HARDWARE_100TPS_PLAN.md) (แผน hardware). เอกสารนี้คือ vision เริ่มต้น — ส่วนที่ build-as-designed แยกไว้ใน [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) §0

---

## สารบัญ

- [1. ปัญหา](#1-ปัญหา)
- [2. แนวคิดหลัก](#2-แนวคิดหลัก)
- [3. สถาปัตยกรรมเบื้องต้น](#3-สถาปัตยกรรมเบื้องต้น)
- [4. แนวทางเสริม](#4-แนวทางเสริม)
- [5. คำถามเปิด](#5-คำถามเปิด)
- [6. แผนงาน](#6-แผนงาน)

---

## 1. ปัญหา

| อุปสรรค | รายละเอียด |
|---------|-----------|
| **Weight size** | โมเดลใหญ่ (100B–3T+) → หนักตั้งแต่ 50 GB ถึง ~1.4 TB (MXFP4) |
| **RAM จำกัด** | เครื่องทั่วไปมี 32–64 GB — ไม่พอโหลดทั้งก้อน |
| **MoE sparsity** | เช่น K3: 896 experts, 16 active/token → 8/9 ไม่ได้ใช้ในแต่ละ step |
| **Dense ก็ไม่เว้น** | โมเดล dense 100B+ ยังต้องใช้ RAM เกินกว่าที่เครื่องทั่วไปมี |
| **แนวทางปัจจุบัน** | mmap (reactive page fault) → I/O-bound inference → ช้ามาก |

**เป้าหมายระยะยาว:** Inference บนโมเดลใหญ่ (100B–3T+ parameters, ทุกสถาปัตยกรรม) โดยใช้ RAM 32–64 GB + NVMe SSD  
**เป้าหมายระยะสั้น (K3):** Inference บน Kimi K3 2.8T โดยใช้ RAM 32–64 GB + NVMe SSD  
**โดยที่ความเร็วพอใช้งานได้ (< 5–10 วินาทีต่อ token ชุดแรก)**

---

## 2. แนวคิดหลัก

### Paradigm Shift

```
❌  Load-All → Execute          (แนวทางปัจจุบัน)
✅  Predict → Pre-fetch → Stream → Execute   (แนวทางใหม่)
```

### Speculative Weight Streaming

รวม 3 เทคโนโลยีเข้าด้วยกันในรูปแบบที่ไม่เคยมีมาก่อน — ออกแบบให้ใช้งานได้กับ **ทั้ง MoE และ Dense** model:

#### Layer 1: Draft Model (3–7B) ← อยู่ใน RAM ตลอด
- รัน speculative decoding ตามปกติ
- **แต่เพิ่ม:** Predict ว่า weights (experts/layers/attention projection) ไหนจะถูกเรียกสำหรับ token ถัดไป

> **MoE case:** Predict expert routing (เช่น K3: 16/896 experts)  
> **Dense case:** Predict layer activation patterns, หรือ split model เป็น shards และ predict shard access pattern

#### Layer 2: Weight Predictor + Pre-fetch Scheduler
- รับ prediction จาก draft model
- จัด priority queue ของ weights ที่ต้องใช้
- **Pre-fetch จาก NVMe → buffer RAM ขนาด ~256 MB–1 GB** ก่อนที่ main model จะเรียกถึง
- *ขนาด buffer ปรับตาม architecture (MoE → smaller buffer, Dense → larger buffer)*

#### Layer 3: Main Model (execution from streaming buffer)
- Main model weights อยู่บน NVMe ตลอด — ไม่เคยโหลดทั้งหมดเข้า RAM
- Execute จาก buffer ที่ pre-fetch ไว้
- ล้าง buffer ทันทีเมื่อใช้งานเสร็จ → reuse space

---

## 3. สถาปัตยกรรมเบื้องต้น

```
┌─────────────────────────────────────────────────────────┐
│ RAM — 32-64 GB                                          │
│                                                         │
│  ┌──────────┐    ┌──────────────┐    ┌───────────────┐  │
│  │ Draft     │    │ Weight       │    │ Streaming     │  │
│  │ Model     │───→│ Predictor    │───→│ Buffer        │  │
│  │ (3B)      │    │ (priority    │    │ (~256 MB)     │  │
│  │           │    │  queue)      │    │               │  │
│  └──────────┘    └──────┬───────┘    └───────┬───────┘  │
│                         │                    │          │
└─────────────────────────┼────────────────────┼──────────┘
                          │ pre-fetch          │ compute
                          ▼                    ▼
┌─────────────────────────────────────────────────────────┐
│ NVMe SSD — 2-4 TB                                       │
│                                                         │
│  ┌──────────────────────────────────────────────────┐   │
│  │  K3 Weights (1.4 TB)  [Experts sharded by layer] │   │
│  │  Layout optimized for sequential read patterns    │   │
│  └──────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

### ตัวเลข feasibility (K3 case)

| Metric | ค่า |
|--------|-----|
| NVMe PCIe 5.0 sequential read | ~14 GB/s |
| NVMe PCIe 5.0 random read | ~7 GB/s |
| 16 experts size (MXFP4) | ~48 MB |
| Draft model generate 5 tokens | ~200 ms |
| **Bandwidth ที่ต้องการ** | **48 MB / 200 ms = 240 MB/s** |
| NVMe ทำได้จริง | 7,000–14,000 MB/s ✅ |
| **Buffer reuse rate** | 70–90% (ถ้า prediction accuracy สูง) |

> ⚠️ ตัวเลขนี้เป็นกรณี K3 — สำหรับ dense model (ไม่มี expert sparsity) bandwidth ที่ต้องการจะสูงกว่า และต้องใช้กลยุทธ์ pre-fetch ต่างออกไป (เช่น layer-wise streaming, activation checkpointing ร่วมด้วย)

---

## 4. แนวทางเสริม

### 4.1 Computational Storage (Near-Storage Computing)

ย้าย compute ไปที่ SSD:
```
SSD Controller
├── Flash (weights 2.8T)
├── FPGA/NPU ชิปเล็กๆ
│   └── ทำ matrix-vector multiply ที่ SSD
│       → ส่งผลลัพธ์กลับมา (~KB)
└── ไม่ต้องโหลด weights เข้า RAM เลย
```

### 4.2 Collaborative Inference

ใช้หลายเครื่องในบ้าน/ออฟฟิศ ต่อกันด้วย high-speed network:
- แบ่ง experts กันคนละส่วน
- Orchestrator จัดสรร token → expert → เครื่องที่ถูกต้อง
- เหมาะกับ MoE โดยธรรมชาติ

### 4.3 Model-specific Compression

- **MoE:** Quantization เฉพาะ expert (บาง expert quantize หนักกว่าได้), Pruning experts ที่ซ้ำซ้อน, Adaptive precision
- **Dense:** Layer pruning, Mixed-precision (layers ท้ายๆ quantize หนักกว่า), Knowledge distillation
- **Cross-architecture:** Adaptive precision — weights ที่เรียกบ่อย → FP8, เรียกนานๆ ครั้ง → MXFP4 หรือ 2-bit

---

## 5. คำถามเปิด (Open Problems)

1. **Accuracy ของ weight predictor** — draft model จะ predict ได้แม่นขนาดไหนว่า experts ไหนจะถูกเรียก?
2. **Buffer management** — ขนาด buffer ที่เหมาะสม? Eviction policy แบบไหน?
3. **Latency hiding** — จะ overlap I/O กับ computation ได้ดีแค่ไหน?
4. **Draft model design** — ใช้ model เดิมที่เล็กกว่า หรือ train predictor โดยเฉพาะ?
5. **NVMe endurance** — อ่าน weights ซ้ำๆ 1.4 TB จะทำให้ SSD ตายเร็วไหม?
6. **Memory-mapped ใหม่** — mmap ตัวปัจจุบันช้าเพราะ page fault → ถ้า prefetch ถูกต้อง mmap ก็ใช้ได้?

---

## 6. แผนงาน (เสนอ)

| Phase | หัวข้อ | รายละเอียด |
|-------|--------|-----------|
| 1 | **Research Review** | หางานวิจัย/patents ที่ใกล้เคียง — ดูว่ามีใครทำอะไรไปแล้วบ้าง |
| 2 | **Architecture Design** | ออกแบบระบบเต็ม: data layout, scheduler, buffer mgmt, execution engine |
| 3 | **Prototype** | สร้าง proof-of-concept ด้วยโมเดล MoE เล็ก + NVMe simulation |
| 4 | **Evaluation** | ทดสอบกับ real workload — latency, throughput, accuracy |
| 5 | **Paper / Research** | บันทึกผล — contribution ที่ "ยังไม่มีใครทำ" |

---

*เริ่มต้น: 2026-07-27*

---

## 📁 โครงสร้าง

```
~/weight-streaming/
│
├── PROJECT.md            ← ไฟล์นี้
├── CHANGELOG.md          ← บันทึกความคืบหน้า
│
├── docs\
│   ├── CONCEPT.md        ← Concept ฉบับสมบูรณ์ (บันทึกการสนทนา)
│   └── ...               ← ADRs, architecture diagrams, notes
│
└── research\             ← งานวิจัย/paper notes/references
    └── README.md         ← ไว้ใส่ reference ภายหลัง
```

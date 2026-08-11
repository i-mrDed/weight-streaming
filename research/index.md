# Research Index — Speculative Weight Streaming

> **Phase 1 Complete — 2026-07-27**  
> Survey งานวิจัย 4 หมวดหลัก + Kimi K3 architecture

---

## 📊 สรุปภาพรวม

| หมวด | # Papers | Relevance | Key Insight |
|------|---------|-----------|-------------|
| [Speculative Decoding](./speculative-decoding/) | 8+ | 🟢 สูงมาก | EAGLE-3 คือ SOTA — draft head แทน draft model เต็ม |
| [MoE Routing Prediction](./moe-routing/) | 10+ | 🟢 สูงมาก | Expert activation prediction 90%+ accuracy มีงานทำแล้ว |
| [Out-of-Core Execution](./out-of-core-execution/) | 8+ | 🟢 สูงมาก | SSD streaming สำหรับ MoE มี PoC จริง (1.9–4.4 tok/s) |
| [Near-Storage Computing](./near-storage-compute/) | 5+ | 🟡 ปานกลาง | ยังเน้น CNN/GNN แต่มีแนวโน้มมา LLM |
| [Kimi K3 Architecture](./kimi-k3/) | — | 🔵 กรณีศึกษา | 896 experts, KDA, MXFP4, ~50B active/token |

---

## 🔗 Key Findings ที่ส่งผลต่อ Speculative Weight Streaming

### 1. Draft Model → **EAGLE-3 Architecture**
- ไม่ต้องใช้ draft model แยก — ใช้ lightweight draft head (~1 layer + projections)
- Multi-layer feature fusion, scaling law สำหรับ training data
- **启示:** Draft model ในระบบเราสามารถเป็น EAGLE-3-style head แทน 3B model เต็ม

### 2. Expert Prediction → **มีงานทำแล้ว 90%+ accuracy**
- PreScope: LLaPor predictor → Top-4 accuracy >90%
- DuoServe-MoE: MLP predictor สำหรับ decode stage
- MoE-prefetching (SNU): Fine-tune gate layer เพื่อ predict expert ใน decoder ถัดไป
- **启示:** Weight predictor เป็น可行性สูง — ไม่ใช่ส่วนที่ยากที่สุดของระบบ

### 3. SSD Streaming → **มี PoC จริงใน Production**
- llama.cpp + mmap: ใช้ได้จริงบน Windows (1.5 GB/s NVMe → 2.5–4.3 tok/s)
- flash-moe: 48GB MacBook → 4.4 tok/s กับ 397B model
- DeepSeek-V4-Flash Strix Halo: 64GB → 1.9 tok/s กับ 284B MoE
- **启示:** SSD streaming ใช้ได้จริง แต่ speed ยังไม่ถึงเป้า (< 5 tok/s)

### 4. Energy → **เป็นข้อจำกัดสำคัญ**
- SSD offloading → energy เพิ่ม 12x vs HBM
- แต่สำหรับ edge/batch size เล็ก → MoE sparsity + Flash อนาคต = viable

### 5. K3 Architecture → **เหมาะกับแนวทางเรามาก**
- 896 experts, 16 active → sparsity 1.8%
- 16 experts per token = ~48 MB → bandwidth requirement ต่ำ
- MXFP4 weights → ขนาดเล็กลงอีก

---

## 📁 โครงสร้าง

```
research/
├── index.md                            ← ไฟล์นี้
├── speculative-decoding/               ← Speculative decoding
│   └── README.md
├── moe-routing/                        ← Expert routing prediction
│   └── README.md
├── out-of-core-execution/              ← Weight offloading / SSD streaming
│   └── README.md
├── near-storage-compute/               ← Computational storage
│   └── README.md
├── kimi-k3/                            ← Kimi K3 architecture
│   └── README.md
└── writeups/                           ← บทเรียน + writeups (ดูด้านล่าง)
```

---

## 📌 บทเรียน (Lessons)

- [2026-08-11 — Tests ที่ผ่าน local แต่แดงบน CI (machine-dependent test)](./2026-08-11-lesson-ci-hermetic-tests.md)

---

## 📝 TODO: Phase 1b

- [ ] อ่านรายละเอียด PreScope paper (arXiv 2509.23638)
- [ ] อ่านรายละเอียด EAGLE-3 paper (arXiv 2503.01840)
- [ ] ทดสอบ llama.cpp expert offloading จริง (ถ้ามี hardware)
- [ ] วิเคราะห์ K3 routing pattern (เมื่อ weights เปิด)

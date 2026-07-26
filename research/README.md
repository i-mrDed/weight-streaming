# Research — Speculative Weight Streaming

> **ที่เก็บ paper notes, reference links, และการสำรวจวรรณกรรมที่เกี่ยวข้อง**  
> ✅ Phase 1: Research Review — **เสร็จสมบูรณ์ (2026-07-27)**

---

## 📂 โครงสร้าง

```
research/
├── README.md                           ← ไฟล์นี้
├── index.md                            ← สรุปรวมทุกหมวด + key findings
│
├── speculative-decoding/               ← งาน speculative decoding
│   └── README.md                       ← EAGLE-3, Medusa, CoS, etc.
│
├── moe-routing/                        ← Expert routing prediction
│   └── README.md                       ← PreScope, DuoServe-MoE, MoE-prefetching
│
├── out-of-core-execution/              ← Weight offloading / SSD streaming
│   └── README.md                       ← llama.cpp, flash-moe, MoE-Infinity
│
├── near-storage-compute/               ← Computational storage
│   └── README.md                       ← HILOS, SmartSSD, HolisticGNN
│
└── kimi-k3/                            ← Kimi K3 architecture
    └── README.md                       ← Specs, architecture, feasibility
```

---

## 🔑 Key Takeaways (ฉบับรวบรัด)

### ✅ Strong Signal — ไปต่อได้
1. **Speculative decoding** สุกงอม (EAGLE-3) — draft head <5% params
2. **Expert routing prediction** accuracy >90% ด้วย MLP เล็ก
3. **SSD streaming** ใช้ได้จริง (1.9-4.4 tok/s) แต่ยัง reactive
4. **K3 spec** เหมาะกับแนวทาง — MXFP4, 16 experts, KDA ลด KV cache

### ⚠️ Risk / Open Problems
1. **Speed ยังไม่ถึงเป้า** — ต้อง predictive แทน reactive mmap
2. **Energy** — SSD offloading เปลืองไฟ แต่ desktop ≠ data center
3. **K3 routing** — Quantile Balancing ≠ Top-k → predict ต่างออกไป
4. **Windows** — ไม่มี io_uring ต้องใช้ IOCP หรือ overlapped I/O

### 🆕 Novel Opportunity
> **ไม่มีงานไหนรวม speculative decoding + weight prediction + SSD streaming ในระบบเดียว**

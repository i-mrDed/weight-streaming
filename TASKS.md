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
| ⬜ | Design data layout (NVMe sharding) | 🔴 | |
| ⬜ | Design Weight Predictor architecture | 🔴 | |
| ⬜ | Design Pre-fetch Scheduler | 🔴 | |
| ⬜ | Design Streaming Buffer management | 🔴 | |
| ⬜ | Design Execution Engine interface | 🔴 | |
| ⬜ | Design abstraction layer (MoE vs Dense) | 🟡 | |

---

## 📋 Phase 3: Prototype

| สถานะ | Task | Priority | Notes |
|-------|------|---------|-------|
| ⬜ | Select small MoE model for PoC | 🟡 | Mixtral? Qwen MoE? |
| ⬜ | Implement buffer simulator | 🔴 | |
| ⬜ | Implement predictor (heuristic first) | 🔴 | |
| ⬜ | Implement pre-fetch scheduler | 🔴 | |
| ⬜ | Integrate with existing inference engine | 🔴 | |

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

# MoE Routing & Expert Prediction — Research Notes

> **หัวข้อ:** การทำนาย expert activation pattern ใน MoE models  
> **ความเกี่ยวข้อง:** 🟢 สูงมาก — เป็นหัวใจของ Weight Predictor (Layer 2)  
> **SOTA (2025-2026):** PreScope (LLaPor predictor), DuoServe-MoE

---

## 📑 งานวิจัยที่เกี่ยวข้อง

### 1. PreScope: Unleashing the Power of Prefetching (2025) ⭐
| รายการ | รายละเอียด |
|--------|-----------|
| **Paper** | [PreScope: Unleashing the Power of Prefetching for Resource-Constrained MoE Inference](https://arxiv.org/abs/2509.23638) |
| **ผู้แต่ง** | Enda Yu et al. (NUDT, Tsinghua) |
| **แนวคิด** | ระบบ expert scheduling 3 ส่วน: LLaPor predictor + PreSched scheduler + AsyncIO |
| **ผลลัพธ์** | Throughput +141% vs Klotski, latency -74.6% vs HybriMoE |

**รายละเอียด LLaPor predictor:**
- **Layer-group aware:** MoE layers แบ่งเป็น input/output/middle group — แต่ละกลุ่มมี routing behavior ต่างกัน
- **Input:** Top-4 prediction accuracy **>90%**
- **ใช้:** Inter-layer routing correlation + cosine similarity ของ gating inputs
- **Online continuous learning:** ปรับปรุงระหว่าง inference
- **Architecture:** เบา — MLP ขนาดเล็ก

**ความเกี่ยวข้อง:** แสดงว่า expert prediction ทำได้แม่น (>90%) ด้วยโมเดลเล็กๆ — Weight Predictor ในระบบเรา feasibility สูง

---

### 2. DuoServe-MoE: Dual-Phase Expert Prefetch (2025)
| รายการ | รายละเอียด |
|--------|-----------|
| **Paper** | [DuoServe-MoE: Dual-Phase Expert Prefetch and Cache Scheduling](https://arxiv.org/abs/2509.07379) |
| **แนวคิด** | แยกกลยุทธ์ pre-fetch สำหรับ prefill (all experts) และ decode (predictive) |
| **Prediction** | Lightweight MLP — ใช้ popularity vector + inter-layer affinity |
| **GPU cache** | เก็บเฉพาะ k experts (Top-k) — memory ~15% ของ all-expert |

**ความเกี่ยวข้อง:** decode stage ใช้ predicted prefetching — เหมือนกับแนวทาง Speculative Weight Streaming

---

### 3. MoE-Prefetching (SNU, IEEE CAL 2025)
| รายการ | รายละเอียด |
|--------|-----------|
| **Paper** | [SSD Offloading for LLM MoE Weights Considered Harmful in Energy Efficiency](https://arxiv.org/abs/2508.06978) |
| **เทคนิค** | Fine-tune gate layer ของ decoder i เพื่อ predict expert สำหรับ decoder i+1 |
| **แนวคิด** | ระหว่างที่ decoder i + layer แรกของ decoder i+1 ทำงาน → fetch expert weights สำหรับ i+1 |
| **ข้อค้นพบ** | Latency hiding ได้ แต่ energy penalty ยังสูง |

**ความเกี่ยวข้อง:** เทคนิคนี้คล้ายกับ Speculative Weight Streaming มาก — แต่เรา extend ไปอีกขั้นด้วย draft model prediction

---

### 4. Expert Choice Routing (Google, NeurIPS 2022)
| รายการ | รายละเอียด |
|--------|-----------|
| **Paper** | [Mixture-of-Experts with Expert Choice Routing](https://arxiv.org/abs/2202.09368) |
| **แนวคิด** | สลับบทบาท: experts เลือก tokens แทน tokens เลือก experts |
| **ข้อดี** | Load balance สมบูรณ์, 2x training efficiency |
| **ข้อเสีย** | ต้องรู้ batch composition ล่วงหน้า |

**ความเกี่ยวข้อง:** ถ้า K3 ใช้ expert choice routing → prediction ยากขึ้น (expert เลือก token ไม่ใช่ token routing ผ่าน gate)

---

### 5. Least-Loaded Expert Parallelism (2026)
| รายการ | รายละเอียด |
|--------|-----------|
| **Paper** | [Least-Loaded Expert Parallelism](https://arxiv.org/abs/2601.17111) |
| **ข้อค้นพบ** | MoE models มี imbalanced routing ตามธรรมชาติ — desirable (domain-specific experts) |
| **ความเกี่ยวข้อง** | Imbalance → บาง expert เรียกบ่อยมาก → prediction แม่นขึ้น, buffer hit rate สูงขึ้น |

---

### 6. Fate: Fast MoE Inference via Predictive Prefetching (2025)
| รายการ | รายละเอียด |
|--------|-----------|
| **แนวคิด** | ใช้ similarity ของ adjacent-layer gating inputs ทำนาย expert |
| **ข้อจำกัด** | ไม่แก้ mismatch ระหว่าง compute duration และ I/O latency |
| **ความเกี่ยวข้อง** | การ predict จาก gating input similarity เป็น baseline ที่ดี |

---

### 7. ExpertFlow: Adaptive Expert Scheduling (2025)
| รายการ | รายละเอียด |
|--------|-----------|
| **แนวคิด** | Adaptive expert prefetching + cache-aware routing |
| **Cache** | Reduce cache misses, remove swap-in latency |
| **ความเกี่ยวข้อง** | Cache management policy — มี lessons ให้เอามาปรับใช้ |

---

### 8. Load Balancing for MoE (หลายงาน)
| Paper | ปี | แนวคิด |
|-------|-----|--------|
| EfficientMoE | 2025 | Load prediction + dynamic schedule |
| Adaptive-expert-weight load balance | 2025 | ปรับ expert weights โดยตรง แทน aux loss |
| Load Balancing with Similarity Preserving Routers | 2025 | MaxScore routing (min-cost max-flow) |

**ความเกี่ยวข้อง:** เข้าใจ routing dynamics → prediction ที่ดีขึ้น

---

## 📊 Expert Activation Pattern — ข้อเท็จจริงที่ค้นพบ

| ข้อเท็จจริง | หลักฐาน |
|-----------|---------|
| Expert activation มี **temporal locality** | Token ที่ติดกันมักเลือก experts คล้ายกัน |
| มี **hot experts** ที่ถูกเรียกบ่อย | ~20% experts รับ ~80% tokens |
| Layer-group structure | Input/output layers ต่างจาก middle layers |
| Routing **predictable** (>90% accuracy) | PreScope, SiDA |
| Imbalance เป็นธรรมชาติและ desirable | Least-Loaded EP paper |

---

## 🔑 Key Takeaways

| ข้อ | รายละเอียด |
|-----|-----------|
| 1 | Expert prediction **ทำได้ accuracy >90%** ด้วย MLP เล็ก |
| 2 | มีระบบ production-ready (PreScope, DuoServe-MoE) ที่ใช้เทคนิคคล้าย Speculative Weight Streaming |
| 3 | MoE-prefetching (gate layer fine-tune) ใกล้เคียงแนวทางเราที่สุด |
| 4 | Temporal locality + hot experts → buffer management มีโอกาสสำเร็จสูง |
| 5 | **Novel contribution:** รวม expert prediction เข้ากับ speculative decoding ใน draft model เดียวกัน |

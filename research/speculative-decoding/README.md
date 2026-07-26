# Speculative Decoding — Research Notes

> **หัวข้อ:** การเร่ง inference ด้วย draft model + verification  
> **ความเกี่ยวข้อง:** 🟢 สูงมาก — เป็น Layer 1 ของ Speculative Weight Streaming  
> **SOTA (2026):** EAGLE-3

---

## 📑 งานวิจัยที่เกี่ยวข้อง

### 1. EAGLE-3 (NeurIPS'25) ⭐ สำคัญที่สุด
| รายการ | รายละเอียด |
|--------|-----------|
| **Paper** | [EAGLE-3: Scaling up Inference Acceleration of Large Language Models via Training-Time Test](https://arxiv.org/abs/2503.01840) |
| **ปี** | 2025 |
| **ผู้แต่ง** | Yuhui Li et al. |
| **แนวคิด** | ใช้ lightweight draft head (~1 transformer layer + projections) แทน draft model เต็ม |
| **จุดเด่น** | - Multi-layer feature fusion (low/mid/high level)<br>- Feature prediction constraint → direct token prediction<br>- Scaling law: training data → speedup ratio<br>- Acceptance rate flat vs position (robust) |
| **Speedup** | 2-4x vs vanilla autoregressive |

**ความเกี่ยวข้อง:** Draft model ในระบบ Speculative Weight Streaming ไม่จำเป็นต้องเป็น 3B model เต็ม — สามารถใช้ EAGLE-3-style head ที่เบากว่า และ train ให้ predict expert routing ไปพร้อมกัน

---

### 2. EAGLE-2 (EMNLP'24)
| รายการ | รายละเอียด |
|--------|-----------|
| **Paper** | [EAGLE-2: Faster Inference of Language Models with Dynamic Draft Trees](https://arxiv.org/abs/2406.16858) |
| **ปี** | 2024 |
| **แนวคิด** | Dynamic draft tree — ปรับจำนวน speculative tokens ตาม confidence |
| **ความเกี่ยวข้อง** | ระบบเราอาจปรับจำนวน candidate tokens ตาม prediction confidence ได้ |

---

### 3. Original Speculative Decoding (ICML'23)
| รายการ | รายละเอียด |
|--------|-----------|
| **Paper** | [Fast Inference from Transformers via Speculative Decoding](https://arxiv.org/abs/2211.17192) |
| **ปี** | 2023 |
| **ผู้แต่ง** | Leviathan, Kalman, Matias (Google) |
| **แนวคิด** | Draft model generate K tokens → target model verify ใน 1 forward pass |
| **ทฤษฎี** | Lossless — output distribution identical to target model |
| **Speedup** | 2-3x |

---

### 4. Medusa (2024)
| รายการ | รายละเอียด |
|--------|-----------|
| **Paper** | [Medusa: Simple LLM Inference Acceleration Framework without Drafting](https://arxiv.org/abs/2401.10774) |
| **แนวคิด** | เพิ่ม multiple heads บน target model (ไม่ต้องมี draft model แยก) |
| **ข้อจำกัด** | ต้อง fine-tune target model |

---

### 5. Speculative Diffusion Decoding (NAACL'25)
| รายการ | รายละเอียด |
|--------|-----------|
| **Paper** | [Speculative Diffusion Decoding](https://aclanthology.org/2025.naacl-long.601/) |
| **แนวคิด** | Use discrete diffusion เป็น draft — parallel draft + parallel verification |
| **Speedup** | Up to 7x |
| **ความเกี่ยวข้อง** | Parallel drafting อาจช่วยให้ prediction + pre-fetch มีเวลามากขึ้น |

---

### 6. Collaborative Decoding via Speculation (CoS, 2025)
| รายการ | รายละเอียด |
|--------|-----------|
| **Paper** | [Fast LLM Collaborative Decoding via Speculation](https://arxiv.org/abs/2502.01662) |
| **แนวคิด** | สนับสนุน multiple draft models + alternate proposal framework |
| **ความเกี่ยวข้อง** | อาจใช้ draft model + weight predictor working in parallel |

---

### 7. Production-Grade Evaluation (UC Berkeley, 2025)
| รายการ | รายละเอียด |
|--------|-----------|
| **Paper** | [Efficient LLM System with Speculative Decoding](https://www2.eecs.berkeley.edu/Pubs/TechRpts/2025/EECS-2025-224.html) |
| **แนวคิด** | การประเมิน speculative decoding ใน production — verification dominates execution time |
| **ข้อค้นพบ** | เมื่อ speculative tokens ถูก reject → overhead สูง |

---

## 🔑 Key Takeaways

| ข้อ | รายละเอียด |
|-----|-----------|
| 1 | **EAGLE-3** เป็น SOTA — draft head (<5% params) แทน draft model เต็ม |
| 2 | Speculative decoding **lossless** — output ไม่เปลี่ยน |
| 3 | Speedup ปกติ 2-3x, สูงสุด ~7x (diffusion) |
| 4 | Acceptance rate ขึ้นกับ **alignment** ระหว่าง draft ↔ target |
| 5 | Draft model ที่ดีต้อง predict weight access pattern ได้ด้วย → **novel contribution** |

---

## 💡 ความเชื่อมโยงกับ Speculative Weight Streaming

```
EAGLE-3 Head (draft) ──→ predict tokens + predict experts
         │
         ▼
Weight Predictor ──→ priority queue → pre-fetch from NVMe
         │
         ▼
Main Model ──→ execute from streaming buffer
         │
         ▼
(overlap) ←── EAGLE-3 head + predictor ทำงานขนานกับ main model
```

**คำถามเปิด:** จะ extend EAGLE-3 ให้ predict expert routing ไปพร้อมกับ token prediction ได้ไหม?

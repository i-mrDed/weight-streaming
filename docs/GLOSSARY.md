# Glossary — Speculative Weight Streaming

> **用途:** รวมคำศัพท์เฉพาะของโปรเจค — ใช้คำเดียวกันทั้งทีม  
> **ต้องทำ:** เพิ่มคำศัพท์ใหม่ทันทีเมื่อมีการใช้ใน docs/code

---

## 📖 Glossary

| คำ | ภาษา | ความหมาย | เกี่ยวข้องกับ |
|----|------|---------|-------------|
| **Speculative Weight Streaming** | EN | ระบบที่เรา propose — ใช้ draft model ทำนาย weight access pattern + pre-fetch จาก NVMe | ทุก Layer |
| **Speculative Decoding** | EN | เทคนิคให้ draft model generate K tokens → target model verify พร้อมกัน | Layer 1 |
| **Draft Model** / **Draft Head** | EN | โมเดลเล็ก (<5% params) ที่ predict tokens + weight access | Layer 1 |
| **EAGLE-3** | EN | SOTA speculative decoding — draft head แบบ multi-layer feature fusion | Layer 1 reference |
| **Weight Predictor** | EN | Component ที่รับ prediction จาก draft → จัด priority queue → สั่ง pre-fetch | Layer 2 |
| **Pre-fetch Scheduler** | EN | จัดคิว I/O request ตาม priority, batch sequential reads | Layer 2 |
| **Streaming Buffer** | EN | RAM buffer สำหรับ weights ที่ pre-fetch มา — LRU eviction | Layer 3 |
| **Kimi K3** | EN | โมเดล MoE 2.8T ของ Moonshot AI — กรณีศึกษาแรก | Target Model |
| **KDA (Kimi Delta Attention)** | EN | Hybrid linear attention — reduce KV cache ~75% | K3 architecture |
| **AttnRes (Attention Residuals)** | EN | Selective retrieval across depth — 25% training efficiency | K3 architecture |
| **Stable LatentMoE** | EN | MoE routing framework ของ K3 — latent-space routing | K3 architecture |
| **Quantile Balancing** | EN | วิธี load balance expert — derive จาก router-score quantiles | K3 architecture |
| **MXFP4** | EN | 4-bit floating point precision — K3 ใช้ trained-in quantization | Precision |
| **MoE (Mixture of Experts)** | EN | สถาปัตยกรรมที่มี experts หลายตัว → activate เพียงบางส่วนต่อ token | Architecture |
| **Dense Model** | EN | สถาปัตยกรรมที่ทุก parameters ใช้ทุก token | Architecture |
| **Speculative Decoding Acceptance Rate** | EN | สัดส่วนของ draft tokens ที่ target model ยอมรับ | Performance Metric |
| **Hit Rate** | EN | สัดส่วนของ weight access ที่เจอใน streaming buffer (ไม่ต้องรอ I/O) | Performance Metric |
| **MoE-prefetching** | EN | เทคนิค fine-tune gate layer เพื่อ predict expert ใน layer ถัดไป | Related Work |
| **Near-Storage Computing** | EN | การย้าย compute ไปใกล้ SSD — FPGA บน SSD controller | Supplementary |
| **ADR (Architecture Decision Record)** | EN | บันทึกการตัดสินใจทางเทคนิค — รู้ที่มา รู้เหตุผล | Documentation |
| **CXL (Compute Express Link)** | EN | Interconnect สำหรับ memory pooling — อนาคตอาจเปลี่ยน architecture | Future |
| **io_uring** | EN | Linux async I/O API — สำหรับ pre-fetch scheduling | Implementation |
| **IOCP (I/O Completion Ports)** | EN | Windows async I/O API — สำหรับ pre-fetch scheduling | Implementation |

---

## 📝 วิธีเพิ่มคำศัพท์ใหม่

1. เช็คก่อนว่ามีในนี้หรือยัง
2. ใช้คำตามที่นิยามไว้ใน GLOSSARY
3. ถ้ามีความหมายต่างกันในบริบทอื่น → ระบุบริบทด้วย

---

> **คำแนะนำ:** ถ้าอ่านไฟล์ไหนแล้วเจอคำที่ไม่เข้าใจ → กลับมาที่นี่ก่อน หรือเพิ่มเข้ามา

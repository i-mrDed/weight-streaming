# Related Work Notes — PreScope/LayerScope + EAGLE-3

> **2026-08-13** · อ่านเพื่อปิด gap ของ Phase 5 paper outline (Related Work
> §2.3) — สรุปสาระ + ตำแหน่งเทียบกับงานเรา

---

## 1. PreScope → **LayerScope** (arXiv:2509.23638, ICS'26)

**Title now:** *LayerScope: Predictive Cross-Layer Scheduling for Efficient
Multi-Batch MoE Inference on Legacy Servers* (Enda Yu et al., NUDT/Tsinghua)

### สาระ

Prediction-driven **expert scheduling** สำหรับ MoE ที่ offload ลง
CPU memory + GPU บน commodity hardware — โจทย์: PCIe transfer latency
เกิน compute หลายเท่า ต้อง prefetch ให้ตรง 3 components:

1. **LLaPor** — layer-aware predictor: ใช้ layer-group structure
   (input/output/middle layers มี routing pattern ต่างกัน) → Top-4
   prediction accuracy > 90% + online learning
2. **PreSched** — cross-layer global scheduler: cost model รวมทุก layer
   (ไม่ใช่ greedy per-layer) สมดุล prefetch cost vs on-demand load
3. **AsyncIO** — async I/O optimizer: overlap PCIe transfer กับ
   GPU/CPU kernel, split expert เป็น chunks เติม PCIe bandwidth

**ผล:** throughput +141% vs SOTA (Klotski/HybriMoE), decoding latency
−74.6% — บน Mixtral-8x7B, DeepSeek-MoE, Qwen3-30B-A3B, Moonlight-16B-A3B

### เทียบกับงานเรา

| มิติ | LayerScope | เรา (weight-streaming) |
|---|---|---|
| Bottleneck | **PCIe** (CPU↔GPU offload) | **Disk→RAM** (mmap, page faults) |
| ที่เก็บ | CPU memory (offload จาก GPU) | OS page cache (mmap) |
| สภาพแวดล้อม | GPU + CPU co-exec, legacy servers | consumer CPU-only (ngl=0) + 12GB VRAM |
| Predictor | LLaPor (layer-group-aware, >90% Top-4) | heuristic/perfect (EXP-002: predictor ไม่ critical) |
| Buffer | GPU resident experts (prefetch slot) | LRU+priority buffer / OS page cache |
| หลักฐาน | throughput/latency gain ต่อ batch | honest physics: BW ÷ bytes/token + telemetry |

**ความสัมพันธ์:** LayerScope ยืนยันว่า prefetch มีค่ามากบน resource-
constrained (ตรงใจเรา) แต่ใช้ GPU+PCIe ที่ BW สูงกว่า disk-mmap มาก —
ตัวเลขของเค้า (141% กำไร) กับของเรา (24× K3 upside ที่ buffer พอดี)
คือเรื่องเดียวกันคนละ tier: **กำไรของ prefetch = f(BW gap ระหว่าง hit
path กับ miss path)** — PCIe gap ~10×, disk-mmap gap ~50× → ของเรายิ่ง
ต้อง hit สูงกว่า ตรง EXP-029

**อ้างอิงใน paper:** Related Work §2.3 (weight streaming / prefetch) +
Discussion (ของเราวัด honest disk-bound tier ที่เค้าไม่ได้พูดถึง)

---

## 2. EAGLE-3 (arXiv:2503.01840)

*Scaling up Inference Acceleration of Large Language Models via
Training-Time Test* (Yuhui Li et al., Microsoft Research)

### สาระ

Speculative decoding รุ่น 3: draft model เร่ง target LLM โดย
**abandon feature prediction → direct token prediction** + **multi-layer
feature fusion** (training-time test) — draft ได้ประโยชน์เต็มที่จากการ
scale training data

**ผล:** speedup ถึง **6.5×**, ~1.4× เหนือ EAGLE-2; บน SGLang batch 64
→ throughput +1.38×

### เทียบกับงานเรา

- EAGLE-3 = **token-level speculation** (draft tokens) — คนละกลไกกับ
  weight prefetching ของเรา
- เราเคยทดลอง speculative decoding จริง (MTP head, EXP-015/016/017):
  **ช้าลง −11–18%** บนเครื่องนี้ — เพราะ draft step ยังรัน full forward
  pass + model file ใหญ่ขึ้น — ข้อค้นพบที่ตรงข้ามกับ EAGLE-3 ซึ่งได้
  speedup บน GPU cluster ที่ BW ไม่ใช่กำแพง
- **บทเรียนร่วม:** speculation/prefetch ชนะเฉพาะเมื่อ "ของที่ต้องรอ"
  แพงกว่า "ของที่เดา" — EAGLE-3: draft tokens ถูกกว่า target tokens;
  ของเรา: disk read ถูกกว่า? ไม่ — disk read แพงมาก (0.38 GB/s) →
  การเดา experts ต้องแม่นถึงจะคุ้ม (LLaPor Top-4 >90% คือคำตอบของ
  LayerScope สำหรับ PCIe; ของเรา = predictor ไม่ critical เพราะ OS
  page cache + locality ทำงานเองแล้ว EXP-002)

**อ้างอิงใน paper:** Related Work (speculative decoding ตระกูล EAGLE) +
ของเรา = หลักฐานว่า speculation บน bandwidth-bound consumer HW ไม่ได้
กำไร (EXP-015/016/017) — นี่คือจุดต่างที่ paper ควรชี้

---

## สรุปสำหรับ paper

- **§2.3 Prefetching/weight streaming:** LayerScope (2509.23638) =
  งานที่ใกล้สุด (prediction-driven prefetch) แต่ tier ต่างกัน (PCIe vs
  disk-mmap); เราเติมส่วนที่เค้าไม่มี: honest disk-bound telemetry +
  physics model ที่ทำนายได้
- **Speculative decoding:** EAGLE-3 (2503.01840) = token-level; งานเรา
  มี negative result จริงบน consumer HW (EXP-015..017)
- **จุดยืนของเรา (differentiator):** ไม่มีใคร publish ตัวเลข >RAM จริง
  ด้วย OS-level telemetry + calibrated physics — EXP-012 write-up คือ
  หลักฐาน

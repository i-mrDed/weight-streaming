# Session Log — Speculative Weight Streaming

> **用途:** บันทึกการทำงานทุก session — session ถัดไปรู้ทันทีว่าค้างตรงไหน  
> **ต้องทำทุกรอบ:** ก่อนเริ่ม session → อ่าน entry ล่าสุด | หลังจบ session → เขียน entry ใหม่

---

## [S004] — 2026-07-27 — Phase 3a: Prototype Simulator

**🎯 เป้าหมาย:** สร้าง Python simulator + รัน experiments วัด performance

### ✅ สิ่งที่ทำ
- สร้าง simulator framework ครบ 5 modules (600+ บรรทัด)
- EXP-001: Buffer size & eviction policy sweep → **พบว่า 512 MB + LFU = 78.2% hit rate**
- EXP-003: Timing + overlap efficiency → **76.7% overlap, 2.74 tok/s**
- EXP-002: Predictor — partial (ต้องปรับ access model)
- วิเคราะห์ findings: predictor accuracy = biggest performance leverage

### ⚡ การตัดสินใจ (อัปเดต)
- **เปลี่ยน buffer default จาก 256 MB → 512 MB** (จาก evidence)
- **เปลี่ยน default eviction จาก LRU+priority → LFU** (LFU > LRU สำหรับ MoE)
- **Priority boost ปิด** จนกว่า predictor accuracy >30%
- **RAM budget ยัง OK:** 512 MB buffer + draft head (~6 GB) + KV cache (~8 GB) = ~14.5 GB

### 🐛 ปัญหา / อุปสรรค
- Windows encoding (cp874) → emoji + special chars พิมพ์ไม่ได้ → แก้เป็น ASCII
- Access pattern per-layer independent → working set ใหญ่เกินจริง → ต้องปรับ

### ⏭️ ถัดไป
- [ ] EXP-002: ปรับ access model + ทดสอบ MLP predictor
- [ ] EXP-004: Per-layer expert sharing (K3 realistic)
- [ ] เลือก MoE model เล็กสำหรับ PoC + fork llama.cpp

### 📎 อ้างอิง
- `simulator/` — code ทั้งหมด
- `research/experiments/EXP-001-buffer-sim/` — buffer results
- `research/experiments/EXP-003-timing-sim/` — timing results

---

## [S005] — 2026-07-27 — EXP-002: Predictor Accuracy Sweep

**🎯 เป้าหมาย:** วัดผลกระทบของ predictor accuracy ต่อ buffer hit rate และ throughput

### ✅ สิ่งที่ทำ
- ปรับ `access_pattern.py` เพิ่ม shared_experts_per_token mode (realistic K3: 72/80 layers identical per token)
- เพิ่ม simulated_accuracy predictor mode สำหรับ injection error ควบคุม
- เพิ่ม `sweep-accuracy` CLI — ทดสอบ 9 ระดับความแม่นยำ x 2 policies (LFU, LRU+priority)
- บันทึก results + analysis มายัง experiment tracking

### 🔬 Key Findings (เปลี่ยนแปลง Design อย่างมีนัยสำคัญ)

1. **LFU = 76.2% hit rate flat** — ทุกระดับ accuracy ได้ค่าเท่ากัน (LFU ไม่ใช้ prediction)
2. **LRU+P hit rate แย่ลงเมื่อ accuracy สูงขึ้น** — 29.9% (10%) → 15.5% (perfect) — "priority clogging"
3. **Throughput flat = 2.73 t/s** — compute (350ms) ครอบงำ I/O อย่างสมบูรณ์
4. **Overlap ดีขึ้น 7.6x** (30.9ms → 233.8ms) แต่ไม่ช่วย throughput

### ⚡ การตัดสินใจ
- **ยุติ priority boost** — LFU ไม่ใช้ priority, LRU+P มีปัญหา clogging
- **ลดบทบาท predictor** — accuracy ไม่ critical, heuristic ก็พอ
- **คง LFU เป็น default eviction policy** — simple, effective, no prediction needed
- **Weight streaming ≈ RAM reduction tool ไม่ใช่ throughput accelerator**

### 🐛 ปัญหา / อุปสรรค
- `evaluate_prediction` truncate top-16 → accuracy รายงานต่ำกว่าความเป็นจริง (fixed)
- `predictor_confidence` dead parameter ใน timing model (fixed)
- `_predict_simulated_accuracy` คำนวณ accuracy เทียบ n_predict แทน n_actual (fixed)

### ⏭️ ถัดไป
- อัปเดต ARCHITECTURE.md ตาม findings
- Phase 3b: fork llama.cpp + real HW test เพื่อวัด compute/I/O ratio จริง
- EXP-004: Cold start + turbulence resilience (ถ้า predictor มีประโยชน์ตรงไหน)

### 📎 อ้างอิง
- `EXP-002-predictor-sim/results.md` — full data table
- `EXP-002-predictor-sim/analysis.md` — interpretation + design changes
- `simulator/predictor.py` — simulated_accuracy predictor
- `simulator/access_pattern.py` — shared_experts_per_token mode

---

## [S006] — 2026-07-27 — Phase 3b: Real Hardware Benchmark

**🎯 เป้าหมาย:** วัด compute time จริงของ MoE model บน consumer hardware

### ✅ สิ่งที่ทำ
- ตรวจสอบ system spec: RTX 3060 12 GB, 68.6 GB RAM, CPU-only inference
- ติดตั้ง llama-cpp-python + ดาวน์โหลด Qwen1.5-MoE-A2.7B Q2_K GGUF (5.88 GB)
- รัน benchmark วัด: prefill timing (16-256 ctx), per-token compute, throughput
- สร้าง EXP-004 benchmark experiment พร้อม analysis

### 🔬 Key Finding: SIMULATOR WRONG — Real System is I/O-BOUND

| | Old Simulator | Real Hardware |
|---|---|---|
| Compute time (K3) | 350 ms/token | **815 ms/token** |
| Bottleneck | compute-bound | **I/O-BOUND** |
| Predictor value | None | **Critical for throughput** |
| Buffer value | RAM reduction only | **Direct throughput improvement** |

**Qwen measured:** 44ms/token, 22.7 tok/s (CPU, 2.7B active params)
**K3 scaled:** 815ms/token, 1.23 tok/s (50B active params, MXFP4)
**NVMe full load:** 1786ms (25 GB @ 14 GB/s)

### ⚡ Design Reversal (based on real data)
- **Predictor accuracy IS important** — I/O-bound means overlap efficiency = throughput
- **Buffer hit rate directly affects throughput** — 76.2% → 1.06 t/s vs 0% → 0.56 t/s (+88%)
- **Priority boost might matter** — keeping right experts in buffer reduces NVMe reads
- **Simulator timing needs update**: compute_time 350ms → 815ms

### ⏭️ ถัดไป
- อัปเดต simulator timing model ด้วย real K3 estimate (815ms compute)
- Re-run EXP-001/002/003 with new timing → verify I/O-bound conclusions
- Phase 3b สร้าง streaming buffer prototype (ถ้ามี hardware เพิ่ม)

### 📎 อ้างอิง
- `EXP-004-benchmark/results.json` — raw benchmark data
- `EXP-004-benchmark/analysis.md` — full analysis
- `research/models/Qwen1.5-MoE-A2.7B_Q2_k.gguf` — downloaded model (5.88 GB)

---

## [S001] — 2026-07-27 — Initial Concept + Phase 1 Research

**🎯 เป้าหมาย:** กำหนดแนวคิดโปรเจค + ค้นคว้างานวิจัยที่เกี่ยวข้อง

### ✅ สิ่งที่ทำ
- ตั้ง Concept Speculative Weight Streaming
- Phase 1 Research Review ครบ 5 หมวด
- ขยายเป้าหมายจาก K3 สู่ cross-architecture
- สร้าง research/ structure

### ⚡ การตัดสินใจ
- **เลือก 3-layer architecture** (Draft Model → Weight Predictor → Streaming Buffer)
- **เริ่มที่ K3 ก่อน** แต่ framework ต้องรองรับทุก model
- **ไม่ใช้ near-storage computing** — รอ hardware 成熟

### ⏭️ ถัดไป
- ตั้งระบบบันทึกการทำงาน (กำลังทำใน S002)

### 📎 อ้างอิง
- `v0.1.0` — Concept + feasibility
- `v0.2.0` — Research Review

---

> **Template สำหรับ session ใหม่:**
> ```markdown
> ## [S000] — YYYY-MM-DD — [หัวข้อสั้น]
>
> **🎯 เป้าหมาย:** ...
>
> ### ✅ สิ่งที่ทำ
> - ...
>
> ### ⚡ การตัดสินใจ
> - ...
>
> ### 🐛 ปัญหา / อุปสรรค
> - ...
>
> ### ⏭️ ถัดไป
> - ...
>
> ### 📎 อ้างอิง
> - ...
> ```

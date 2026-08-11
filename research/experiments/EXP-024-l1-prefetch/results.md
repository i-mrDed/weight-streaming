# EXP-024 — L1 Prefetch A/B (E1/E2/E2b): does readahead help?

> **วันที่:** 2026-08-11 · **สถานะ:** CLOSED (negative result — prefetch ต้องรู้ routing)
> **โมเดล:** DeepSeek-V4-Flash-0731 UD-IQ3_XXS (97.05GB, split 4) · **เครื่อง:** i9-9900KF + RTX 3060 12GB + 64GB RAM
> **base:** main `d6f8784` (รวม PR #1: GGUFSplitParser + WS_LLAMA_BACKEND_PORT)

---

## 1. เป้าหมาย & Gate

- **G0 (สถาปัตยกรรม/วัดได้):** random 4KB คือคอขวดจริงไหม + GGUF layout เอื้อ sequential prefetch ไหม
- **G1 (ประสิทธิภาพ):** readahead ลด warm faults/tok ≥ 50% โดย tok/s ไม่ลด — **เป้าหมาย 2.5–4 tok/s**

## 2. ผล E1 — NVMe character (Gate G0 ✅ ผ่าน)

อ่านไฟล์ shard2 46.5GB โดยตรง (Python seek+read, 256MB/เทสต์):

| pattern | QD1 | QD8 | QD32 |
|---|---:|---:|---:|
| sequential 4KB | 3,245 MB/s | — | — |
| sequential 64KB | 2,293 MB/s | — | — |
| sequential 1MB | 1,732 MB/s | — | — |
| **random 4KB** | **12.5 MB/s** | 63.0 | 65.0 |
| random 64KB | 2,103 MB/s | 939 | 939 |
| random 1MB | 838 MB/s | 2,296 | 2,148 |

**Verdict:** random 4KB ช้ากว่า sequential 64KB **35–183×** — คอขวดคือ random fault throughput จริง (headroom มีจริง)

## 3. ผล E3 — GGUF layout (รันจริง 4 shards)

- shard1 = metadata-only (5MB, tensor_count=0) · shard2 = 660 tensors (L0–21) · shard3 = 620 (L22–42) · shard4 = 48
- data section **ต่อเนื่อง 100%** (zero-gap) — อ่านตาม tensor-table order = sequential จริง
- **expert tensor = 620–822MB/ชิ้น** — ใหญ่กว่า shard 4MB ของ shard_repacker ~180× (repacker granularity ผิด)
- `deepseek4`: 43 layers · 256 experts · **6 used** · MLA · context 1M

## 4. ผล E2/E2b — prefetch A/B (warm, drop-cache protocol)

| รอบ | สเปค prefetch | drop cache | warm faults/tok | warm tok/s |
|---|---|---|---|---|
| E2 (naive) | 64MB/round เร็วสุด | ❌ ไม่ drop | **-8.6%** | **-10.0%** 🔴 |
| E2b-v2 (rate-limit) | 300MB/s | ✅ 32.8GB | **-20.4%** | **-30.6%** 🔴 |
| E2b-v2 (full) | 700MB/s | ✅ 40.0GB | **+69.0%** 🔴🔴 | **-42.2%** 🔴🔴 |

## 5. 🔴 ฟันธง: CLOSED — prefetch แบบไม่รู้ routing = แย่ลงทุกกรณี

- ไม่ว่าสเปคต่ำ/เต็ม ไม่ว่า drop cache หรือไม่ — **tok/s ลดเสมอ (10–42%)**; สเปคเต็ม + drop cache ถูกต้อง = **faults พุ่ง +69%** (thrash: prefetch 700MB/s อ่านหน้าที่ไม่ใช้ กดหน้าที่ generation ต้องการออกจาก cache)
- **บทเรียน (สอดคล้องกับ WASTE advisory):** ต่อให้อ่าน 64KB–1MB ได้ 35–180× เร็วกว่า 4KB random (E1) — **ถ้าไม่รู้ว่า "expert ไหนจะถูกใช้" prefetch waste 41%+ และแย่ง disk จนแย่กว่าเดิม**
- **ทางเดียวที่ถูกต้อง (Gate 1 → ทาง A):** ปิด gap `total_accesses = 0` (instrumented/patched llama.cpp หรือ fork เล็ก) → router-aware predictor (6 experts/layer) → prefetch เฉพาะที่ใช้จริง

## 6. งานที่เข้า main แล้วจาก EXP-024 (PR #1)

| commit | งาน |
|---|---|
| `fa5058f` | `GGUFSplitParser` — split-shard GGUF + global offsets (verify 97GB จริง, 11 tests) |
| `31c099f` | `WS_LLAMA_BACKEND_PORT` — รัน server คู่โดยไม่ชน port (7 tests) |

## 7. เอกสารประกอบ

- `D:\.opencode-research\weight-streaming-l1-engine-review\research\09-e2-results.md` — ผลเต็ม 3 รอบ
- `research/10-decision.md` — ทางเลือก + ฟันธง
- `research/11-router-aware-plan.md` — blueprint ทาง A (พร้อมเริ่ม)
- `research/07-e1-e3-results.md` — E1/E3 ละเอียด
- `research/08-t0-parser-plan.md` — GGUFSplitParser design

## 8. สิ่งที่ยังค้าง (เปิดทาง A)

1. **total_accesses=0 gap** — ยังไม่ปิด (ต้อง instrumented llama.cpp)
2. **E4 idle-gap** — PDH sampler ยังคืน 0 (path counter ผิด) — ยังไม่เคยวัด idle จริง
3. **hardware** — โมเดลอยู่ C: (SATA, ดิสก์เดียวกับ Windows) → เครื่องค้างตอนโหลด; แนะนำย้ายไป D: (NVMe, disk #4) เมื่อมีพื้นที่ ~97GB
4. **dependabot** — 3 vulnerabilities (2 high, 1 moderate) บน default branch
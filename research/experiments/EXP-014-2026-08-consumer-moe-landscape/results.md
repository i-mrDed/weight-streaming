# EXP-014 ผล — ภาพรวม 2026-08: ระบบที่รัน MoE ใหญ่บน consumer hardware

## 1. Landscape (ตัวเลขจาก source จริง ณ 2026-08-10)

| ระบบ | โมเดลสูงสุดที่รัน | Hardware | tok/s | OS | "ใช้ได้จริง"? |
|---|---|---|---|---|---|
| **pulsar** (giannisanni/pulsar, Rust+CUDA) | GLM-5.2 **743B** 2.7 · DS-V4-Flash 284B **8.2–11.3** · K2.7 1T 1.3 · Hy3 295B 6–7 | 2×16GB GPU + **30GB RAM** + NVMe Gen5 | 1.3–11.3 | Linux | ✅ ระดับสบาย (DS V4 Flash), ระดับอดทน (GLM 743B) |
| **llama.cpp** (K3 PR merge แล้ว) | K3 2.8T (1-bit ≈ 594–620 GB) | "home lab" / 29–64GB RAM | **0.5–4** | ทุก OS | ⚠️ รันได้ แต่ยังใช้จริงยาก (0.5 @29GB → 4 t/s lab) |
| **Deltafin** (gavamedia/deltafin, 701⭐) | K3 2.8T | Apple Silicon M1 Max 64GB / Linux | **~15 s/token (0.07)** | macOS/Linux | ❌ รันได้ แต่ช้าเกินใช้จริง |
| **kimi-k3-in-c** (FareedKhan-dev) | K3 2.8T | **8.24 GB RAM** CPU-only | ต่ำมาก (ดู EXP-013: 71/120) | Linux | ❌ พิสูจน์แนวคิดเท่านั้น |
| **sqliteai/waste** (3 วันก่อน) | K3 2.8T | 64GB RAM แนะนำ | ยังไม่มี benchmark | ? | ❓ ใหม่เกินไป |
| **PowerInfer-2** (paper 2024) | Mixtral 47B | สมาร์ทโฟน | 11.68 (47B) | Android | ✅ แต่โมเดลเล็กกว่า |
| **vLLM (DSpark)** | K3 2.8T | datacenter GPU (8×H100 ฯลฯ) | 370/user | Linux | ✅ แต่ไม่ใช่ consumer |

**คำตอบข้อ 1 — ซื่อตรง:** ณ ส.ค. 2026 **ยังไม่มีใคร** รัน K3 2.8T บนเครื่อง
32–64GB RAM แล้ว "ใช้ทำงานได้จริง" — ทุกตัวที่ทำได้อยู่ที่ 0.07–4 tok/s
(ใช้จริงยาก) ส่วนโมเดล 300B–1T บน **consumer GPU** นั้น **pulsar เพิ่งพิสูจน์
ว่าใช้ได้จริง** (743B @ 2.7 tok/s) — แต่ต้องมี 32GB VRAM (2×16GB) +
NVMe Gen5 + Linux

## 2. Deep-dive: pulsar — "กุญแจ" ที่เพิ่งค้นพบ

Engine ใหม่ (Rust + CUDA) **ไม่ใช้ llama.cpp เลย** — ออกแบบตาม thesis
เดียวกับโปรเจคเรา:

```
routed experts อยู่บน NVMe → stream ต่อ token
ส่วนที่ "ตัดสินใจ" (attention + hot experts) อยู่ resident ใน VRAM
CPU lane (opt-in): expert ที่ host-cache hit คำนวณบน CPU (AVX2 iq kernels)
  แทน upload ขึ้น GPU — 42 GB/s บน 9900X สูงกว่า PCIe 28.7 GB/s
```

### ตัวเลขที่ยืนยันฟิสิกส์เดียวกับ EXP-012 ของเรา

- **"decode rate slides with output length… the floor is set by how much
  expert working set fits in host RAM — more RAM lifts the whole curve"**
  → ตรงกับ verdict EXP-012 (disk-bound; RAM 128GB = ทางเดียวที่ยกทั้ง curve)
- **CPU lane ช่วยเมื่อ host-cache-hit** (DS V4 Flash 8.2→11.3 tok/s)
  → ยืนยันทิศทาง `--cpu-moe`/`n-cpu-moe` ของเรา + จุด crossover คือ
  PCIe bandwidth vs CPU bandwidth
- **Quant เล็กกว่าวิ่งเร็วได้** (IQ2_XXS > Q4_K_M เมื่อ expert อยู่ resident มากกว่า)
  → ตรงกับ EXP-011/012 quant comparison — ต้องวัด IQ2_XXS บน DS V4 Flash
- **Warm census (expert popularity) ก่อน bench** → เราใช้ clean-room +
  cold/warm อยู่แล้ว

### ทำไม pulsar เร็วกว่าเรา 5–6× (DS V4 Flash 8–11 vs 1.5–1.9)

| ปัจจัย | pulsar | เรา | ผล |
|---|---|---|---|
| VRAM | 32 GB (2×16) | 12 GB | hot experts ~90% อยู่ GPU tier |
| NVMe | Gen5 ~7 GB/s | Gen3/4? | อ่าน expert ต่อ token เร็วขึ้น |
| CPU lane | AVX2 iq kernels + DDR5 9900X | llama.cpp CPU (DDR4) | host-cache-hit experts ถูกกว่า |
| Engine | custom CUDA | llama.cpp (ของคนอื่น) | — |

→ **ช่องว่างส่วนใหญ่คือ hardware (เปลี่ยนไม่ได้ตอนนี้) ไม่ใช่ซอฟต์แวร์**
แต่มี software headroom จริงที่ยืมได้ (ข้อ 4)

## 3. คะแนนเทียบ (แบบ EXP-013, เต็ม 120)

| มิติ | เรา (weight-streaming) | pulsar | Deltafin | kimi-k3-in-c |
|---|---:|---:|---:|---:|
| รัน >RAM บน consumer HW | 15 | 15 | 13 | 12 |
| ความเร็วที่วัดจริง | 8 (1.5–1.9 DS V4) | 14 (8–11 DS V4) | 4 (0.07 K3) | 4 |
| ใช้ทำงานได้จริง (UX/product) | 10 | 12 | 6 | 3 |
| รองรับสถาปัตยกรรม/โมเดลหลายตัว | 12 | 15 | 5 | 4 |
| Windows support | 12 | 2 (Linux เท่านั้น) | 3 (mac/Linux) | 3 |
| memory-engineering (quant/dequant) | 10 | 14 | 12 | 15 |
| correctness/honesty (gates, telemetry) | 13 | 13 | 7 | 12 |
| เอกสาร/ความโปร่งใส | 9 | 12 | 8 | 8 |
| **รวม** | **89** | **97** | **58** | **61** |

## 4. Verdict + ไอเดียที่ยืมได้ (ภายใต้ข้อจำกัดคงที่)

**Verdict:** thesis เราถูกทิศ (pulsar พิสูจน์แล้ว) — แต่บนเครื่องนี้
**ไม่มีซอฟต์แวร์ใด** จะทำให้ K3 (594GB+) ใช้ได้จริง (ฟิสิกส์: ~10 GB/token
active → 0.3–0.5 tok/s ที่ bandwidth เรา) เป้าหมายจริงที่บรรลุได้ =
**DS V4 Flash 104 GB จาก 1.5–1.9 → 2.5–4 tok/s** (ใช้แบบอดทนได้)

**ยืมได้ 5 อย่าง (software-only):**

1. **Expert popularity census → auto tiering** — วัดว่า experts ไหนถูกเรียก
   บ่อย (warm census) แล้ววาง hot experts ลง VRAM อัตโนมัติ (แทน n-cpu-moe
   แบบ static) — เราเขียนได้บน llama-server ผ่าน `--n-cpu-moe` ที่ปรับตาม census
2. **CPU lane ตาม host-cache residency** — เลือกว่า expert ตัวไหนคำนวณบน
   CPU (cache-hot) vs upload ขึ้น GPU ตาม residency จริง (เราวัด residency
   ได้แล้ว — `QueryWorkingSetEx`)
3. **วัด IQ2_XXS บน DS V4 Flash** — quant เล็กลง → bytes/token น้อยลง →
   resident มากขึ้น (สคริปต์มี `--variant iq2m` แล้ว — ตัวต่อยอดตรง)
4. **Speculative decoding บน GPU backend** — EXP-010 dead end บน CPU
   (llama.cpp) แต่ pulsar/Deltafin ยืนยัน MTP/nextn ช่วย (27.5 vs 18.3)
   → วัดบน LlamaServerBackend (P7.1b)
5. **วินัย benchmark** — ทุกตัวเลขจาก script เดียว + warm-run (pulsar ทำ;
   เราทำผ่าน clean-room + cold/warm แล้ว) — ต่อยอด value-aware flag check

**ไม่ยืมได้ (ข้อจำกัดเรา):** Gen5 NVMe, 32GB VRAM, DDR5, Linux/io_uring
→ ข้อ 1–4 คือสิ่งที่ทำให้ "สร้างสิ่งที่ไม่น่าจะเป็นไปได้" บน Windows + 12GB
นี้จริง ๆ ต่อไป

> **อัปเดต 2026-08-10 (หลัง EXP-015/016/017):** ข้อ 1 (census→tiering)
> ปิด — EXP-016: ไม่มี hot layer ที่ layer granularity; ข้อ 2 (CPU lane)
> ปิด — EXP-017: CPU bandwidth-bound อยู่แล้ว; ข้อ 4 (spec-decode)
> ปิด — EXP-015: MTP ช้าลง 11–18% → **เหลือ lever เดียวจริง: ข้อ 3
> IQ2_XXS** (ลด bytes/token โจมตี bandwidth wall ตรงๆ)

## 5. Deep-dive: otheru/DeepSeek-V4-Flash-Strix-Halo-GGUF (ROCmFPx, 2.58 BPW)

### Verdict: **ไม่ทดสอบบนเครื่องนี้** (runtime incompatible) — แต่บทเรียน 3 ข้อมีค่า

| ข้อเท็จจริง | รายละเอียด |
|---|---|
| ไฟล์ | `DeepSeek-V4-Flash-0731-Abliterated-ROCMFPx-Strix-Lean-2.58bpw.gguf` 91.5 GB (85.26 GiB), 2.58 BPW, GGUF v3 deepseek4 1,328 tensors |
| Runtime | **custom types 100/101/107** (`Q4_0_ROCMFP4`, `Q4_0_ROCMFP4_FAST`, affine `Q2_0_ROCMFP2`) — mainline llama.cpp/LM Studio/Ollama **ไม่ implement** → ต้อง Ember runtime บน **ROCm (gfx1151)** เท่านั้น |
| Hardware ที่ benchmark | AMD Ryzen AI Max+ 395 + **128 GB unified memory** (Strix Halo) — decode 22.4 tok/s (DSpark, 100% acceptance), prefill 279–393 tok/s |
| Quant recipe | 129 routed-expert gate/up/down: affine Q2_0_ROCMFP2 (2.5 BPW, packed blocks 2.5 BPW ใช้ scale เป็น affine offset) · 43 attn_kv: dual-scale Q4_0_ROCMFP4 · 574 dense/shared/indexer/output: Q4_0_ROCMFP4_FAST · attn_output_b: Q8_0 · embd: Q6_K |
| Importance matrix | `DeepSeek-V4-Flash-0731-chat-v2-routed-moe-ds4-rocm.dat` (0.45 GB) — **747,650,202 expert observations** จาก 4,692 prompts / 2.9M tokens / 202,186 quantizer chunks — ใช้ calibrate quant (ไม่ใช่ placement) |
| อื่นๆ | Abliterated (ถอด refusal), 46 attn_output_b tensors, SRA rank 8, scale 2.5 · draft model `-DSpark-draft-4.25bpw.gguf` 10.9 GB (ต้อง Ember/ROCm) |

### บทเรียน 3 ข้อ (ยืมได้โดยไม่ต้องรัน)

1. **Census ที่ถูกต้อง = calibrate quant, ไม่ใช่ placement** — เขาเก็บ
   747M expert observations เพื่อลด bytes/token (imatrix) — ตรงกับข้อสรุป
   EXP-016/017 ของเราที่ว่า "ไม่มีการจัด placement ที่เหนือกว่า auto-fit"
   และเส้นทางจริงคือ **ลด bytes/token** — ยืนยันข้อ 3 (IQ2_XXS) เป็น
   ทิศทางเดียวที่ถูก
2. **2.58 BPW ทำได้จริงบน DS V4 Flash (91.5 GB vs IQ3_XXS 104 GB)** —
   ประหยัด ~12 GB (12%) ด้วย affine quant + imatrix — ถ้า format ปกติ
   (llama.cpp-compatible) มี quant ระดับนี้ ก็คือ lever ตรงๆ (bytes ↓ →
   resident ↑ → tok/s ↑ ตาม curve super-linear ของ EXP-016)
3. **DSpark spec decode ได้ 100% acceptance แต่เฉพาะเมื่อ bandwidth เหลือ**
   — 22.4 tok/s บน 128 GB unified memory (RAM ไม่ใช่คอขวด) — ยืนยัน
   EXP-015/017: spec-decode และเทคนิคเพิ่ม throughput ไร้ค่าเมื่อคอขวดคือ
   bandwidth ของเครื่องเราเอง

### สรุป

ไม่เหมาะกับระบบเราโดยตรง (ROCm-only + custom types + 91.5 GB เกินดิสก์
เหลืออยู่แล้ว) — แต่บันทึกเป็นหลักฐานสนับสนุนทิศทางเดียวที่เหลือ:
**หาทางลด bytes/token ของ DS V4 Flash ใน format ที่ llama.cpp รองรับ
(IQ2_XXS / quant เล็กลง)**

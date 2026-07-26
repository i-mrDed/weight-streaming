# Out-of-Core Execution & SSD Streaming — Research Notes

> **หัวข้อ:** การรันโมเดลที่ใหญ่กว่า RAM โดยใช้ SSD เป็น secondary memory  
> **ความเกี่ยวข้อง:** 🟢 สูงมาก — เป็น Layer 3 (Streaming Buffer) + NVMe I/O  
> **SOTA (2026):** llama.cpp expert offloading, flash-moe, MoE-Infinity

---

## 📑 งานวิจัย/โครงการที่เกี่ยวข้อง

### 1. llama.cpp + mmap Expert Offloading ⭐
| รายการ | รายละเอียด |
|--------|-----------|
| **Repository** | [llama.cpp](https://github.com/ggml-org/llama.cpp) |
| **เทคนิค** | mmap (memory-mapped file) + OS page cache + `-ot` tensor override |
| **Hardware** | CPU + GPU (NVIDIA, AMD, Apple Silicon) |
| **MoE flag** | `-ot ".ffn_.*_exps.=CPU"` → expert weights อยู่ CPU, attention/shared อยู่ GPU |

**ผลการทดสอบจริง (Windows, RTX 3060 12GB + 16GB RAM + NVMe 1.5 GB/s):**
- Qwen3-30B-A3B Q8_0 (32GB) → **2.5–4.3 tok/s**
- OS page cache ทำหน้าที่ LRU cache อัตโนมัติ
- Hit → instant, Miss → stream จาก SSD ~1.5 GB/s

**ข้อจำกัด:**
- mmap reactive — ไม่มี prefetching → page fault → stall
- OS ไม่รู้ MoE topology → cache policy ไม่เหมาะกับ expert access pattern
- **นี่คือสิ่งที่ Speculative Weight Streaming จะแก้**

---

### 2. flash-moe (Daniel Isaac / danpacary) ⭐
| รายการ | รายละเอียด |
|--------|-----------|
| **Repository** | [flash-moe](https://github.com/danpacary/flash-moe) |
| **เทคนิค** | Parallel `pread()` + Metal compute |
| **Hardware** | Apple Silicon (48 GB MacBook) |
| **ผลลัพธ์** | Qwen3.5-397B → **4.4 tok/s** |
| **58 experiments** | บันทึก findings ละเอียด |

**Lessons learned:**
- SSD speed สำคัญมาก (17.5 GB/s Apple SSD)
- Parallel I/O หลาย expert พร้อมกัน
- Buffer management: ต้อง balance ระหว่าง prefetch depth vs memory

---

### 3. llama-cpp-moe-flash (cecil-the-coder) ⭐
| รายการ | รายละเอียด |
|--------|-----------|
| **Repository** | [llama-cpp-moe-flash](https://github.com/cecil-the-coder/llama-cpp-moe-flash) |
| **เทคนิค** | io_uring async I/O + SSD streaming + Vulkan GPU compute |
| **Hardware** | AMD Ryzen AI 365 (Strix Halo) 120 GB UMA |
| **ผลลัพธ์** | 7–10 tok/s สำหรับ >GTT models |

**Key features:**
- Async expert prefetch with io_uring
- Auto-detect buffer sizing
- Slot remapping สำหรับ >GTT models
- **Production-ready** (8 MoE models validated)

**ความเกี่ยวข้อง:** แนวทาง async prefetch + expert buffer management = คล้าย Speculative Weight Streaming

---

### 4. DeepSeek-V4-Flash on 64GB Strix Halo
| รายการ | รายละเอียด |
|--------|-----------|
| **Gist** | [by AlexsJones](https://gist.github.com/AlexsJones/9b43e7b8f3682679d17f255a3ca0d9d3) |
| **เทคนิค** | mmap on, mlock off → OS page cache เก็บ attention core (~13 GB) |
| **โมเดล** | DeepSeek-V4-Flash (284B params, 2-bit → 81 GB GGUF) |
| **Hardware** | 64 GB Strix Halo → **~1.9 tok/s** |
| **ข้อค้นพบ** | - mmap ON, mlock OFF (ตรงข้ามกับปกติ)<br>- 4-6 threads optimal<br>- cgroup guard ป้องกัน OOM |

---

### 5. MoE-Infinity (2024)
| รายการ | รายละเอียด |
|--------|-----------|
| **Paper** | [MoE-Infinity: Efficient MoE Inference on Personal Machines with Sparsity-Aware Expert Cache](https://arxiv.org/abs/2401.14361) |
| **แนวคิด** | Sparsity-aware expert cache — เก็บเฉพาะ experts ที่เรียกบ่อย |
| **Cache policy** | ใช้ expert popularity + temporal locality |
| **ความเกี่ยวข้อง** | Cache policy reference สำหรับ streaming buffer |

---

### 6. MoE-Lightning (2024)
| รายการ | รายละเอียด |
|--------|-----------|
| **Paper** | [MoE-Lightning: High-Throughput MoE Inference on Memory-constrained GPUs](https://www.semanticscholar.org/paper/MoE-Lightning%3A-High-Throughput-MoE-Inference-on-Cao-Liu/07f1fbd2a036d3e75a9fb00b30a413981b7ff17e) |
| **แนวคิด** | Model weights in CPU DRAM → paged to GPU HBM via pinned-memory buffers |

---

### 7. SSD Offloading — Energy Perspective
| รายการ | รายละเอียด |
|--------|-----------|
| **Paper** | [SSD Offloading for LLM MoE Weights Considered Harmful in Energy Efficiency](https://arxiv.org/abs/2508.06978) |
| **ข้อค้นพบ** | SSD offloading → energy เพิ่ม **~12x** vs HBM (DeepSeek-R1)<br>แต่สำหรับ batch size เล็ก + MoE sparsity → อาจ viable ในอนาคต |
| **Implication** | สำหรับ desktop use (ไม่ใช่ data center) → energy เป็น secondary concern |

---

### 8. I/O Characterization (HotStorage'25)
| รายการ | รายละเอียด |
|--------|-----------|
| **Paper** | [An I/O Characterizing Study of Offloading LLM Models and KV Caches to NVMe SSD](https://dl.acm.org/doi/10.1145/3719330.3721230) |
| **ข้อค้นพบ** | Block-level I/O trace analysis ของ DeepSpeed + FlexGen offloading |

---

## 📊 Performance Comparison

| System | Hardware | Model | Speed | Buffer |
|--------|----------|-------|-------|--------|
| llama.cpp + mmap | RTX 3060 + 16GB RAM | Qwen3-30B-A3B Q8 (32GB) | 2.5–4.3 tok/s | OS page cache |
| flash-moe | 48GB MacBook | Qwen3.5-397B | 4.4 tok/s | Custom buffer |
| llama-cpp-moe-flash | Strix Halo 128GB | >GTT models | 7–10 tok/s | io_uring + buffer |
| DeepSeek V4 Strix | 64GB Strix Halo | DSv4 284B IQ2 (81GB) | ~1.9 tok/s | mmap + page cache |
| **Our target** | **32-64GB + NVMe** | **K3 2.8T (1.4TB)** | **>2 tok/s** | **Predictive buffer** |

---

## 🔑 Key Takeaways

| ข้อ | รายละเอียด |
|-----|-----------|
| 1 | SSD Streaming **ใช้ได้จริง** — มีหลายโครงการที่ run จริง |
| 2 | ความเร็วปัจจุบัน 1.9–4.3 tok/s — **ยังต่ำกว่าเป้า** (< 5 tok/s) |
| 3 | ปัญหาหลักคือ **reactive mmap** → page fault stall |
| 4 | **Speculative Weight Streaming แตกต่างตรง:** Predictive (ไม่ reactive) + structure-aware |
| 5 | OS page cache ไม่รู้ MoE topology → custom buffer management ดีกว่า |
| 6 | io_uring (Linux) หรือ IOCP (Windows) = foundation สำหรับ async I/O |

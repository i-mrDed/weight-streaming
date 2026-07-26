# Near-Storage Computing — Research Notes

> **หัวข้อ:** การย้าย compute ไปที่ SSD (computational storage)  
> **ความเกี่ยวข้อง:** 🟡 ปานกลาง — แนวทางเสริม (Section 6.1)  
> **สถานะ:** ยังเน้น CNN/GNN เป็นหลัก, LLM inference เพิ่งเริ่มมีงาน

---

## 📑 งานวิจัยที่เกี่ยวข้อง

### 1. HILOS: Near-Storage Processing for Long-Context LLMs (ASPLOS'26) ⭐
| รายการ | รายละเอียด |
|--------|-----------|
| **Paper** | [A Cost-Effective Near-Storage Processing Solution for Offline Inference of Long-Context LLMs](https://arxiv.org/abs/2502.09921) |
| **แนวคิด** | ใช้ FPGA near SSD เร่ง attention operation |
| **เทคนิค** | Attention offload → near-storage accelerator |
| **Target** | Long-context offline inference |
| **ความเกี่ยวข้อง** | แสดงแนวโน้มการนำ near-storage มาใช้กับ LLM |

---

### 2. Samsung SmartSSD + FPGA Neural Network Accelerator
| รายการ | รายละเอียด |
|--------|-----------|
| **Paper** | [Enabling Computational Storage through FPGA Neural Network Accelerator for Enterprise SSD](https://ieeexplore.ieee.org/document/8765616) (2019) |
| **Platform** | Samsung SmartSSD — FPGA บน SSD controller |
| **งานที่เกี่ยวข้อง** | - RM-SSD: In-storage computing for recommendation inference<br>- SmartSAGE: GNN training using in-storage processing |
| **ข้อจำกัด** | FPGA compute power จำกัด — ไม่เหมาะกับ LLM scale |

---

### 3. Fusing In-storage and Near-storage Acceleration (ACM JETC, 2023)
| รายการ | รายละเอียด |
|--------|-----------|
| **Paper** | [Fusing In-storage and Near-storage Acceleration of CNNs](https://dl.acm.org/doi/10.1145/3597496) |
| **แนวคิด** | NAND flash accelerator + FPGA accelerator สำหรับ CNN |
| **เทคนิค** | Heterogeneous architecture — in-storage + near-storage |
| **ข้อจำกัด** | เน้น CNN (video analytics) — ไม่ใช่ Transformer |

---

### 4. Computational Storage for AI Training (PatSnap, 2025)
| รายการ | รายละเอียด |
|--------|-----------|
| **รายงาน** | [Computational Storage Architectures for AI Model Training](https://eureka.patsnap.com/report-research-on-computational-storage-architectures-for-ai-model-training) |
| **แนวโน้ม** | Smart SSD with ARM processor / NPU → In-situ data processing |
| **Patent** | US20240127056A1: DRAM buffering + SSD/FPGA dimensionality reduction + GPU training |

---

### 5. HolisticGNN: Near-Storage GNN Inference (USENIX FAST'22)
| รายการ | รายละเอียด |
|--------|-----------|
| **Paper** | [Hardware/Software Co-Programmable Framework for Computational SSDs](https://www.usenix.org/conference/fast22/presentation/kwon) |
| **แนวคิด** | Near-storage GNN inference framework |
| **ความเกี่ยวข้อง** | แสดงให้เห็นว่า near-storage compute มีประโยชน์กับ graph-based models |

---

## 💡 Near-Storage สำหรับ Speculative Weight Streaming

### แนวทางที่เป็นไปได้

```
SSD Controller Board
├── Flash Chips (weights 1.4 TB)
├── FPGA / NPU
│   ├── Matrix-vector multiply สำหรับ expert weights
│   ├── ส่งผลลัพธ์กลับ host (~KB)
│   └── ประหยัด bandwidth PCIe
└── Host RAM → result buffer (~256 MB)
```

### ข้อจำกัดสำหรับ LLM

| ข้อจำกัด | รายละเอียด |
|---------|-----------|
| **FPGA compute** | Matrix multiply 2.8T parameters → FPGA เทียบ GPU ไม่ได้ |
| **Bandwidth** | NVMe to FPGA < NVMe to CPU/GPU |
| **ความยืดหยุ่น** | ต้อง custom accelerator สำหรับแต่ละ architecture |
| **ต้นทุน** | FPGA development cost สูง |

### สรุป

> Near-storage computing น่าสนใจแต่ **ยังไม่成熟พอ** สำหรับ LLM inference  
> แนวทางนี้ควรรอให้ hardware (Samsung SmartSSD รุ่นถัดไป, CXL-based computational memory) 成熟 ก่อน  
> ปัจจุบัน **Speculative Weight Streaming โดยไม่ต้อง near-storage** ก็ feasible แล้ว

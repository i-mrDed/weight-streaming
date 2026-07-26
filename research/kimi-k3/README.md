# Kimi K3 Architecture — Research Notes

> **หัวข้อ:** รายละเอียดสถาปัตยกรรม Kimi K3 (กรณีศึกษา)  
> **Released:** July 16, 2026 | **Open weights:** July 27, 2026  
> **Developer:** Moonshot AI

---

## 📋 Spec Sheet

| Spec | Value |
|------|-------|
| **Total parameters** | 2.8 trillion (2.8T) |
| **Architecture** | Mixture-of-Experts (MoE) |
| **Experts** | 896 total, **16 active per token** (~1.8%) |
| **Active params/token** | ~50B equivalent |
| **Context window** | 1,048,576 tokens (1M) |
| **Attention** | Kimi Delta Attention (KDA) — hybrid linear attention |
| **Residuals** | Attention Residuals (AttnRes) |
| **Routing** | Stable LatentMoE + Quantile Balancing |
| **Weight precision** | MXFP4 (4-bit), QAT-trained |
| **Activation precision** | MXFP8 |
| **Activation function** | Sigmoid Tanh Unit (SiTU) |
| **Optimizer** | Per-Head Muon |
| **KV cache** | Gated Multi-head Latent Attention (Gated MLA) |
| **Modality** | Text + Vision (native, not adapter-based) |
| **Reasoning** | Always-on thinking mode |
| **License** | Modified MIT |

---

## 🏗️ Architecture Deep Dive

### Kimi Delta Attention (KDA)
- Hybrid linear attention mechanism
- **3:1 linear-to-full attention interleave**
- Up to **6.3x faster decoding** in million-token contexts
- Up to **75% KV-cache reduction**
- Key insight for us: KDA reduces KV cache size → more RAM for streaming buffer

### Attention Residuals (AttnRes)
- Selective retrieval across depth (ไม่ใช่ accumulate แบบ uniform)
- ~25% higher training efficiency at <2% additional cost
- Drop-in replacement สำหรับ residual connections

### Stable LatentMoE
- Latent-space routing (ไม่ใช่ token-level routing ปกติ)
- **Quantile Balancing:** Derive expert allocation จาก router-score quantiles
- ไม่มี heuristic updates หรือ sensitive balancing hyperparameter
- **Soft dropping** สำหรับ overflow tokens

### Weight Sizing

| Component | Size (MXFP4) | Notes |
|-----------|-------------|-------|
| Total weights | ~1.4 TB | All 896 experts + shared + attention |
| Per expert (1 layer) | ~4 MB | 8B active / 896 experts per layer |
| 16 experts/token | ~64 MB | ทั้งหมดที่ต้องใช้ต่อ token |
| Non-MoE (attention, embedding) | ~50 GB | Shared across all tokens |
| KV cache (1M context) | ~8-16 GB | With Gated MLA compression |

---

## 📊 Feasibility Analysis Update (Based on Actual Specs)

### Bandwidth
| Component | K3 Actual | Our Estimate |
|-----------|-----------|-------------|
| Expert size | ~4 MB/MoE layer | ✅ ตรงกับที่ประมาณ |
| Experts/token | 16 | ✅ ตรง |
| Weight per token | 64 MB (if miss) | ✅ ตรง |
| NVMe needed | 64 MB / target latency | ✅ Bandwidth ไม่ใช่ bottleneck |

### Memory Budget (อัปเดต)
| Component | RAM Use | Notes |
|-----------|---------|-------|
| Draft model | ~6-14 GB | EAGLE head = เล็กกว่า |
| KV cache | ~8-16 GB | KDA ลด 75% → น้อยกว่าที่คิด |
| Streaming buffer | ~256 MB | 16 experts |
| **Total** | **~15-30 GB** | **✅ เหลือพื้นที่มากขึ้น** |

### Key Update
> KDA's KV-cache reduction (75%) → **RAM budget เพิ่มขึ้น ~8 GB**  
> → streaming buffer ขยายเป็น ~512 MB หรือ draft model ใหญ่ขึ้นได้

---

## 📝 Insights for Speculative Weight Streaming

### 1. MXFP4 Precision
- K3 ใช้ MXFP4 weights อยู่แล้ว → เราไม่ต้อง quantize เพิ่ม
- 1 expert = ~4 MB → pre-fetch เร็ว

### 2. Quantile Balancing Routing
- ต่างจาก Top-k routing ปกติ
- **Challenge:** Predictor ต้องเข้าใจ Quantile Balancing logic
- **Opportunity:** Quantile-based = deterministic กว่า → predict ง่ายขึ้น?

### 3. Gated MLA KV Cache
- KV cache เล็กกว่าเดิม → เหลือ RAM สำหรับ buffer
- แต่ MLA อาจมี attention pattern ที่ซับซ้อนกว่า

### 4. KDA Hybrid Attention
- Linear attention ส่วนหนึ่ง → อาจลด I/O สำหรับ attention weights
- แต่ยังต้อง load expert weights ตามปกติ

### 5. SiTU Activation
- Custom activation function → compute ต่างจาก standard MoE
- อาจต้อง custom kernel → มีผลต่อ execution engine design

---

## 🔗 แหล่งอ้างอิง

| แหล่ง | URL |
|-------|-----|
| Official Blog | [kimi.com/blog/kimi-k3](https://kimi.com/blog/kimi-k3) |
| HuggingFace Model Card | [huggingface.co/blog/ResterChed/kimi-k3](https://huggingface.co/blog/ResterChed/kimi-k3-model-overview-mxfp4-quantization-open-wei) |
| OpenLM.ai Summary | [openlm.ai/kimi-k3](https://openlm.ai/kimi-k3) |
| Morph LLM | [morphllm.com/kimi-k3](https://www.morphllm.com/kimi-k3) |
| GLM5 Blog | [glm5.app/blog/what-is-kimi-k3](https://glm5.app/blog/what-is-kimi-k3) |

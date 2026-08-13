# 2. Related Work

> **Status:** draft (Phase 5, TASKS.md) · 2026-08-13 · ตาม `research/paper/OUTLINE.md`
> + `related-work-notes.md` · ตัวเลขอ้างอิง experiment จริงใน repo

---

## 2.1 Large-model inference and serving

The dominant serving stacks — vLLM, TensorRT-LLM, llama.cpp — assume the
model's weights are resident in GPU VRAM or RAM. vLLM's continuous
batching and PagedAttention optimize compute-bound serving on
datacenter-class hardware [cite vLLM]; llama.cpp pioneered CPU-first
inference with mmap-backed weight loading, which is the substrate our
work builds on [cite llama.cpp]. None of these systems publish the
>RAM case: the regime where the working set exceeds physical memory and
every token faults part of the model back from disk. That gap is exactly
the one this paper measures.

## 2.2 MoE efficiency

Sparse activation makes MoE attractive for inference: only the top-k
experts per token are computed (e.g. 16 of 896 in K3-class routers), so
the *compute* per token is a fraction of the dense-equivalent model. But
the *bytes* that must be touched per token still scale with the active
set, and on consumer hardware the binding constraint is memory and its
bandwidth, not FLOPs.

Quantization is the lever that moves bytes/token. Our own measurements
show IQ1_M vs IQ2_M on Qwen3.6-35B-A3B = 77 vs 56 tok/s (EXP-011); the
community result is the same — lower bits mean more of the model stays
resident and fewer faults per token. We additionally found that expert
activation is *flat* across layers on our test model, so "hot-expert"
tiering has no layer-level structure to exploit (EXP-014/016) — a
finding that motivates our buffer-centric (not predictor-centric)
conclusion.

## 2.3 Weight prefetching and speculative decoding

Two families of work attack the I/O cost of MoE inference from opposite
directions.

**Prediction-driven expert scheduling.** LayerScope (formerly PreScope,
arXiv:2509.23638, ICS'26) is the closest system to ours: it prefetches
expert weights ahead of the router's decision using a learnable
layer-aware predictor (LLaPor, >90% Top-4 accuracy), a cross-layer
global scheduler (PreSched), and an asynchronous I/O optimizer
(AsyncIO), reporting 141% higher throughput and 74.6% lower latency
than prior CPU-GPU offloading systems. The key difference is the *tier*:
LayerScope moves experts between GPU VRAM and CPU RAM over PCIe (a
bandwidth gap of ~10×), whereas our disk-mmap tier moves weights between
disk and RAM over page faults (an effective gap of ~50× against the
NVMe spec, ~0.38 GB/s vs 19.18 GB/s — EXP-025). The prefetch payoff is
a function of that gap: the larger the hit/miss bandwidth ratio, the
higher the hit rate must be (EXP-029). LayerScope's lesson — prediction
accuracy matters when the miss cost is high — transfers directly to our
>RAM regime, where we show buffer *size* (not predictor cleverness) is
the dominant lever (EXP-002/029).

**Speculative decoding.** EAGLE-3 (arXiv:2503.01840) accelerates
generation by drafting *tokens* with a small draft model (direct token
prediction + multi-layer feature fusion), achieving up to 6.5× speedup
on datacenter GPUs. This is a different axis from ours — it reduces
compute/attention cost, not weight-movement cost. On our bandwidth-bound
consumer machine, we measured the MTP speculative head as *slower*
(−11–18%, EXP-015): the draft pass still runs the full forward over the
same weight bytes, and the larger model file reduces residency. (The
related dead ends — flat expert traffic EXP-016, CPU-lane compute
EXP-017 — reinforce the same point from other angles.) The lesson unifies both directions: speculation (of tokens
or weights) only pays when what you are waiting for costs more than what
you speculate — on a disk-bound pipeline, the speculative work itself
competes for the same scarce bandwidth.

## 2.4 Honest benchmarking and telemetry

Our methodological contribution sits here. Prior systems report
throughput on the models they *can* run; for the >RAM case the honest
numbers — page faults per token, disk MB per token, effective disk
bandwidth — are rarely published, because the results are unflattering.
We ship this telemetry in production (`generation.paging` in `/v1/stats`,
measured at the OS level) and reduce it to a calibrated physics model
(`tok/s = effective bandwidth ÷ bytes per token`) that predicts real
hardware within ±9% (EXP-025/028). We also contribute a buffer
abstraction (`BufferBackend`) that maps both simulator buffers and
production OS signals to one view, so the simulator and the real engine
speak the same language (EXP-026).

---

## Position summary

| Dimension | LayerScope (2509.23638) | EAGLE-3 (2503.01840) | This work |
|---|---|---|---|
| Bottleneck | PCIe (GPU↔CPU) | compute/attention | disk→RAM (page faults) |
| Mechanism | expert prefetch + schedule | token-level drafting | physics model + telemetry + buffer sizing |
| Hardware | GPU+CPU legacy servers | datacenter GPUs | consumer (CPU-only / small VRAM) |
| Reported | +141% TP, −74.6% latency | up to 6.5× | honest >RAM number + calibrated prediction (24× buffer upside on K3) |
| Evidence | sim + their hardware | their hardware | OS-level telemetry + 29 open experiments |

**Differentiator:** none of the above publishes the number for a model
larger than the machine, with OS-level telemetry and a physics model
that predicts the cost before you buy hardware.

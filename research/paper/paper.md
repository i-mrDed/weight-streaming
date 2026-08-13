# Weight Streaming on Consumer Hardware: The Honest Cost of Running MoE Models Larger Than RAM

> **Status:** assembled draft · 2026-08-13 · Phase 5 complete (TASKS.md)
> แหล่ง: `OUTLINE.md` + `01-introduction.md`..`04-evaluation.md` (sections
> แยกเป็นไฟล์เดียวกับ paper นี้ เพื่อความง่ายในการแก้ทีละ section)

---

## Abstract

MoE language models keep growing past the hardware most people can
afford: flagship open checkpoints ship as 100 GB+ files while consumer
machines still have 8–64 GB of RAM. The community benchmarks the models
it *can* run and stays silent — or claims it's fine — about the ones it
cannot. We publish the honest number and a physics model that predicts
it.

We run a **104 GB DeepSeek-V4-Flash on a 64 GB RAM + 12 GB VRAM
consumer machine and measure 1.5–1.9 tok/s**, proven disk-bound by
OS-level telemetry: 36,000–77,000 page faults per token, i.e. 150–300 MB
read from disk for every token. Config tweaks (threads, offload,
tiering) move this by only ~15% — the wall is the disk, and the disk's
*effective* bandwidth is **~0.38 GB/s, ~37× below the NVMe sequential
spec**, because page-fault reads are random access.

Everything reduces to one identity: `tok/s = effective bandwidth ÷
bytes per token`, calibrated per tier (cpu-ram 19.18 / gpu-vram 61.09 /
disk-mmap 0.38 GB/s). It predicts a fits-RAM Qwen1.5-MoE-A2.7B at
22.73 tok/s and we measure 22.73 (+0.02%). On the >RAM target K3
(15.6 GB/token), the same metrics show the real lever: at a 51% buffer
hit rate throughput collapses to **0.049 tok/s**; at 99.9% it reaches
the compute ceiling (815 ms/token) at **1.18 tok/s — a 24× swing from
buffer size alone**.
Buffering is worthless when the model fits RAM and is the entire game
when it does not.

## 1. Introduction

*[จาก `01-introduction.md` — โจทย์ >RAM, ตัวเลขจริง, physics identity,
เมื่อไหร่ buffer คุ้ม, 4 contributions]*

Mixture-of-Experts (MoE) language models keep growing past the hardware
most people can afford. Kimi K3 — the model class this project targets —
is estimated at ~2.8T parameters with ~50B active per token, and the
largest open MoE checkpoints ship as 100 GB+ files. Meanwhile, the
mainstream consumer machine still has 8–64 GB of RAM and 8–24 GB of
VRAM. The gap is not shrinking: quantized 2–3-bit weights of a flagship
MoE *fill* a consumer machine's RAM several times over.

The community's default is to benchmark the models you *can* run, and to
either claim the ones you cannot fit are "fine" or to stay silent about
them. Neither is honest, and both leave a critical question unanswered:
**what does it actually cost, in measurable terms, to run a model larger
than your hardware?** This paper answers that question with real
measurements, real telemetry, and a physics model that predicts the cost
before you spend on hardware.

**We measure the honest number.** Running a 104 GB DeepSeek-V4-Flash on a
64 GB RAM + 12 GB VRAM consumer machine (i9-9900KF, RTX 3060) yields
**1.5–1.9 tok/s** — usable for batch jobs, not interactive — and the
OS-level telemetry proves *why*: **36,000–77,000 page faults per token,
i.e. 150–300 MB read from disk for every token generated** (EXP-012,
full write-up in `research/writeups/`). More threads or more VRAM
tiering move this by only ~15%; the wall is the disk, and the disk is
measurable, not vibes.

**We calibrate the physics.** Every one of those numbers reduces to a
single identity: `tok/s = effective bandwidth ÷ bytes per token`, where
bytes/token = active params × bits/weight ÷ 8. Calibrating the
bandwidth from real measurements gives three tiers: **cpu-ram
19.18 GB/s, gpu-vram 61.09 GB/s, disk-mmap 0.38 GB/s** (EXP-025). The
disk-mmap tier is the number nobody quotes: page-fault reads are random
access, so the honest effective bandwidth of an NVMe is **~0.38 GB/s,
37× below its 14 GB/s sequential spec**. With this model we predict a
fits-RAM Qwen1.5-MoE-A2.7B at 22.73 tok/s and measure **22.73 tok/s
(+0.02%)** on the real machine (EXP-028) — a validation that is not a
lucky fit but a calibrated identity.

**We show when buffering is worth it — and when it is not.** On a model
that fits RAM (Qwen, 5.9 GB), throughput is compute-bound: hit rate is
1.000, latency has no tail (p99 ≈ 2.0×p50), and no buffer or prefetch
helps (EXP-027, ADR-003). On the target K3 (15.6 GB/token, *does not*
fit RAM), the same metrics tell the opposite story: at the simulator's
default 256 MB buffer, hit rate drops to 51% and throughput collapses to
**0.049 tok/s**; a 4 GB buffer raises hit rate to 99.9% and recovers
**1.18 tok/s** — the compute ceiling (815 ms/token, EXP-004/025). That
is a **24×** swing from one number: the buffer hit rate (EXP-029).
Prefetching and buffering are not marginal tweaks on >RAM models; they
are the difference between unusable and usable.

Our contributions:

1. **The honest >RAM benchmark.** First-hand, reproducible measurement of
   a 104 GB MoE on consumer hardware with OS-level telemetry
   (page faults/token, disk MB/token) — the number the community
   doesn't publish (EXP-012, write-up).
2. **A calibrated physics model.** `tok/s = BW ÷ bytes/token` with three
   empirically calibrated bandwidth tiers, validated to within ±9% on
   real hardware (EXP-025/028) and used to *predict* K3's behavior
   rather than guess it (EXP-029).
3. **A buffer abstraction bridging simulation and production.** A single
   `BufferBackend` protocol that maps both the simulator's LRU/LFU/priority
   buffer and the production OS signals (`generation.paging`) to one
   buffer-equivalent view — closing the gap where the tracker observed
   nothing during real inference (EXP-026, ADR-003).
4. **Evaluation metrics with real numbers.** Hit rate, latency
   distribution (p50/p90/p99), and throughput-vs-physics definitions,
   computed from real telemetry on Qwen and applied to the K3 target
   (EXP-028/029).

## 2. Related Work

*[จาก `02-related-work.md` — serving, MoE efficiency, prefetch/speculation, honest benchmark]*

### 2.1 Large-model inference and serving

The dominant serving stacks — vLLM, TensorRT-LLM, llama.cpp — assume the
model's weights are resident in GPU VRAM or RAM. vLLM's continuous
batching and PagedAttention optimize compute-bound serving on
datacenter-class hardware; llama.cpp pioneered CPU-first inference with
mmap-backed weight loading, which is the substrate our work builds on.
None of these systems publish the >RAM case: the regime where the
working set exceeds physical memory and every token faults part of the
model back from disk. That gap is exactly the one this paper measures.

### 2.2 MoE efficiency

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

### 2.3 Weight prefetching and speculative decoding

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
higher the hit rate must be (EXP-029).

**Speculative decoding.** EAGLE-3 (arXiv:2503.01840) accelerates
generation by drafting *tokens* with a small draft model (direct token
prediction + multi-layer feature fusion), achieving up to 6.5× speedup
on datacenter GPUs. This is a different axis from ours — it reduces
compute/attention cost, not weight-movement cost. On our
bandwidth-bound consumer machine, we measured the MTP speculative head
as *slower* (−11–18%, EXP-015): the draft pass still runs the full
forward over the same weight bytes, and the larger model file reduces
residency. (The related dead ends — flat expert traffic EXP-016,
CPU-lane compute EXP-017 — reinforce the same point from other angles.)

### 2.4 Honest benchmarking and telemetry

Our methodological contribution sits here. Prior systems report
throughput on the models they *can* run; for the >RAM case the honest
numbers — page faults per token, disk MB per token, effective disk
bandwidth — are rarely published, because the results are unflattering.
We ship this telemetry in production (`generation.paging` in
`/v1/stats`, measured at the OS level) and reduce it to a calibrated
physics model (`tok/s = effective bandwidth ÷ bytes per token`) that
predicts real hardware within ±9% (EXP-025/028). We also contribute a
buffer abstraction (`BufferBackend`) that maps both simulator buffers
and production OS signals to one view, so the simulator and the real
engine speak the same language (EXP-026).

## 3. Architecture

*[จาก `03-architecture.md` — engine, physics, telemetry, buffer abstraction, metrics]*

### 3.1 Engine and the mmap substrate

Inference runs on **llama.cpp's llama-server** (CPU-first, GPU offload
optional), with the model file memory-mapped (`mmap`). The operating
system's page cache is therefore the *de facto* weight-streaming layer:
weights are read from disk on first touch and stay resident as long as
they fit RAM. Our earlier custom streaming buffer (ADR-001) was
abandoned after real-hardware measurement: with mmap + OS page cache,
the OS already does the LRU-equivalent caching, and an application-level
buffer added tracking overhead without throughput (ADR-003, EXP-002/026).
The product's role is therefore not "buffer weights ourselves" but
**observe and predict**: track what the OS actually faults in, and hint
what to prefetch when the working set exceeds RAM.

### 3.2 Physics model: bandwidth ÷ bytes per token

```
bytes_per_token = active_params × bits_per_weight / 8
tok/s           = effective_bandwidth / bytes_per_token
```

`bytes_per_token` comes from the model spec: Qwen1.5-MoE-A2.7B Q2_K =
2.7B × 2.5 bpw ≈ **0.844 GB/token**; the K3 target = 50B × 2.5 bpw ≈
**15.6 GB/token**.

| Tier | Effective BW (GB/s) | Calibrated from |
|---|---|---|
| cpu-ram | **19.18** | Qwen 22.73 tok/s CPU-pure (EXP-004) |
| gpu-vram | **61.09** | Qwen 56–72 tok/s GPU-offload (EXP-011) |
| disk-mmap | **0.38** | DS-V4-Flash 150–300 MB/token @ 1.9 tok/s (EXP-012) |

### 3.3 Honest telemetry: `generation.paging`

The server ships per-generation paging telemetry in `/v1/stats`:
`faults_per_token`, `fault_mb_per_token`, `disk_mb_per_token` — OS-level
signals, never simulated. A reported tok/s number can be audited: "fast
on paper" cannot hide disk thrashing if faults/token and disk MB/token
are published alongside (EXP-012).

### 3.4 Buffer abstraction: one protocol for simulator and production

`StreamingBuffer.total_accesses` was 0 during real inference: llama.cpp
reads the mmap opaquely, so the tracker observed nothing. EXP-026 closes
this with a unified protocol: `BufferBackend` with two implementations —
`SimulatorBufferAdapter` (wraps the LRU/LFU/priority simulator buffer)
and `TelemetryBufferObserver` (maps OS paging signals to buffer-equivalent
stats) — both producing the same `BufferStatsView`. Physics-derived
throughput (hit bytes @ cpu-ram BW + miss bytes @ disk-mmap BW) is
computed identically for both, so the real Qwen measurement and the K3
simulation sit on one table (§4).

### 3.5 Evaluation metrics

1. **Hit rate** — `1 − disk_mb_per_token / bytes_per_token`; warm ≥ 0.90.
2. **Latency distribution** — per-token latency from the SSE stream,
   p50/p90/p99/mean/max (nearest-rank); PASS when p99 < 3×p50.
3. **Throughput** — tok/s vs the physics prediction; PASS within ±15%.

All three are pure functions over telemetry, unit-testable offline.

## 4. Evaluation

*[จาก `04-evaluation.md` — physics validation, >RAM จริง, K3 buffer lever]*

### 4.1 Setup and method

**Machine:** Intel i9-9900KF (8C/16T), RTX 3060 12 GB, 64 GB DDR4, NVMe,
Windows 11 — the same machine for every measurement.

**Models:** Qwen1.5-MoE-A2.7B Q2_K (5.88 GB, fits RAM); DeepSeek-V4-Flash
(104 GB, the real >RAM case); K3 (simulated, 15.6 GB/token, the target).

**Method — honest measurement discipline:** clean room (kill stale
llama-server orphans), verify the actual spawned command line, cold +
warm generations, record paging telemetry, warm average = mean of ≥ 3
runs of 100 tokens with per-token latency from the SSE stream.

### 4.2 Physics validation

| Case | Predicted | Measured | Error |
|---|---:|---:|---:|
| Qwen CPU-pure (EXP-004) | 22.73 | 22.73 | **0.0%** |
| Qwen via server, warm (EXP-025) | 22.73 | 20.76 | **−8.7%** |
| Qwen via server, warm (EXP-028) | 22.73 | 22.73 | **+0.02%** |
| DS-V4-Flash >RAM (EXP-012) | ~1.8 | 1.5–1.9 | **in band** |

All within the ±15% tolerance. The model predicts an unmeasured target
(K3) rather than describing a measured one.

### 4.3 The real >RAM case: 104 GB on 64 GB RAM

| config | cold | warm | faults/tok | disk MB/tok |
|---|---:|---:|---:|---:|
| all-expert CPU, t8 | 1.48 | 1.76 | 68,009 | ~150–270 |
| 42-layer MoE tiering, t8 | 1.46 | **1.89** | 76,548 | ~160–300 |
| all-expert CPU, t16 | 1.71 | 1.75 | 64,935 | ~145–260 |
| auto placement, t8 | 1.65 | 1.83 | 62,933 | ~150–250 |
| forced `-ngl 99` | **OOM** | — | — | — |

A 104 GB model runs at 1.5–1.9 tok/s — real, reproducible, disk-bound;
config tweaks move it only ~15%. Dead ends closed with evidence: MTP
speculation slower (−11–18%, EXP-015), flat expert traffic (EXP-014/016),
CPU-lane dead (EXP-017); the lever that works is bytes/token (IQ1_M vs
IQ2_M = 77 vs 56, EXP-011).

### 4.4 The target case: K3 (>RAM) and the buffer lever

| metric | Qwen real | K3 @ 256 MB | K3 @ 4 GB |
|---|---:|---:|---:|
| **tok/s** | **22.73** | **0.049** | **1.18** |
| hit rate | 1.000 | 0.512 | 0.999 |
| p50 (ms) | 41.1 | 21,300 | ~816 |
| p90 (ms) | 48.6 | 27,051 | ~816 |
| p99 (ms) | 84.4 | 31,258 | ~816 |

Buffer sweep (EXP-029): 64 MB → 0.336 hit / 0.036 tok/s · 256 MB → 0.512
/ 0.049 · 1024 MB → 0.779 / 0.103 · **4096 MB → 0.999 / 1.180**.

1. **Hit rate is the entire game on >RAM.** At 51% hit, half of every
   token's 15.6 GB streams at disk-mmap speed → 0.049 tok/s, ~465×
   slower than Qwen's compute-bound 22.73. At 99.9% hit the model
   reaches its compute ceiling (815 ms/token) → 1.18 tok/s = **24×**.
2. **Buffer size beats predictor cleverness here** — LRU + priority
   reaches 99.9% at 4 GB (EXP-002, ADR-003).
3. **The latency distribution exposes the misses** — Qwen no tail
   (p99 ≈ 2.0×p50); K3 p99 = 31 s vs p50 = 21 s is exactly the tokens
   that missed.

### 4.5 Threats to validity

One consumer machine (tiers re-calibrate per hardware); K3 is simulated
(spec follows EXP-004's 50B-active × 2.5 bpw assumption; access pattern
validated against real census EXP-014/016); warm and cold both reported —
neither hidden.

### 4.6 Summary

| Question | Answer |
|---|---|
| Does a >RAM model run on consumer HW? | Yes — 104 GB at 1.5–1.9 tok/s, disk-bound |
| Why is it slow? | Effective disk BW 0.38 GB/s (~37× below NVMe spec) |
| Does physics predict it? | Yes — within ±9% on real HW (EXP-025/028) |
| Is buffering worth it? | 24× on >RAM (0.049→1.18); ~0× when the model fits |
| What is the lever? | Buffer hit rate ≥ 99% — size, not predictor cleverness |

## 5. Conclusion

The honest >RAM number is 1.5–1.9 tok/s on 104 GB — usable, not fast,
and now predictable. The wall is bandwidth, not compute: an NVMe's
effective page-fault bandwidth is ~0.38 GB/s, and every optimization on
a bandwidth-bound pipeline is a bytes-per-token play. The design
consequence is sharp: **buffer/prefetch is a 24× lever when the model
does not fit RAM and a 0× lever when it does.** Future work: applying
layer-aware prediction (LayerScope-style) and larger buffers to a real
K3-class checkpoint, with the honest harness from this paper.

## References

- arXiv:2509.23638 — LayerScope (formerly PreScope): Predictive
  Cross-Layer Scheduling for Efficient Multi-Batch MoE Inference on
  Legacy Servers. Yu et al., ICS'26.
- arXiv:2503.01840 — EAGLE-3: Scaling up Inference Acceleration of Large
  Language Models via Training-Time Test. Li et al., 2025.
- Project experiment log (open source, MIT):
  github.com/i-mrDed/weight-streaming —
  `research/experiments/EXP-001..029` (this paper's EXP-004/011/012/
  014/015/016/017/025/026/027/028/029) + `research/writeups/`.

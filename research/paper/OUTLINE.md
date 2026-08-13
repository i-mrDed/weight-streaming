# Paper Outline — Speculative Weight Streaming: Running MoE Models Larger Than Your Hardware, Honestly

> **Status:** draft outline (Phase 5, TASKS.md) · 2026-08-13
> **Workflow:** `phase5-paper-outline` (MongoModel rev 49)
> ทุก key claim ด้านล่างอ้างอิง experiment/write-up ที่มีอยู่จริงใน repo —
> ตัวเลขทั้งหมดมาจากการวัด ไม่ใช่สมมติ

---

## Working title (options)

- *Weight Streaming on Consumer Hardware: The Honest Cost of Running MoE Models Larger Than RAM*
- *Bandwidth Is the Wall: Physics, Telemetry, and Buffering for >RAM MoE Inference*

**Venue target:** workshop paper (MLSys/NeurIPS WANT/ES-FoMo) — empirical
systems paper, 6–8 pages. Community gap: almost nobody publishes the
number for the model you *can't* fit.

---

## Abstract (bullet sketch)

- Problem: MoE models (K3 ~2.8T, 104 GB files) exceed consumer RAM/VRAM;
  community default = claim-it's-fine or silence. We publish the honest
  number + a physics model that predicts it.
- Method: measure real >RAM inference (DeepSeek-V4-Flash 104 GB on 64 GB
  RAM + 12 GB VRAM) with OS-level telemetry (page faults/token, disk
  MB/token) — EXP-012.
- Result 1: 1.5–1.9 tok/s, **disk-bound**; effective disk bandwidth
  ~0.38 GB/s (not the 14 GB/s NVMe spec) — EXP-012/025.
- Result 2: physics identity `tok/s = bandwidth ÷ bytes/token` calibrated
  on 3 tiers (cpu-ram 19.18 / gpu-vram 61.09 / disk-mmap 0.38 GB/s)
  predicts real Qwen within ±9% (EXP-025), 22.73 tok/s warm (EXP-028).
- Result 3: on the target K3 (15.6 GB/token), buffer size is the lever:
  51% hit → 0.049 tok/s vs 99.9% hit → 1.18 tok/s (**24×**) — EXP-029.
- Claim: for models that fit RAM, buffering is worthless (ADR-003,
  EXP-026/027); for >RAM models, hit rate ≥ 99% is the difference between
  unusable and usable.

---

## 1. Introduction

**Key claims + evidence:**

1. **The gap:** benchmarking culture covers models you *can* run; the
   >RAM case is either exaggerated or ignored. (Motivation — write-up
   EXP-012; no experiment needed, cite community practice.)
2. **The honest number exists and is reproducible:** 104 GB model on a
   64 GB machine runs at 1.5–1.9 tok/s, measured with OS telemetry
   (36k–77k faults/token, 150–300 MB/token). [EXP-012, write-up]
3. **The bottleneck is quantifiable, not vibes:** `tok/s = BW ÷
   bytes/token`; the disk-mmap tier is 0.38 GB/s effective — **50× slower
   than RAM, 37× slower than NVMe spec**. [EXP-025]
4. **Consequence for design:** prefetch/buffer only pays when the model
   doesn't fit; when it fits, compute-bound (ADR-003, EXP-027).
5. Contributions list: (a) honest >RAM benchmark + telemetry method,
   (b) calibrated physics model, (c) buffer-abstraction protocol bridging
   simulator ↔ production telemetry, (d) evaluation metrics
   (hit rate / latency / throughput) with real numbers.

**Gap before writing:** none blocking — need to finalize the "community
silence" claim with 2–3 concrete citations (to add during Related Work).

---

## 2. Related Work

**Sections + claims:**

1. **Large-model serving** (vLLM, TensorRT-LLM, llama.cpp) — assumption:
   weights resident. We're the >RAM case. (Survey EXP: Phase 1 survey +
   ADR-001/003 references.)
2. **MoE efficiency** (Mixtral, Qwen-MoE, K3 architecture survey — TASKS
   #109 done) — expert routing, quant (IQ1_M vs IQ2_M = 77 vs 56 tok/s,
   EXP-011/EXP-015), our finding: expert activation is flat → no "hot
   layer" to tier [EXP-014/015].
3. **Prefetching / weight streaming** (PreScope 2509.23638, EAGLE-3
   2503.01840 — papers marked "to read" in TASKS) — our position: buffer
   size + hit rate dominates; predictor accuracy secondary [EXP-002,
   ADR-003].
4. **Honest benchmarking / telemetry** — our contribution: page-fault
   level telemetry shipped in production (`generation.paging`) +
   buffer-abstraction protocol [EXP-026, code].

**Gap before writing:** **must read PreScope + EAGLE-3** (TASKS.md Phase 1
open items) — currently only cited from survey notes; needs real
positions to compare against.

---

## 3. Architecture (System)

**Structure + claims:**

1. **Engine:** llama.cpp (llama-server) + mmap; OS page cache does the
   "streaming" for free; our layer adds *tracking + prefetch hints*
   (ADR-003 pivot from custom buffer). [ARCHITECTURE.md §0, ADR-003]
2. **Physics model:** `bytes_per_token = active_params × bpw / 8`;
   `tok/s = effective_BW ÷ bytes_per_token`; calibrated BW per tier from
   real measurements. [EXP-025, `simulator/physics.py`]
3. **Telemetry:** `generation.paging` (faults/token, disk MB/token)
   shipped in `/v1/stats`; honest = OS signals, not simulated.
   [code, EXP-012]
4. **Buffer abstraction protocol:** unified `BufferBackend` —
   `SimulatorBufferAdapter` (existing LRU/LFU/priority buffer) and
   `TelemetryBufferObserver` (OS signals → buffer-equivalent stats);
   closes the `total_accesses = 0` gap. [EXP-026]
5. **Evaluation metrics:** hit rate / latency distribution (p50/p90/p99) /
   throughput vs physics tolerance ±15%. [EXP-028]

**Gap before writing:** EXP-026/028 cover the abstraction + metrics;
need a system diagram (1 figure) — no new experiment required.

---

## 4. Evaluation

**Main table (real data, from EXP-028/029):**

| metric | Qwen real (fits RAM) | K3 sim (>RAM) @256MB | K3 sim @4GB |
|--------|---------------------|----------------------|-------------|
| tok/s | **22.73** | **0.049** | **1.18** |
| hit rate | 1.000 | 0.512 | 0.999 |
| p50 (ms) | 41.1 | 21,300 | ~816 |
| p90 (ms) | 48.6 | 27,051 | ~816 |
| p99 (ms) | 84.4 | 31,258 | ~816 |

Sub-sections:

1. **Setup:** machine (i9-9900KF / RTX 3060 12GB / 64GB RAM), models
   (Qwen1.5-MoE-A2.7B Q2_K 5.88 GB; DS-V4-Flash 104 GB; K3 sim), method
   (clean-room measure + warm runs, honest cold/warm split).
   [EXP-012/025/028]
2. **Physics validation:** Qwen warm 22.73 vs predicted 22.73 (+0.02%,
   EXP-028); earlier 20.76 vs 22.73 (−8.7%, EXP-025) — both within ±15%
   tolerance; DSv4 within band. [EXP-025/028]
3. **>RAM real:** 1.5–1.9 tok/s, disk-bound, config tweaks ≤ 15% gain,
   4 dead ends closed. [EXP-012]
4. **K3 prediction:** buffer sweep table (64 MB → 16 GB) showing the
   non-linear hit-rate → throughput curve; 24× upside.
   [EXP-029]
5. **Latency distribution:** Qwen no tail (p99 ≈ 2.0×p50); K3 tail is
   the miss signal. [EXP-028/029]

**Gap before writing:** **Phase 1 open task "Test llama.cpp expert
offloading"** would strengthen §4.3 (tiering evidence beyond
`n-cpu-moe`); optional. The `--thai` quality gate (9 questions) exists as
a bonus eval if space allows [bench/thai.py].

---

## 5. Method / Reproducibility (short, optional)

- Clean-room measurement discipline (kill stale servers, verify spawned
  cmdline, cold + warm) — `weight_stream/bench/measure.py`.
- Hermetic test suite (459 tests, 7 skipped) — no network/model needed
  for metric math.
- All logs: `research/experiments/EXP-001..029` + write-up.

---

## 6. Conclusion

- The honest >RAM number: 1.5–1.9 tok/s on 104 GB — usable, not fast.
- The physics: bandwidth wall, not compute; effective disk BW 0.38 GB/s.
- The design consequence: buffer/prefetch = 24× on >RAM, 0× on fits-RAM.
- Future: PreScope-style access prediction + larger buffer on real K3.

---

## Section → evidence map

| Section | Primary evidence | Status |
|---------|-----------------|--------|
| Intro | EXP-012 write-up, EXP-025/027 | ✅ ready |
| Related Work | survey notes; PreScope/EAGLE-3 **to read** | ⚠️ needs reading |
| Architecture | ADR-003, EXP-025/026, code | ✅ ready (needs figure) |
| Evaluation | EXP-012/025/028/029 | ✅ ready |
| Method | bench/measure.py, tests | ✅ ready |

## Open gaps (must-do before writing each section)

1. **Read PreScope (2509.23638) + EAGLE-3 (2503.01840)** — TASKS.md
   Phase 1 open items; needed for Related Work §2.3.
2. **(Optional) Test llama.cpp expert offloading** — would strengthen
   Evaluation §4.3 tiering claims.
3. **System diagram (1 figure)** for Architecture — no experiment needed.
4. **2–3 citations for "community silence"** in Intro — to collect during
   Related Work reading.

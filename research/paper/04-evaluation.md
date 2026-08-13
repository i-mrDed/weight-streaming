# 4. Evaluation

> **Status:** draft (Phase 5, TASKS.md) · 2026-08-13 · ตาม `research/paper/OUTLINE.md`
> ทุกตัวเลขมาจากการวัดจริง (EXP-012/025/028/029) — วิธีวัดใน §4.1

---

## 4.1 Setup and method

**Machine (consumer, fixed):** Intel i9-9900KF (8C/16T), NVIDIA RTX 3060
**12 GB**, **64 GB DDR4**, NVMe, Windows 11 — the same machine for every
measurement in this paper.

**Models:**
- **Qwen1.5-MoE-A2.7B Q2_K** (5.88 GB, 2.7B active) — fits RAM; the
  compute-bound reference (EXP-004/025/028).
- **DeepSeek-V4-Flash-0731** (104 GB UD-IQ3_XXS across 4 shards, 34B
  active) — the real >RAM case (EXP-012).
- **K3 (simulated)** — 896 experts / 16 active / 50B active per token
  (15.6 GB/token), the project's target (EXP-029, based on EXP-004
  scaling).

**Method — honest measurement discipline** (`weight_stream/bench/measure.py`):
1. **Clean room** — kill stale llama-server processes (Windows orphans
   squat on the backend port and silently change flags), restart the API
   server with the exact configuration under test.
2. **Verify, don't trust** — after load, inspect the *actual* spawned
   llama-server command line; the requested flags must be present with
   the right values (`-t`, `-fa`, `-ctk`, `-ctv`).
3. **Cold + warm** — generation #1 faults weights in from disk (the
   honest "first real workload"); generation #2 runs with the OS page
   cache populated (the honest "best case on this machine").
4. **Record paging** — faults/token and disk MB/token from
   `generation.paging` in `/v1/stats`, so speed cannot hide disk
   thrashing.
5. **Warm average** — headline throughput = mean of ≥ 3 warm runs of 100
   tokens (EXP-028), per-token latency captured from the SSE stream.

## 4.2 Physics validation: prediction matches real hardware

The calibrated physics model (`tok/s = BW ÷ bytes/token`, §3.2) predicts
what the real machine does:

| Case | Predicted | Measured | Error |
|---|---:|---:|---:|
| Qwen CPU-pure (EXP-004) | 22.73 tok/s | 22.73 tok/s | **0.0%** |
| Qwen via server, warm (EXP-025) | 22.73 | 20.76 | **−8.7%** |
| Qwen via server, warm (EXP-028) | 22.73 | 22.73 | **+0.02%** |
| DS-V4-Flash >RAM (EXP-012) | ~1.8 (0.2 GB @ 0.38 GB/s) | 1.5–1.9 | **in band** |

All measurements land within the ±15% tolerance (EXP-025 set the
tolerance from the real-HW validation; EXP-028 reproduced 22.73 tok/s
to +0.02%). The physics model is not a fitted curve over the test set —
it is a two-line identity calibrated on three tier constants, and it
predicts an unmeasured model (K3) rather than describing a measured one.

## 4.3 The real >RAM case: 104 GB on 64 GB RAM

| config | cold tok/s | warm tok/s | faults/tok | disk MB/tok |
|---|---:|---:|---:|---:|
| all-expert CPU, t8 | 1.48 | 1.76 | 68,009 | ~150–270 |
| 42-layer MoE tiering, t8 | 1.46 | **1.89** | 76,548 | ~160–300 |
| all-expert CPU, t16 | 1.71 | 1.75 | 64,935 | ~145–260 |
| auto placement (n-cpu-moe 0), t8 | 1.65 | 1.83 | 62,933 | ~150–250 |
| forced `-ngl 99` (everything to GPU) | **OOM** | — | — | — |

Findings (EXP-012):
- A **104 GB model runs on a 64 GB machine at 1.5–1.9 tok/s** — real,
  reproducible, and dominated by the disk, not the CPU or GPU.
- **Config tweaks move the number only ~15%.** Threads, offload, and
  tiering all hit the same wall: the disk→RAM→CPU pipeline.
- The telemetry is unambiguous: **36k–77k page faults/token =
  150–300 MB read from disk per token** — every token thrashes part of
  the working set back from disk.
- Dead ends closed with evidence: speculative decoding (MTP) *slower*
  (−11–18%, EXP-015); expert traffic *flat* across layers — no hot layer
  to tier (EXP-014/016); CPU-lane compute dead because RAM bandwidth is
  saturated (EXP-017); the lever that works is bytes/token (IQ1_M vs
  IQ2_M = 77 vs 56 tok/s, EXP-011).

## 4.4 The target case: K3 (>RAM) and the buffer lever

The project's target — K3-class models with 15.6 GB/token active sets —
does not fit RAM at all. Phase 4 metrics applied to the K3 simulator
(EXP-029) show what buffering is worth:

| metric | Qwen real (fits RAM) | K3 @ 256 MB buffer | K3 @ 4 GB buffer |
|---|---:|---:|---:|
| **tok/s** | **22.73** | **0.049** | **1.18** |
| hit rate | 1.000 | 0.512 | 0.999 |
| p50 (ms) | 41.1 | 21,300 | ~816 |
| p90 (ms) | 48.6 | 27,051 | ~816 |
| p99 (ms) | 84.4 | 31,258 | ~816 |

Buffer size sweep (EXP-029):

| buffer MB | hit rate | tok/s | stall ms/token |
|---|---:|---:|---:|
| 64 | 0.336 | 0.036 | 27,322 |
| 256 | 0.512 | 0.049 | 20,075 |
| 1024 | 0.779 | 0.103 | 9,108 |
| **4096** | **0.999** | **1.180** | **33** |

Three conclusions:

1. **The hit rate is the entire game on >RAM.** At 51% hit, half of
   every token's 15.6 GB streams at disk-mmap speed → 0.049 tok/s,
   ~465× slower than Qwen's compute-bound 22.73. At 99.9% hit the model
   reaches its compute ceiling (815 ms/token) → **1.18 tok/s = 24×
   faster**. The curve is steeply non-linear because the hit/miss
   bandwidth gap is ~50× (19.18 vs 0.38 GB/s).
2. **Buffer *size* beats predictor cleverness here.** LRU + priority
   already reaches 99.9% at 4 GB; predictor accuracy is secondary
   (EXP-002, ADR-003). The 24× lever is engineering budget, not ML.
3. **The latency distribution exposes the misses.** Qwen's warm
   distribution has no tail (p99 ≈ 2.0×p50); K3's p99 = 31 s vs
   p50 = 21 s — the tail is exactly the tokens that missed. Any latency
   SLA on a >RAM model must control per-token hit rate, not just the
   average.

## 4.5 Threats to validity

- **One consumer machine.** The physics model is calibrated on this
  machine; the tier constants (RAM/GPU/disk BW) transfer to other
  hardware only via re-calibration (the harness ships to do so).
- **K3 is simulated.** No K3-class checkpoint exists publicly at this
  size; the 15.6 GB/token spec follows EXP-004's K3 assumptions (50B
  active × 2.5 bpw). The simulator's access pattern is validated against
  real expert census data (EXP-014/016).
- **Warm-vs-cold honesty.** We report both; the headline warm numbers
  are the best case, cold numbers are the honest first-touch case —
  neither is hidden.

## 4.6 Summary

| Question | Answer |
|---|---|
| Does a >RAM model run on consumer HW? | Yes — 104 GB at 1.5–1.9 tok/s, disk-bound |
| Why is it slow? | Effective disk BW 0.38 GB/s (~37× below NVMe spec) |
| Does physics predict it? | Yes — within ±9% on real HW (EXP-025/028) |
| Is buffering worth it? | 24× on >RAM (0.049→1.18 tok/s); ~0× when the model fits |
| What is the lever? | Buffer hit rate ≥ 99% — size, not predictor cleverness |

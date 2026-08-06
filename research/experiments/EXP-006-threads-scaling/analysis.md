# EXP-006: CPU Thread Scaling — Analysis

## Findings

1. **8 threads is the optimum on i9-9900KF** for `--cpu-moe` — confirmed
   empirically (46.35–46.52 tok/s, p95 20.1–20.5 ms). 12 is a tie; 16 is a
   small regression (44.64 tok/s, p95 21.8 ms, max 31.1 ms).

2. **The workload is memory-bound, not compute-bound.** 8 vs 16 threads moved
   nothing because the bottleneck is DDR4-3200 dual-channel bandwidth
   (~45 GB/s) feeding expert weights — extra threads can't create bandwidth.
   This is exactly the prediction in EXP-005's analysis.

3. **Measurement methodology works.** SSE per-delta timing via
   `/v1/chat/completions` gives a stable per-token distribution; the
   prefill-excluded SSE tok/s and the wall-clock `/v1/stats` tok/s agree on
   ordering across configs. `scripts/measure_threads_scaling.py` is reusable
   for any future tuning sweep.

## Surprises

- 12 threads matching 8 exactly (not slightly better) is a clean confirmation
  of the physical-core ceiling — no hidden gain from 1 extra logical thread.
- The SSE tok/s (~50) consistently reads ~8% higher than server tok/s (~46):
  purely an artifact of excluding prefill, not a measurement bug.

## Conclusions & next steps

- ✅ **Keep default threads at 8.** No code change needed — the existing
  `_default_n_threads()` (cpu_count/2 = 8) is already optimal for this
  workload.
- The path to >46 tok/s on this model is NOT threads — it is reducing expert
  bytes read through RAM: KV cache `q8_0` (frees VRAM), `-ncmoe` (put some
  experts on GPU), or a larger expert hot-cache. Follow with EXP-007 (KV cache
  type) and EXP-008 (`-ncmoe` partial GPU experts).
- Reusable harness: `scripts/measure_threads_scaling.py` (WS_THREADS env to
  override the sweep).

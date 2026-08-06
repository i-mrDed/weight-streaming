# EXP-006: CPU Thread Scaling — Results

> **⚠️ INVALIDATED (2026-08-06, EXP-007):** these measurements ran while a
> stale Jan llama-server (Qwythos-9B dense) was squatting on **port 8805 —
> the same port our backend uses** — and requests went to it, not the 35B.
> 46 tok/s flat across threads is exactly what a dense GPU-resident 9B does
> (GPU-bound, threads irrelevant) — NOT a memory-bound MoE result. Verified
> clean 35B + `--cpu-moe` runs ~18.4 tok/s (EXP-007). Treat this whole
> experiment as void; thread tuning on the real model is still a valid
> follow-up.

## Raw data (200 tokens, warm) — CONTAMINATED (see header)

| threads | server tok/s | SSE tok/s | per-token avg ms | median ms | **p95 ms** | max ms |
|--------:|-------------:|----------:|-----------------:|----------:|-----------:|-------:|
| **8**   | **46.35**    | 50.93     | 19.5             | 19.5      | **20.5**   | 23.4   |
| **12**  | **46.41**    | 50.85     | 19.6             | 19.5      | **20.5**   | 24.0   |
| 16      | 44.64        | 49.50     | 20.1             | 20.0      | 21.8       | **31.1** |
| 8 (repeat) | 46.52     | 51.14     | 19.5             | 19.4      | 20.1       | 23.1   |

> SSE tok/s (~50) is higher than server tok/s (~46) because the first SSE gap
> (prefill) is excluded from the SSE calc while `/v1/stats` counts full wall
> time — the *server* number is the honest end-to-end figure.

## Verdict

- **8 and 12 are statistically identical** (46.35 vs 46.41 tok/s; p95 both 20.5 ms).
- **16 is slightly worse**: −3.8% throughput, p95 +1.3 ms, max +8 ms — classic
  hyperthreading contention on a memory-bound workload.
- Repeat-8 (46.52) matches first-8 (46.35): no drift, steady measurement.

## Interpretation

- The current default (8 threads = physical cores) is already the optimum —
  matching the llama.cpp guidance that memory-bound MoE matmul does not scale
  past physical cores.
- The gap between 46 tok/s (measured) and the ~70+ tok/s VRAM-bandwidth ceiling
  is NOT a threading problem — it is the DDR4 expert-stream bandwidth (the 8
  active experts still read through RAM). Threads tuning will not close it;
  expert hot-cache in VRAM would.

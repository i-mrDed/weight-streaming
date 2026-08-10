# EXP-011: Ultra-Low-Bit Quant (IQ1_M) — Results

## Headline

| config | IQ2_M (11.5 GB) | IQ1_M (10.05 GB) | Δ tok/s |
|--------|:---:|:---:|:---:|
| n-cpu-moe 10 | 47.2 | 44.6 (server) / 48.7 (raw) | ≈ 0 |
| **n-cpu-moe 0 (all experts GPU)** | **56.4** | **72.4 (server) / 77.6 (raw)** | **+28–37%** |

## Full numbers (IQ1_M)

| config | server tok/s | raw tok/s | VRAM after gen | p95 |
|--------|:---:|:---:|:---:|:---:|
| n-cpu-moe 10 | 44.6 | 48.7 | 8,869 MiB | 22.7 ms |
| n-cpu-moe 0 | **72.4** | **77.6** | 10,803 MiB | 13.9 ms |

(`server tok_s` = what the API server reports via /v1/stats after a
real generation; `raw tok_s` = llama-server's own decode figure.)

## What changed vs IQ2_M

- **VRAM footprint:** n-cpu-moe 0 uses 10,803 MiB (IQ2_M filled ~12,067).
  The 1.5 GB smaller file means attention + shared/experts-in-VRAM fit
  fully with headroom — the p95 drops 21.9 → **13.9 ms**.
- **Bandwidth math:** every expert read from RAM moves fewer bytes
  (1.75 bpw vs ~2.3 bpw) → less PCIe/DDR4 traffic per token.
- **n-cpu-moe 10 unchanged** (≈47) — expert-offload tiering is not where
  the win is; full-GPU experts + small quant is.

## Quality eval (2026-08-10, same 9-question Thai set, n-cpu-moe 0)

| metric | IQ1_M | IQ2_M |
|--------|:---:|:---:|
| tok/s | **79.1** | 50.3 |
| 8/9 dimensions (fact, math, logic, code, idiom, multi-step, price, science) | ✅ | ✅ |
| Thai tonal classification | ❌ wrong (systematic) | ✅ correct |

Raw answers: `scripts/.quant_quality_out.json` (IQ1_M, latest run) and
`scripts/.quant_quality_out.iq2m.json` (IQ2_M backup).

## Caveats

1. ~~**Quality:** IQ1_M is an ultra-low-bit quant — quality loss vs IQ2_M is
   REAL (this is the trade the tok/s buys). Not evaluated for task
   quality here; check before relying on it for real work.~~
   **DONE — see Quality eval above**: 8/9 equal; Thai tonal is the real,
   systematic regression (ข้าว/ข่าว/ไข่/ไก่ etc. all wrong tone class).
2. **VRAM headroom at n-cpu-moe 0 is thin** (1,485 MiB free). A larger
   n_ctx or concurrent second model will spill → expect a cliff, not a
   smooth decline.
3. p95 here is generation-only (no queue contention).

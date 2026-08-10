# EXP-016: Expert Popularity Census → Auto Tiering — Results

## Headline: NO hot layer — expert traffic is flat across layers

Layer-band sweep (Qwen3.6-35B-A3B UD-IQ2_M, n-cpu-moe-style `-ot` pinning,
3 × 200-300 token Thai idiom generations, median tps):

| config | experts on GPU | tps | VRAM (MiB) | tps/GB |
|--------|:---:|:---:|:---:|:---:|
| exp_cpu (none) | — | 17.2 | 2,840 | 6.20 |
| gpu_0_9  | layers 0–9 | 23.1 | 5,079 | 4.66 |
| gpu_10_19 | layers 10–19 | 23.5 | 5,141 | 4.67 |
| gpu_20_29 | layers 20–29 | 23.4 | 5,141 | 4.66 |
| gpu_30_39 | layers 30–39 | 23.2 | 5,236 | 4.54 |
| **exp_gpu (all)** | layers 0–39 | **69.6** | 11,864 | 6.01 |

Single-layer pins (checking for in-band hot spots):

| config | tps | VRAM (MiB) |
|--------|:---:|:---:|
| l0  | 18.0 | 3,067 |
| l13 | 17.6 | 3,066 |
| l26 | 17.4 | 3,064 |
| l39 | 17.7 | 3,102 |

## Interpretation

1. **Layer position does not matter.** All four 10-layer bands give the
   same tps (23.1–23.5, within noise). Single layers are flat too
   (17.4–18.0). There is no "hot" early/mid/late band worth pinning first.
2. **The only lever is bytes on GPU.** 2.8 GB → 5.1 GB (+2.3 GB of experts)
   buys +6 tps; 5.1 → 11.9 GB (another +6.7 GB) buys **+46 tps** — a
   strongly super-linear curve. Marginal expert bytes become MORE valuable
   the more you add, because once most experts are resident the CPU no
   longer computes them every token.
3. **Contradicts the skew hypothesis at LAYER granularity.** RFC #24528's
   Gini ≈ 0.76 is per-EXPERT; llama.cpp places at per-LAYER granularity
   (fused tensors), and at that granularity the traffic is uniform. The
   skew, if it exists, lives *inside* layers — invisible to `-ot` without
   defusing the GGUF + an instrumented build (`LLAMA_LOG_MOE`).
4. **Practical conclusion:** on this 12 GB card, "auto tiering" = **fill
   VRAM with as many expert bytes as possible** — which is exactly what
   `--n-cpu-moe 0` (auto placement) already does. No smarter static split
   exists at layer granularity. The census adds no win over the existing
   flag.

## What would change the verdict (future, needs tooling)

- **Per-expert census** via defused GGUF + instrumented llama.cpp
  (`LLAMA_LOG_MOE`). If a small hot expert set exists, a runtime expert
  cache (RFC #24528's `--moe-cache`, leloch's branch) could pin those —
  but that's a llama.cpp feature, not something our backend can express
  today, and batot1's GTX-1080Ti regression test suggests it may not help
  on a single older GPU anyway.

## Verdict

ROADMAP Phase 4 #1 (census → auto `n-cpu-moe` tiering) is **closed as "no
additional win at layer granularity"** — the existing `--n-cpu-moe 0` /
auto-fit already implements the optimal static placement the census can
express. Remaining levers: #2 CPU lane by residency (untested) and #3
IQ2_XXS on DS V4 Flash (bytes/token ↓ → resident ↑), which directly attacks
the super-linear bytes-on-GPU curve above.

## Raw data

- `scripts/.expert_census_out.json` (band sweep)
- `scripts/.expert_census_single.json` (single-layer)
- Harness: `scripts/measure_expert_census.py`
- `-ot` order finding: last override wins; band `=CUDA0` must precede the
  catch-all `=CPU` (verified 5,341 vs 2,898 MiB on the same band)

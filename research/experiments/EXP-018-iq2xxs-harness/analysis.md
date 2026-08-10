# EXP-018 Analysis — verdict

## The quant ladder on Qwen3.6-35B-A3B (this machine, honest numbers)

| quant | size | tok/s | Thai tonal | daily-driver? |
| :--- | ---: | ---: | :--- | :--- |
| IQ1_M | 9.36 GB | 74.7 | ❌ (0/6) | general chat only |
| **IQ2_XXS** | **10.02 GB** | **43–66** (band; sustained 63–66) | **❌ (1/6)** | general chat only |
| IQ2_M | 10.73 GB | 43–56 | ✅ | Thai-inclusive |

## Verdict: the last Phase-4 lever is closed — ❌ NOT the sweet spot for Thai

**Hypothesis rejected.** The 0.7 GB over IQ1_M does NOT restore Thai tonal
accuracy — IQ2_XXS fails the same discriminator (5/6 words wrong, 1/6
correct vs IQ1_M's 0/6). The quality cliff is between **IQ2_XXS and IQ2_M**
(10.02 → 10.73 GB), not between IQ1_M and IQ2_XXS.

What IQ2_XXS buys instead: **a real speed margin over IQ2_M at identical
non-Thai quality** (8/9 questions correct, same as both neighbors). The
sustained gate number is 63–66 vs IQ2_M's 43–56 — but note the cold/warm
band overlaps (43–62 cold vs IQ2_M's 43–56), so the margin is clearest in
sustained/warm use. For English/technical/chat workloads where Thai tonal
doesn't matter, IQ2_XXS is the better daily driver than IQ2_M.

## What this closes

- **Phase 4 is now complete** — every lever on the roadmap has been
  measured and closed: spec-decode (EXP-010/015), census/tiering
  (EXP-016), CPU lane (EXP-017), and now the last one, IQ2_XXS (EXP-018).
- The bandwidth-wall physics is consistent across all of them: on this
  fixed hardware, **tok/s tracks bytes/token super-linearly** (EXP-016)
  and no software placement recovers what the 12 GB VRAM + DDR4
  bandwidth budget cannot hold (EXP-017).
- The honest ceiling for Thai-safe Qwen3.6-35B-A3B on this machine is
  **IQ2_M at 43–56 tok/s**; the honest ceiling for non-Thai use is
  **IQ2_XXS at ~63–66 tok/s sustained** (or IQ1_M at 74.7 for
  speed-first).

## Harness learnings (first real run of weight_stream/bench)

1. The packaged harness worked end-to-end on a real model on the first
   clean run (restart → verify cmdline → cold/warm → Thai gate → reports).
2. Two gaps found and fixed while using it for real:
   - **JSON export dropped the quality gate** — the whole point of the
     harness is diffable records; now the full JSON includes gate +
     complete answers.
   - **thai_tonal needs >2048 tokens** — the model writes a long EN think
     block; at 2048 the answer is truncated mid-think. Added
     `--quality-max-tokens`.
3. **Windows console encoding** — the ✅ emoji crashed a cp1252 console
   process; ASCII-safe output in the CLI + resume script.
4. **Download resume** — the IQ2_XXS download stalled at 97.6% when its
   process died (no .part, no hub tracking); added reusable
   `scripts/resume_download.py` (Range-append + byte-exact verify — the
   EXP-011b lesson applied to plain downloads).

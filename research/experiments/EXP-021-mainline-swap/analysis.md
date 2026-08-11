# EXP-021 Analysis — verdict

## Question: is a newer engine worth it on THIS machine? → NO (this round)

mainline b10357 (the newest official prebuilt, CUDA 12.4) matches Jan
b9967 on the same model/config within run-to-run variance (cold 62 vs
43–62, warm 57 vs 52–61). The engine version is not the bottleneck.

## What this means for ik_llama.cpp (`research/IK_LLAMA_EVAL.md`)

The fork's pitch is +45% on Qwen3.6 via MoE-specific optimisations that
are NOT in mainline — so this test does NOT rule out a fork gain. But it
does bound it: upstream mainline (which has absorbed many of ik's ideas)
gives nothing here, and the community's headline 110 tok/s was measured
on a 4070 Super, not a 3060. A realistic ceiling on this 3060 is ~80 tok/s
(per the 3060-12GB MTP thread), i.e. at most +30% over today's 61–66 —
and that requires building ik from source (no Windows binary, no toolchain
installed, disk ~10 GB short). **Decision: defer the ik build.** Revisit
if/when: (a) ik publishes Windows binaries, or (b) a toolchain + disk
become available and +30% matters more than the cost.

## What would actually move tok/s on this rig (next levers)

- CPU lane: EXP-020 already showed `-t 12` gains on Gemma (+13%) — the
  same thread tune may help Qwen IQ2_XXS (not yet swept on Qwen).
- The 3060's 12 GB VRAM is the hard ceiling; a config that spills LESS
  (smaller quant, KV q8 at real ctx) or uses MTP where the model has a
  head (Qwen3.6 has an MTP head — EXP-010/015 found it hurt on the CPU
  lane, but worth one more shot at t12 with the GPU path).

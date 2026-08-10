# EXP-016: Expert Popularity Census → Auto Tiering — Setup

## Goal

ROADMAP Phase 4 candidate #1: build an expert popularity census (which
experts fire most during real generation) and use it to drive automatic
`--n-cpu-moe`-style tiering — keep the HOT experts resident on the 12 GB
GPU instead of a static layer split.

Hypothesis (from EXP-014 / llama.cpp RFC #24528): expert traffic is highly
skewed (Gini ≈ 0.76 on Qwen3.5-122B; top 10% of experts ≈ 80% of hits), so
a census should reveal a small hot set worth pinning to VRAM.

## What the binary actually exposes

Investigated before designing the experiment (honest boundary):

1. **No per-token expert routing in logs.** `-lv 5/8/10` dumps load-time
   metadata only — no per-token expert selection. The moe-viz tool that
   shows per-token routing requires patching + rebuilding llama.cpp.
2. **`LLAMA_LOG_MOE=1` (used by tightwad's profile-guided mode) is NOT in
   this Jan b9967 build** — 0 log lines emitted. Needs the instrumented
   build from tightwad's `scripts/patches/`.
3. **Placement granularity = LAYER, not expert.** Expert tensors are fused
   per layer (`blk.N.ffn_gate_exps.weight` packs all 256 experts), so
   `--override-tensor (-ot)` can pin a whole layer's experts, not
   individual experts. Per-expert placement requires defusing the GGUF
   (tightwad `moe defuse`).

So the actionable census question becomes: **is any LAYER BAND hotter than
others?** If yes → pin those layers first. If flat → auto tiering reduces
to "fill VRAM with expert bytes", which `--n-cpu-moe 0` already does.

## Method (EXP-008/011/012/015 skeleton)

- Model: Qwen3.6-35B-A3B UD-IQ2_M (11.52 GB, the one we have)
- Configs via `-ot` overrides (order matters — last match wins; verified
  `CUDA0` band must come before the catch-all `CPU` rule):
  - `exp_cpu`: all conditional experts CPU (2.8 GB VRAM — attention +
    shared expert stay GPU)
  - `gpu_0_9 / 10_19 / 20_29 / 30_39`: one 10-layer band on GPU, rest CPU
  - `l0 / l13 / l26 / l39`: single layers, to check for in-band hot spots
  - `exp_gpu`: all experts GPU (upper bound)
- Each: restart API server with WS_LLAMA_EXTRA_ARGS → load → warmup +
  3 × generation (Thai idiom) → median tps + nvidia-smi VRAM
- Harness: `scripts/measure_expert_census.py`

## Environment

- i9-9900KF, RTX 3060 12 GB, 64 GB RAM (fixed)
- llama-server b9967 (Jan CUDA build, bb7049f7)
- API server 0.14.0

# EXP-017: CPU Lane (host-cache expert compute) — Setup

## Goal

ROADMAP Phase 4 candidate #2: pulsar (EXP-014 research) computes
cache-hot experts on the CPU instead of uploading them to the GPU every
token ("CPU lane"). Test whether the same idea helps on this machine:
keep experts in host RAM and let the CPU compute them, while the GPU
handles attention + shared expert.

EXP-016 showed layer placement is flat (no hot layer), so the remaining
question is purely: **is CPU expert compute a viable lane at all on this
hardware, or is the CPU already bandwidth-bound?**

## Method

Two configurations on Qwen3.6-35B-A3B UD-IQ2_M (11.52 GB), same 300-token
Thai idiom prompt, 3 reps:

1. `exp_cpu` — all conditional experts forced to CPU
   (`-ot "blk\.([0-9]+)\.ffn_.*_exps.*=CPU"`, `-ngl 99` keeps attention
   + shared expert on GPU)
2. `exp_gpu` — default auto-fit (experts on GPU, 10.9 GB VRAM)

Measure per rep: tok/s + concurrent CPU% (Get-Counter) + GPU util/VRAM
(nvidia-smi) sampled DURING generation (not after — first attempt sampled
post-gen and read idle numbers).

Harness: `scripts/.measure_util.py` (sampling thread runs while generation
streams).

## Environment

- i9-9900KF (8c/16t, DDR4), RTX 3060 12 GB, 64 GB RAM
- llama-server b9967 (Jan CUDA build, bb7049f7), API server 0.14.0

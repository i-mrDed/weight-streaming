# EXP-017: CPU Lane (host-cache expert compute) — Results

## Headline: CPU lane is a dead end on this hardware — the CPU is already bandwidth-bound

| config | tps | CPU% (during gen) | GPU util (during gen) | VRAM |
|--------|:---:|:---:|:---:|:---:|
| exp_cpu (experts CPU) | 13.0–16.4 | **39–51%** | 32–71% | 2.8 GB |
| exp_gpu (experts GPU) | **56.8–58.6** | 27–35% | 61–73% | 10.9 GB |

Raw reps (exp_cpu): 16.4 / 14.8 / 13.0 · (exp_gpu): 56.8 / 58.6 / 56.9.

## Interpretation

1. **The CPU is NOT compute-bound — it's bandwidth-bound.** With all
   experts on CPU, total CPU utilization sits at only 39–51% while
   generating at 13–16 tps. The i9-9900KF has 8 cores / 16 threads and
   only ~1/3–1/2 are busy — the wall is DDR4 memory bandwidth (the expert
   weights stream from RAM at ~20 GB/s, exactly the EXP-011 bandwidth
   math: bytes-per-token × tok/s ≈ available bandwidth).
2. **Adding a "CPU lane" cannot help.** pulsar's CPU lane works because
   their host has fast multi-channel RAM + many cores that are otherwise
   idle. Here the cores are ALREADY under-used — the bottleneck is
   bandwidth, so moving MORE work to the CPU (the lane idea) makes it
   worse, not better. The GPU at least overlaps attention compute with
   expert streaming and has its own high-bandwidth VRAM.
3. **Consistent with EXP-016's super-linear curve.** The 17 → 23 → 70 tps
   ramp (2.8 → 5.1 → 11.9 GB experts on GPU) is exactly what a
   bandwidth-bound CPU looks like: every expert byte moved off the CPU
   frees RAM bandwidth for the rest, and at 11.9 GB the CPU is no longer
   in the critical path.
4. **Same physics as EXP-012 (DS V4 Flash).** There the bottleneck was
   disk→RAM; here it's RAM→CPU. Both are memory-bandwidth walls — no
   amount of CPU/GPU placement software fixes a bandwidth wall on a fixed
   machine.

## Verdict

ROADMAP Phase 4 #2 (CPU lane) is **closed as a dead end on this machine**:
the i9-9900KF + DDR4 cannot be a productive expert-compute lane because
its cores are idle while its memory bus is saturated. The lever that
remains from Phase 4 is **#3 IQ2_XXS on DS V4 Flash** — reducing
bytes-per-token attacks the bandwidth wall directly (fewer bytes read per
token = more tokens per second), the same mechanism that made IQ1_M win
over IQ2_M in EXP-011.

This also sharpens the honest hardware conclusion: on i9-9900KF + 12 GB +
64 GB, the ONLY software lever left is bytes-per-token (quantization).
RAM (128 GB, keeps DS V4 Flash resident → fault only first pass) or a
bigger GPU (3090/5090) remain the hardware answers from
HARDWARE_100TPS_PLAN.

## Raw data

- `scripts/.measure_util.py` — sampling harness (CPU% during gen via
  Get-Counter, GPU via nvidia-smi)
- exp_cpu server log: `scripts/.ws-server-cpulane.log` (first run —
  `-ot ...=CPU` cmdline verified via wmic)
- exp_gpu run: same server restarted without extra args (cmdline verified)

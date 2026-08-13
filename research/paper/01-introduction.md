# 1. Introduction

> **Status:** draft (Phase 5, TASKS.md) · 2026-08-13 · ตาม `research/paper/OUTLINE.md`
> ตัวเลขทุกตัวมาจากการวัดจริงใน repo (`research/experiments/EXP-001..029`)
> — อ้างอิง EXP-NNN กำกับไว้ ทุกบรรทัด

---

Mixture-of-Experts (MoE) language models keep growing past the hardware
most people can afford. Kimi K3 — the model class this project targets —
is estimated at ~2.8T parameters with ~50B active per token, and the
largest open MoE checkpoints ship as 100 GB+ files. Meanwhile, the
mainstream consumer machine still has 8–64 GB of RAM and 8–24 GB of VRAM.
The gap is not shrinking: quantized 2–3-bit weights of a flagship MoE
*fill* a consumer machine's RAM several times over.

The community's default is to benchmark the models you *can* run, and to
either claim the ones you cannot fit are "fine" or to stay silent about
them. Neither is honest, and both leave a critical question unanswered:
**what does it actually cost, in measurable terms, to run a model larger
than your hardware?** This paper answers that question with real
measurements, real telemetry, and a physics model that predicts the cost
before you spend on hardware.

**We measure the honest number.** Running a 104 GB DeepSeek-V4-Flash on a
64 GB RAM + 12 GB VRAM consumer machine (i9-9900KF, RTX 3060) yields
**1.5–1.9 tok/s** — usable for batch jobs, not interactive — and the
OS-level telemetry proves *why*: **36,000–77,000 page faults per token,
i.e. 150–300 MB read from disk for every token generated** (EXP-012,
full write-up in `research/writeups/`). More threads or more VRAM
tiering move this by only ~15%; the wall is the disk, and the disk is
measurable, not vibes.

**We calibrate the physics.** Every one of those numbers reduces to a
single identity: `tok/s = effective bandwidth ÷ bytes per token`, where
bytes/token = active params × bits/weight ÷ 8. Calibrating the
bandwidth from real measurements gives three tiers: **cpu-ram
19.18 GB/s, gpu-vram 61.09 GB/s, disk-mmap 0.38 GB/s** (EXP-025). The
disk-mmap tier is the number nobody quotes: page-fault reads are random
access, so the honest effective bandwidth of an NVMe is **~0.38 GB/s,
37× below its 14 GB/s sequential spec**. With this model we predict a
fits-RAM Qwen1.5-MoE-A2.7B at 22.73 tok/s and measure **22.73 tok/s
(+0.02%)** on the real machine (EXP-028) — a validation that is not a
lucky fit but a calibrated identity.

**We show when buffering is worth it — and when it is not.** On a model
that fits RAM (Qwen, 5.9 GB), throughput is compute-bound: hit rate is
1.000, latency has no tail (p99 ≈ 2.0×p50), and no buffer or prefetch
helps (EXP-027, ADR-003). On the target K3 (15.6 GB/token, *does not*
fit RAM), the same metrics tell the opposite story: at the simulator's
default 256 MB buffer, hit rate drops to 51% and throughput collapses to
**0.049 tok/s**; a 4 GB buffer raises hit rate to 99.9% and recovers
**1.18 tok/s** — the compute ceiling (815 ms/token, EXP-004/025). That
is a **24×** swing from one number: the buffer hit rate (EXP-029). Prefetching and buffering are not
marginal tweaks on >RAM models; they are the difference between unusable
and usable.

Our contributions:

1. **The honest >RAM benchmark.** First-hand, reproducible measurement of
   a 104 GB MoE on consumer hardware with OS-level telemetry
   (page faults/token, disk MB/token) — the number the community
   doesn't publish (EXP-012, write-up).
2. **A calibrated physics model.** `tok/s = BW ÷ bytes/token` with three
   empirically calibrated bandwidth tiers, validated to within ±9% on
   real hardware (EXP-025/028) and used to *predict* K3's behavior
   rather than guess it (EXP-029).
3. **A buffer abstraction bridging simulation and production.** A single
   `BufferBackend` protocol that maps both the simulator's LRU/LFU/priority
   buffer and the production OS signals (`generation.paging`) to one
   buffer-equivalent view — closing the gap where the tracker observed
   nothing during real inference (EXP-026, ADR-003).
4. **Evaluation metrics with real numbers.** Hit rate, latency
   distribution (p50/p90/p99), and throughput-vs-physics definitions,
   computed from real telemetry on Qwen and applied to the K3 target
   (EXP-028/029).

The rest of this paper is organized as follows. Section 2 reviews related
work on MoE serving, weight prefetching (including LayerScope's
prediction-driven scheduling on the PCIe tier, and EAGLE-3's token-level
speculation — both of which we differentiate from the disk-bound tier),
and honest benchmarking. Section 3 describes the system architecture:
the llama.cpp engine, the physics model, the telemetry, the buffer
abstraction, and the evaluation metrics. Section 4 presents the
evaluation: physics validation, the real >RAM measurements, and the K3
prediction. Section 5 concludes.

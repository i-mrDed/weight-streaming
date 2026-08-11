# EXP-022 Analysis — verdict

## Hypothesis: 12B QAT+MTP is faster AND Thai-safe → CONFIRMED

**Gemma 4 12B QAT+MTP = 75.7 tok/s sustained, Thai gate 9/9 with the
tonal discriminator correct 6/6** (ข้าว/เข้า = โท, ข่าว/ไข่/ไก่ = เอก,
ไหม = จัตวา — with per-word example sentences and a summary table in the
reasoning). The whole model (6.72 GB + 0.47 GB draft) fits in 12 GB VRAM:
faults/tok ~450 vs ~1200 for the 26B — no CPU spill, GPU-bound, and
threads stop mattering (t8 ≈ t12, unlike the 26B's t12 optimum, EXP-020).

## Leaderboard update (this machine — real engine, clean room)

| model | tok/s (warm) | Thai tonal | VRAM fit |
|---|---|---|---|
| **Gemma 4 12B QAT+MTP** | **76** | ✅ 6/6 | full (no spill) |
| Qwen3.6 IQ1_M | 74.7 | ❌ 0/6 | full |
| Qwen3.6 IQ2_XXS | 61–66 | ❌ 1/6 | full |
| Gemma 4 26B QAT+MTP (t12) | 49–51 | ✅ 6/6 | spills ~2.25 GB |
| Qwen3.6 IQ2_M | 43–56 | ✅ | full |

**The 12B is the fastest Thai-safe model measured on this rig** — it beats
the 26B by +52% while keeping perfect Thai tonal, and beats the Qwen speed
kings (IQ1_M/IQ2_XXS) while THOSE fail the tonal gate. Speed + Thai now
finally coexist on 12 GB.

## Honest trade-off vs the 26B

- The 26B is the **stronger model** (larger, deeper reasoning; community
  benchmarks rank it well above the 12B on general tasks). The Thai gate is
  9 fixed questions — both pass; it does NOT distinguish subtle general
  quality.
- **Recommendation:** 12B = daily driver when speed matters (chat, agents,
  long sessions) at 76 tok/s. 26B = quality-first mode (complex reasoning,
  long-form) at ~50 tok/s. Both proven Thai-safe; pick per task.
- Note: the 12B's thai_tonal answer stayed inside its thinking block at
  the 4096-token budget (final truncated) — the tonal verdict was read
  from the recorded reasoning, same handling as EXP-020. The gate harness
  keeps the full think for exactly this reason.

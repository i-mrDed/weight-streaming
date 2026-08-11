# EXP-020 Analysis — verdict

## Hypothesis: the daily-driver config (t8) is not tuned → CONFIRMED

Threads were the untapped lever. **t12 is the new recommended config for
Gemma 4 QAT+MTP on this machine: warm 49.0 tok/s vs 43.5 at t8 (+12.7%)** —
the same model, same quality, for one flag change. Combined with EXP-019's
MTP (+20% over baseline), the full recipe from the t8-no-MTP starting point
(37.6) is now **t12+MTP = 49.0 (+30%)** — all software, no hardware change.

## Why t12 and not t16

- i9-9900KF = 8 cores / 16 threads. Gemma 4 26B spills ~2.25 GB past the
  12 GB VRAM → the spill compute runs on CPU. t12 uses 12 of 16 threads
  (6 of 8 cores + hyperthreading headroom), t16 oversubscribes and loses 8%
  on warm. Matches EXP-006's finding that thread count saturates around the
  physical-core count plus a margin on this CPU.

## What did NOT help (honest negative results)

- **flash-attn off** ≈ on (43.99 vs 43.45): fa only pays off at long
  context — our 2048-ctx bench can't see it. Not a regression, just no
  free lunch here. (Keep `-fa on` for real long-context use.)
- **KV q8_0** ≈ f16 (44.67 vs 43.45): at 2048 ctx the KV is ~MBs — the
  VRAM savings are invisible; q8 may even cost a hair of compute. Would
  only matter at 32k+ context where KV pressure is real.

## Recommended daily-driver config (updated)

```
--fa on -t 12 -ctk f16 -ctv f16 \
--spec-draft-model <MTP draft> --spec-type draft-mtp --spec-draft-n-max 2
```

→ **~49 tok/s warm sustained** (vs 45 recorded in EXP-019 at t8).

## Caveats

- Single clean sweep; run-to-run page-cache variance is ±1–2 tok/s
  (EXP-018 lesson) — the +12.7% t12-vs-t8 delta is consistent within this
  sweep (both cold AND warm favour t12 by a wider margin).
- Threads don't change model output at temperature 0 in principle, but
  FP reduction order can differ → the Thai gate is re-run at t12
  (see gate results in this folder) before the config is declared safe.

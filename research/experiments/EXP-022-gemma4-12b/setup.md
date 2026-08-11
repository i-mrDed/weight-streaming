# EXP-022: Gemma 4 12B QAT+MTP — the smaller challenger

## Date
2026-08-11

## Why
`research/MODELS_12GB_SHORTLIST.md` flagged Gemma 4 **12B** QAT as the
dense alternative: community ~120 tok/s, and — unlike the 26B — the whole
model should fit comfortably in 12 GB VRAM (no CPU spill). EXP-019 proved
the 26B QAT is the Thai-safe daily driver (45–51 tok/s with MTP+t12).
Question: does the smaller 12B hit a meaningfully higher tok/s while
keeping the 9/9 Thai gate + 6/6 tonal?

## Files / model
- `unsloth/gemma-4-12B-it-qat-GGUF`
  - main: `gemma-4-12B-it-qat-UD-Q4_K_XL.gguf` — 6,716,356,800 B (6.72 GB)
  - draft: `MTP/mtp-gemma-4-12B-it-Q8_0.gguf` — 465,127,936 B (0.47 GB)
- Downloaded byte-exact via `scripts/resume_download.py` (Range-append +
  exact-size gate — the same integrity rule as EXP-011b).

## Method
Harness `python -m weight_stream bench` — clean room per config, cmdline
verified. Matrix (all with MTP draft, matching the 26B recipe + EXP-020
thread finding):
| name | threads | notes |
|---|---|---|
| t8  | 8  | EXP-019-style baseline |
| t12 | 12 | EXP-020 optimum for the 26B |
Then the Thai quality gate (9 questions, temp 0, max_tokens 4096) at the
best config.

## Question
12B QAT+MTP vs 26B QAT+MTP: faster AND Thai-safe, or does the 26B stay
the daily driver?

## Files
- `bench.json` / `bench.md` — harness matrix export
- `gate.json` — Thai quality gate full answers
- `results.md` / `analysis.md`

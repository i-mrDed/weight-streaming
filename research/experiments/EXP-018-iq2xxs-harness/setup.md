# EXP-018: IQ2_XXS — the last Phase-4 lever, measured by the new harness

## Date
2026-08-10

## Hypothesis
EXP-011 found the quant ladder's two ends on Qwen3.6-35B-A3B:
- **IQ1_M** (9.36 GB) → 74.7 tok/s but **Thai tonal FAILS** (deterministic 0/6)
- **IQ2_M** (10.73 GB) → 43–56 tok/s, Thai tonal passes

**IQ2_XXS (10.02 GB) sits between the two** — 0.7 GB heavier than IQ1_M,
0.7 GB lighter than IQ2_M. Question: does it give "both fast AND good"?
i.e. does the extra 0.7 GB over IQ1_M restore the Thai tonal accuracy that
IQ2_M has? If yes, it replaces IQ2_M as the daily driver (faster at the
same quality).

## Method (first real run of the packaged harness)
`python -m weight_stream bench <IQ2_XXS.gguf> --model-id iq2xxs --gen-tokens 120 --thai`

- **Clean room:** killed stale llama-servers, restarted the API server on
  :8765 with a fresh backend (WS_LLAMA_EXTRA_ARGS unset → default config).
- **Verify:** spawned llama-server cmdline checked (presence + value-aware
  checks for -t/-fa/-ctk/-ctv).
- **Cold + warm:** gen #1 (disk-bound first workload) and gen #2
  (page-cache resident) at 120 tokens each.
- **Thai gate:** the 9 fixed questions (EXP-009/011 set), temperature 0,
  reasoning off. `thai_tonal` re-asked separately at max_tokens=4096
  because the 2048-token budget truncates the model's long EN think block
  before the closing tag.

## Files
- `results.md` — numbers + quality answers
- `analysis.md` — verdict
- `bench-iq2xxs.json / .md / .quality.md` — raw harness export
- Model: `D:/models/Qwen3.6-35B-A3B-GGUF/Qwen3.6-35B-A3B-UD-IQ2_XXS.gguf`
  (10,756,586,464 bytes, verified byte-exact against HF after a stalled
  download was resumed with `scripts/resume_download.py`)

# EXP-021: engine swap — mainline llama.cpp b10357 vs Jan b9967 (proxy for ik)

## Date
2026-08-11

## Why
`research/IK_LLAMA_EVAL.md`: the ik_llama.cpp fork (claim: +45% on Qwen3.6)
has no Windows binary and this machine lacks a build toolchain, so building
it is deferred. BEFORE deciding whether the toolchain investment is worth
it, test the cheap proxy: **official mainline llama.cpp prebuilt
(b10357, newer than our Jan b9967)**. If a newer mainline engine moves the
needle on the same model/config, the fork (which layers its MoE
optimisations on top) becomes a worthwhile build; if not, the 3060 is the
bottleneck and ik would not help either.

## Files / method
- Model: `D:\models\Qwen3.6-35B-A3B-GGUF\Qwen3.6-35B-A3B-UD-IQ2_XXS.gguf`
  (10.0 GB — the same file EXP-018 measured at **cold 43–62 / warm 52–61 /
  gate 63–66 tok/s** with Jan b9967, default config, no extra args).
- Engine: `tools/llama-b10357/llama-server.exe` (official
  `llama-b10357-bin-win-cuda-12.4-x64.zip`, extracted) via
  `WS_LLAMA_SERVER` — the backend's supported override (llama_server.py).
- Harness: `python -m weight_stream bench <model> --model-id iq2xxs-b10357
  --gen-tokens 120` — SAME default config as EXP-018 for a fair comparison.
  Clean room per run (fresh API server, cmdline verified).

## Question
Does mainline b10357 beat Jan b9967 on IQ2_XXS with identical flags?

## Files
- `bench.json` / `bench.md` — harness export
- `results.md` / `analysis.md`

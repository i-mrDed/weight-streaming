# EXP-019: Gemma 4 26B-A4B QAT + MTP — the challenger, measured

## Date
2026-08-10

## Why
`research/MODELS_12GB_SHORTLIST.md` flagged **Gemma 4 26B-A4B QAT+MTP** as
the strongest competitor to our resident Qwen3.6-35B-A3B: community
benchmarks (2026-07) show ~100 tok/s on a 12 GB RTX 4070, and **QAT
(quantization-aware training) keeps Q4 quality ≈ Q8** — the property that
post-training IQ quants destroy (EXP-011/018: every Qwen3.6 quant below
IQ2_M fails Thai tonal).

Question: on THIS machine (3060 12 GB, i9-9900KF, DDR4), does Gemma 4
beat Qwen3.6 — in speed AND in the Thai quality gate, including the tonal
discriminator that is the project's quality floor?

## Files / model
- `unsloth/gemma-4-26B-A4B-it-qat-GGUF`
  - main: `gemma-4-26B-A4B-it-qat-UD-Q4_K_XL.gguf` — 14,249,047,104 B
    (14.25 GB — bigger than 12 GB VRAM → partial CPU spill expected)
  - draft: `MTP/mtp-gemma-4-26B-A4B-it-Q8_0.gguf` — 461,785,600 B
- Both downloaded byte-exact via `scripts/resume_download.py`
  (GGUF v3 magic verified)

## Method
`python -m weight_stream bench <gemma> --model-id gemma4 --gen-tokens 120
--matrix '{"baseline t8": "-fa on -t 8", "mtp t8": "-fa on -t 8
--spec-draft-model <draft> --spec-type draft-mtp --spec-draft-n-max 2"}'`

- Harness clean room per config (fresh API server, cmdline verified).
- Then the Thai quality gate (9 fixed questions, temperature 0,
  max_tokens 4096) against the server with MTP active.
- Same llama-server build as every prior measurement (Jan b9967).
- Note: Gemma 4 emits thinking as `<|channel>thought …<channel|>` blocks
  (not `<think>`); `split_think` was extended for it (test added).

## Files
- `bench-gemma4.json/.md` — harness matrix export (baseline + MTP)
- `gemma4-gate.json` — Thai quality gate full answers
- `results.md` / `analysis.md`

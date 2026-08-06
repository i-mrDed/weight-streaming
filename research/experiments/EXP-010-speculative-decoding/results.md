# EXP-010: Speculative Decoding — Results

Measured 2026-08-06. All runs through the clean-room gate with token-exact
flag verification.

## Attempt 1 — `-md Qwen3-0.6B-Q8_0.gguf` WITHOUT `--spec-type` (invalid)

| config | server tok/s | VRAM | p95 |
|--------|:---:|:---:|:---:|
| n-cpu-moe 10 baseline | 44.3 | 10,542 MiB | 22.6 ms |
| n-cpu-moe 10 + `-md` (no spec-type) | 39.5 | 10,407 MiB | 31.9 ms |

**Invalid measurement** — this build's `--spec-type` defaults to `none`, so
the draft model was parsed but never used (draft config = plain inference
+ noise). Direct run confirmed: no draft load lines in the server log.

## Attempt 2 — correct flags, vocab check (direct llama-server run)

```
E spec common_specu: the target and draft vocabs are not compatible
E srv load_model: failed to initialize speculative decoding context:
  draft model vocab type must match target model to use speculation
```

**Root cause confirmed:** Qwen3-0.6B uses the Qwen3 tokenizer (~151,936
tokens); the target's GGUF exposes control token `</s>` at index 128,247 →
Qwen3.6 tokenizer (~128k tokens). Vocabs are incompatible → the draft is
rejected outright. Server still started (falls back to no speculation).

## Attempt 3 — `--spec-type ngram-simple` (no draft model)

| config | server tok/s | VRAM | p95 |
|--------|:---:|:---:|:---:|
| n-cpu-moe 10 baseline (cold page cache) | 35.8 | 10,448 MiB | 56.9 ms |
| n-cpu-moe 10 + ngram-simple | 45.5 | 10,455 MiB | 21.7 ms |

The baseline run here is anomalous (cold page cache — p95 56.9 ms is the
disk-streaming signature; the established n-cpu-moe 10 baseline is
44.3-46.9). Comparing ngram 45.5 against the ESTABLISHED baseline range:
**no gain** (≈ baseline within noise).

## Summary

| attempt | result |
|---------|--------|
| Qwen3-0.6B draft | ✗ vocab incompatible (151k vs 128k) |
| Small Qwen3.6 draft | ✗ does not exist on HF (searched) |
| ngram-simple | ≈ baseline (no gain) |
| MTP draft (35B) | impractical on 12 GB VRAM (doubles streaming) |

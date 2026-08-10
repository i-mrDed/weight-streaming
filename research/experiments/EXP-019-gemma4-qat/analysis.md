# EXP-019 Analysis — verdict

## The 12 GB leaderboard (all measured on THIS machine, real engine)

| model | size | tok/s | Thai gate | Thai tonal |
| :--- | ---: | ---: | :--- | :--- |
| Qwen3.6-35B-A3B IQ1_M | 9.36 GB | 74.7 | 8/9 | ❌ 0/6 |
| Qwen3.6-35B-A3B IQ2_XXS | 10.02 GB | 61–66 | 8/9 | ❌ 1/6 |
| Qwen3.6-35B-A3B IQ2_M | 10.73 GB | 43–56 | 9/9 | ✅ |
| **Gemma 4 26B-A4B QAT+MTP** | **14.25 GB** | **45–47** | **9/9** | **✅ 6/6 perfect** |

## Verdict: Gemma 4 QAT+MTP is the new Thai-safe daily driver

- **Quality:** perfect 9/9 gate including a flawless tonal answer (6/6
  with examples + summary table) — the first model on this machine to do
  so at a usable speed. QAT quantization sidesteps the IQ-quant quality
  cliff entirely (EXP-011/018): what needed 10.73 GB (IQ2_M) for Thai
  safety in the Qwen3.6 family, Gemma 4 achieves at Q4_K_XL.
- **Speed:** 45–47 tok/s with MTP ≈ Qwen3.6 IQ2_M's 43–56 — the same
  band, but from a newer, stronger model family (26B-A4B, 128–256K ctx,
  and it's the model community benchmarks at ~100 tok/s on a 4070).
- **Trade-offs vs Qwen3.6:**
  - Qwen IQ2_XXS stays the non-Thai speed king (61–66 tok/s).
  - Qwen IQ1_M stays the speed-first option (74.7) for non-Thai use.
  - Gemma 4 QAT wins when quality matters, especially Thai.
  - Gemma's 14.25 GB file spills past VRAM slightly (1–2k faults/tok);
    on a 16+ GB card the gap would grow further in its favor.

## MTP finding (vs EXP-015)

Gemma 4's separate MTP draft is a **real +20%** (37.6 → 45.1 warm).
Contrast DS V4's embedded MTP (EXP-015: −11–18%): a cheap separate draft
that shares the main model's vocabulary/template wins; a heavy integrated
MTP head that re-runs expert forward passes loses. For speculative
decoding, **draft size × acceptance matters more than head placement**.

## Harness notes
- `split_think` extended for Gemma 4's `<|channel>thought …<channel|>`
  format (test added).
- The gate ran with MTP active (server inherited the mtp extra args) —
  tok/s 46.7 is the sustained MTP number; quality is model quality
  (decode method does not change content).

# EXP-010: Speculative Decoding — Analysis

## Verdict

**Speculative decoding is NOT a viable lever on this machine/model combo
in its current form.** No available draft model is vocab-compatible with
the Qwen3.6 tokenizer, and the draft-free ngram path shows no gain.

## What we learned (valuable)

1. **This llama-server build (Jan b9967) uses the NEW speculative API** —
   `--spec-type` (default `none`) must be set explicitly; `-md` alone is
   silently ignored. Anyone testing spec decode on this binary must pass
   `--spec-type draft-simple` etc. Documented for future EXP runs.
2. **Qwen3.6 has its own tokenizer (~128k tokens)** — distinct from Qwen3's
   151,936. Cross-family drafts (even same-brand Qwen3) are rejected.
   Verified via llama-server's own error, not guessed.
3. **The draft search is complete:** no small Qwen3.6 GGUF exists on HF;
   the only same-family draft is the 35B MTP variant (impractical here).
4. **ngram-simple** uses the target's own vocab (works by construction) but
   on this generation task its acceptance is too low to overcome the
   per-token expert-streaming bottleneck — tok/s ≈ baseline.

## Why spec decode underperforms on this bottleneck

The decode cost here is dominated by reading expert weights from RAM per
token. A draft helps only when verified tokens skip the full-model forward;
when the full model is bandwidth-bound per forward AND the batch is small
(draft lengths 3-16), the win evaporates. A bigger batch (longer draft,
higher acceptance) or a vocab-matched draft could change this — neither is
available here.

## Recommendations

- Do NOT invest further in speculative decoding on the 12 GB GPU with
  Qwen3.6-family models.
- The 53.9-56.4 tok/s (n-cpu-moe 0) / 44-47 (n-cpu-moe 10) regime stands as
  the practical ceiling for this hardware.
- Path to 100+ tok/s remains: a bigger GPU (more VRAM → all-expert
  offload + real batching) or fewer bytes per expert read (lower quants,
  or a faster memory subsystem).

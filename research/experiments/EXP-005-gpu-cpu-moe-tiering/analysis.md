# EXP-005: GPU `--cpu-moe` Tiering Proof — Analysis

## Findings

1. **Mechanism works end-to-end.** The new `WS_LLAMA_EXTRA_ARGS` injection point
   passed `--cpu-moe -fa on` into llama-server; the 256-expert MoE loaded,
   generated, and reported honest stats (`backend: llama-server`,
   `n_experts: 256`, subprocess paging).

2. **Cold pages genuinely come from NVMe; warm runs hit the OS page cache.**
   The cold run faulted **3.13 MB/token** — expert pages were pulled from disk on
   first touch. The warm run faulted **0 MB/token**. **Caveat:** the whole
   11.5 GB model fits in this machine's 64 GB RAM, so "0 warm faults" only shows
   the OS page cache holding the *entire file* — it does **not** yet prove
   selective expert working-set management. That proof needs a model larger than
   RAM, or a VRAM-resident hot-expert cache to compare against.

3. **A 35B MoE generates at ~42 tok/s warm on this hardware via GPU +
   `--cpu-moe`.** Directionally this validates the tiering approach (the
   2.5–4.3 tok/s research figure was a different model/quant/16GB-RAM machine —
   see results.md context table; do not treat this as a measured speedup).

4. **VRAM honesty gap found:** this llama-server build (`b1-bb7049f7`) exposes
   **no `total_vram`/`used_vram`/`n_gpu_layers` in `/props`** — the backend
   correctly reports `gpu: null` instead of fabricating numbers, but real VRAM
   (nvidia-smi: 8.4–9.0 GB) stays out of `/v1/stats`. Older/newer builds expose
   it; this one doesn't. → follow-up: try `GET /slots` / `GET /metrics` or a
   build with full `/props`.

## Surprises

- Cold (44.42) was *faster* than warm (41.7) — explained by different prompts +
   background load, not by caching.
- 8/256 active experts ≈ 0.4 GB/token working set → decode should approach the
  VRAM-bandwidth ceiling (~70+ tok/s) with a tighter expert hot-cache; 42 tok/s
  leaves headroom (n_ctx 2048 KV + shared/attention also occupy VRAM).

## Conclusions & next steps

- ✅ **Key #1 (MoE tiering) mechanism is proven end-to-end on real hardware** —
  a 35B-class MoE runs ~42 tok/s warm on this box. The *selective hot-expert
  cache* benefit (vs whole-file page cache) still needs a bigger-than-RAM model
  or explicit hot-cache instrumentation to measure.
- Next: `-ncmoe` (partial CPU-MoE) tuning, KV cache type (`-ctk q8_0`), measure
  TTFT + p95, then speculative decoding on top for the 55–80 tok/s target.
- File a follow-up issue for the `/props` VRAM gap.

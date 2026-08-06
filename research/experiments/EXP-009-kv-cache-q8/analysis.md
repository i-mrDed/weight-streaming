# EXP-009: KV Cache q8_0 vs f16 — Analysis

## Finding

**KV quantization is a no-op on this machine (~10 MiB VRAM saved, tok/s
unchanged within noise).** This confirms EXP-007 with a direct experiment:
with `--n-cpu-moe 10` (30/40 expert layers + attention on GPU), the KV
cache still lands in HOST RAM — llama.cpp's unified KV allocates in RAM
when the model's offload leaves no VRAM headroom for a large KV block.

## Why it is not a lever here

- EXP-007 showed ctx 2048→32768 moved only +637 MiB in VRAM (vs +5 GB
  theoretical for FP16 in VRAM) — the KV is in RAM, so halving KV bytes
  saves RAM, not the scarce VRAM.
- The decode bottleneck is expert weight streaming from RAM (bandwidth),
  not KV read/write — so even a KV speedup would not move tok/s.

## When q8_0 WOULD matter

- If the KV cache were forced into VRAM (e.g. all layers offloaded with
  VRAM to spare, or `-nkvo`/KV-offload flags), q8_0 would roughly double
  the usable ctx on a 12 GB card — the feature shipped in the load API
  (`kv_cache_type`) is correct and future-proof, just not useful on this
  specific configuration.

## Action

- No code change needed. Keep the `kv_cache_type` load control (already in
  the API + Settings UI) for setups where KV lives in VRAM.
- Next lever candidates: speculative decoding (EXP-010) or a bigger GPU.

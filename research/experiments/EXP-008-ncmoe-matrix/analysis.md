# EXP-008: `--n-cpu-moe` Matrix — Analysis

## Findings

1. **The path to 40+ tok/s exists and is now measured:** `--n-cpu-moe 0`
   (ALL experts on GPU) gives **53.9 tok/s** — **3.0×** the `--cpu-moe`
   baseline (17.9 tok/s) — with p95 20.2 ms (3× better than 60.5 ms). Even
   `--n-cpu-moe 10` (30/40 layers' experts on GPU) reaches **44.5 tok/s**
   (+149%), and `--n-cpu-moe 20` gives 33.8 tok/s (+89%).

2. **The scaling is smooth and monotonic** — every 10 layers of experts
   moved to GPU ≈ +8-10 tok/s and roughly halves p95 tail. This is the
   "expert bytes through RAM" curve EXP-005/006's contaminated numbers
   obscured: it is NOT an on/off cliff, it is a bandwidth-proportional
   trade-off, exactly as the DDR4-bound model predicted.

3. **VRAM headroom is the binding constraint:**
   - `--n-cpu-moe 0`: 11,338 MiB / 12,288 MiB (**92%** — ~950 MiB left) →
     only one model, no room for KV growth or a second model.
   - `--n-cpu-moe 10`: 10,834 MiB (88%) — nearly as tight.
   - `--n-cpu-moe 20`: 8,532 MiB (69%) — comfortable; leaves ~3.7 GB.
   So the "best" config depends on the workload: single-model speed →
   `--n-cpu-moe 0`; multi-model or long-context → `--n-cpu-moe 20`.

4. **`--n-cpu-moe 10` is the sweet spot for THIS 12 GB card:** 44.5 tok/s
   at 88% VRAM. `--n-cpu-moe 0`'s extra 9 tok/s costs the last ~500 MiB of
   safety margin.

## What this corrects

- EXP-005/006 claimed 42-46 tok/s with `--cpu-moe` — INVALID (contaminated).
  The clean `--cpu-moe` number is 17.9-18.4 tok/s. But their headline
  "40+ tok/s is reachable on this machine" turns out to be TRUE via a
  different mechanism: expert GPU offload (`--n-cpu-moe`), not expert RAM
  streaming.
- The KV-cache-in-RAM finding (EXP-007) still holds: with `--cpu-moe` the KV
  cache was mostly host-RAM. Under `--n-cpu-moe N` the numbers above are the
  relevant ones for real deployments.

## Practical recommendation

| Goal | Config | tok/s | VRAM headroom |
|------|--------|------:|--------------:|
| Max single-model speed | `--n-cpu-moe 0` | 53.9 | ~0.9 GB |
| Speed + safety | `--n-cpu-moe 10` | 44.5 | ~1.4 GB |
| Multi-model / long ctx | `--n-cpu-moe 20` | 33.8 | ~3.7 GB |
| (legacy) all-CPU experts | `--cpu-moe` | 17.9 | ~8.4 GB |

## Next steps

- Wire `n_cpu_moe` as a first-class load option (like gpu_layers/kv_cache_type
  from P7.5) instead of only via WS_LLAMA_EXTRA_ARGS — one restart-free knob.
- Optionally combine with KV q8_0 (EXP-007's untouched suggestion) to claw
  back VRAM and allow `--n-cpu-moe 0` with a bigger n_ctx.
- Re-verify p95 vs `-fa on` (flash attention) interaction.

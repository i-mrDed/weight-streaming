# EXP-011: Ultra-Low-Bit Quant (IQ1_M) — Analysis

## The lever that worked

For the first time on this machine, decode passed **70 tok/s** (72.4
server-side, 77.6 raw) — up from the 53.9–56.4 ceiling that held across
EXP-005/006/008. The mechanism is exactly the one predicted in the
hardware plan: on a bandwidth-bound MoE tiering setup, **bytes-per-expert
is the currency**; a 13% smaller file (10.05 vs 11.5 GB) bought a ~30%
tok/s gain because attention + shared live fully in VRAM while expert
reads move fewer bytes.

## Why n-cpu-moe 0 specifically

- IQ2_M at n-cpu-moe 0: 56.4 tok/s but VRAM pinned at ~12,067 MiB —
  right at the ceiling, some expert layers likely spilled.
- IQ1_M at n-cpu-moe 0: 72.4 tok/s at 10,803 MiB — 1.5 GB of slack, and
  the whole model (all experts) fits the GPU. "All experts GPU" finally
  means *actually* all.
- n-cpu-moe 10 (10 experts CPU): unchanged because the win is NOT about
  tiering — it is about total bytes over the wire.

## Updated ceiling on THIS hardware

| setup | tok/s |
|-------|:---:|
| Qwen3.6-35B-A3B IQ2_M, any tiering | ≤ 56.4 |
| **Qwen3.6-35B-A3B IQ1_M, n-cpu-moe 0** | **72.4–77.6** |
| target (project goal) | 100+ |

~75 tok/s is now real, reproducible, and verified through the clean-room
gate. The remaining gap to 100+ is ~30% more bandwidth — which is a
hardware question (a 3090's 936 GB/s is 2.6× this GPU's 360 GB/s; see
`research/HARDWARE_100TPS_PLAN.md`).

## Backlog items surfaced this session (not acted on)

1. **Hub download integrity:** mid-stream EOF was treated as success —
   FIXED (integrity gate + regression test). A follow-up could verify the
   GGUF tensor table end-of-file rather than relying on Content-Length
   alone.
2. **Jan.exe llama-server orphans:** Jan spawns llama-server children the
   clean-room gate flags. Consider excluding Jan-owned PIDs (by parent
   image) from FAIL → WARN so benchmarks are possible while Jan runs, or
   document "close Jan before measuring".
3. **IQ1_M quality eval:** tok/s is not quality — a quick perplexity or
   sample check on the IQ1_M vs IQ2_M would bound how usable 77 tok/s
   actually is.
4. **Auto-select quant by free VRAM:** with per-quant tok/s now known,
   the server could pick IQ1_M (fast) vs IQ2_M (quality) on load based on
   `gpu_layers` headroom — a small feature win for the console.

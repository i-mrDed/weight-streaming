# EXP-007: Context Size (KV Cache) Scaling — Analysis

## Findings

1. **n_ctx has NO measurable effect on decode speed** on this setup:
   18.36–18.72 tok/s at 2048/8192/32768. Decode is bottlenecked by expert
   streaming from DDR4 RAM (the 8 active experts/layer are still read through
   RAM), not by KV cache size. p95 is flat too (56.8–63.7 ms).

2. **The KV cache is NOT fully resident in VRAM.** Going 2048 → 32768 ctx
   grew VRAM by only +637 MiB (3,822 → 4,459 MiB) — far less than the
   ~+5 GB a fully-resident FP16 KV would need. The llama-server working set
   (RAM) is identical (5.84 vs 5.87 GB). Conclusion: on this build with
   `--cpu-moe`, llama.cpp keeps most of the KV cache in host RAM, or
   allocates it lazily as context actually fills. Either way, the earlier
   "ctx = linear VRAM trap" fear was WRONG for this setup.

3. **The +2,000 MiB delta between "after load" and "after gen"** is the GPU
   compute buffer + the part of the KV cache that is on-device, allocated
   lazily on first generation — not the model weights (those were already
   loaded). It is roughly constant across ctx sizes (+2,026 / +2,069 /
   +2,573 MiB), consistent with "small fixed KV portion + compute workspace".

## 🚨 Major correction: EXP-005 and EXP-006 are contaminated

While setting up this experiment I found a **stale Jan llama-server
(Qwythos-9B-Claude-Mythos-5-1M, dense 9B, loaded with `-c 1024`)** that had
been running since 2026-08-04 on **port 8805 — the exact default port our
LlamaServerBackend uses**. The backend's `_wait_ready()` only polls
`/health` on that port and does NOT verify the responder is its own
subprocess. With the stale server answering `/health`, the backend believed
it was ready and forwarded all requests to the WRONG model.

Evidence:

- **46–51 tok/s** (before kill, contaminated) vs **18.36–18.72 tok/s**
  (after kill, verified via `/props` model_path guard) — same harness, same
  server, same env. The ONLY change was killing the stale server.
- Qwythos-9B is a **dense 9B model fully resident in VRAM** → 46-51 tok/s on
  an RTX 3060 is exactly the expected range. The 35B-A3B with `--cpu-moe`
  (experts stream from RAM) genuinely runs at ~18.4 tok/s on this machine.
- EXP-006's "threads make no difference (8=12=16)" was ALSO explained: a
  dense GPU-resident model is GPU-bound, so CPU thread count is irrelevant.
  That was misread as "memory-bound MoE expert streaming".

Consequences for the record:

- EXP-005's "42–44 tok/s GPU tiering proof" and EXP-006's "threads are
  memory-bound" are **not trustworthy** — they measured Qwythos-9B, not
  Qwen3.6-35B-A3B. The REAL 35B-A3B + `--cpu-moe` speed on this machine is
  **~18.4 tok/s** (still 4–7× the 2.5–4.3 tok/s full-mmap CPU baseline, but
  NOT the 10–17× claimed).
- The real `--cpu-moe` decode speed being ~18.4 tok/s — about 2.3× below the
  earlier claim — reframes the tiering picture: expert RAM-streaming works
  but is bandwidth-bound (~8 experts/layer through DDR4), so the path to
  40+ tok/s is NOT threads (EXP-006 was void) but reducing bytes through
  RAM: `-ncmoe` (put some experts on GPU), larger expert hot-cache, or a
  faster memory tier.

## Root cause + fix

`LlamaServerBackend._wait_ready()` binds a FIXED default port (8805) and
accepts any `/health` 200 response. If ANY other llama-server happens to
listen on 8805, the backend silently talks to it. Fix options:
(a) verify `/props` model_path matches the loaded model after ready
(b) pick a free port at spawn time (port 0 / OS-assigned)
(c) both.

The measurement script now implements guard (a) for the harness
(`verify_backend()` after warm-up); the backend itself still needs a fix
(recommended follow-up).

## Conclusion & next steps

- ✅ n_ctx is NOT a VRAM/speed trap on this setup — 32768 ctx is usable
  (the model's own 262k limit aside). The earlier "don't chase 262k" advice
  still holds for conversation-fit reasons, not VRAM reasons.
- ✅ Real 35B-A3B `--cpu-moe` speed: **~18.4 tok/s** (corrected).
- ⏭ Fix `_wait_ready()` port-collision vulnerability (backend code).
- ⏭ Re-run the `-ncmoe` / KV-q8 experiments (EXP-008+) on the now-clean
  harness — the earlier premises need remeasuring.

# EXP-007: Context Size (KV Cache) Scaling — Results

## Raw data (200-token generation, warm, `--cpu-moe -fa on`, t=8)

| n_ctx | server tok/s | SSE tok/s | VRAM after load | VRAM after gen | KV/compute delta | p95 ms |
|------:|-------------:|----------:|----------------:|---------------:|-----------------:|-------:|
| 2048  | 18.41        | 19.78     | 1,825 MiB       | 3,851 MiB      | +2,026 MiB       | 59.9   |
| 8192  | 18.72        | 20.17     | 1,934 MiB       | 4,003 MiB      | +2,069 MiB       | 57.8   |
| 32768 | 18.57        | 19.89     | 1,894 MiB       | 4,467 MiB      | +2,573 MiB       | 56.8   |
| 2048 (repeat) | 18.36 | 19.75   | 1,858 MiB       | 3,852 MiB      | +1,994 MiB       | 63.7   |

VRAM baseline (no model): ~1,810–1,839 MiB.

## Where does the KV cache live? (working-set check)

| n_ctx | llama-server WorkingSet (RAM) | VRAM |
|------:|------------------------------:|-----:|
| 2048  | 5.84 GB                       | 3,822 MiB |
| 32768 | 5.87 GB                       | 4,459 MiB |

→ RAM working set is IDENTICAL for both (5.84 vs 5.87 GB); VRAM grew only
+637 MiB from 2048→32768 ctx (NOT the +5 GB a fully-resident FP16 KV at
32768 would need).

## Speed verdict

**tok/s is flat across all context sizes: 18.36–18.72** (server-measured).
p95 also flat (56.8–63.7 ms). The KV cache reservation size does NOT affect
decode speed on this setup.

## Stale-server contamination (discovered DURING this experiment)

Before killing the stale Jan llama-server (Qwythos-9B, port 8805 — the same
port our backend uses), the SAME harness measured 46–51 tok/s with flat VRAM
delta (~0) across all n_ctx. After killing it, the backend spawned its OWN
llama-server and the verified numbers above (18.4 tok/s) appeared. The
46-51 tok/s readings match Qwythos-9B (dense 9B, fully GPU-resident)
perfectly — see analysis.

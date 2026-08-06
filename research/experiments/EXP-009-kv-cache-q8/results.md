# EXP-009: KV Cache q8_0 vs f16 — Results

Measured 2026-08-06, clean-room gate PASSED, flags verified token-exact on
the live llama-server cmdline (`--n-cpu-moe 10 -fa on [-ctk q8_0 -ctv q8_0]`).

| config | server tok/s | raw tok/s | VRAM after gen | p95 |
|--------|:---:|:---:|:---:|:---:|
| n-cpu-moe 10 + f16 (baseline) | **46.9** | 49.3 | 10,080 MiB | 21.9 ms |
| n-cpu-moe 10 + q8_0 KV | 44.9 | 48.1 | 10,070 MiB | 23.9 ms |

VRAM delta from quantizing the KV cache: **~10 MiB** (within measurement
noise). tok/s difference is within run-to-run variance (44.3-46.9 observed
for the same f16 config across sessions).

## Raw output (scripts/.ws-matrix-q8.log → .ncmoe_matrix_out.json)

```
ncm10 f16 (baseline):  server_tok_s=46.9  vram=10080  p95=21.9
ncm10 q8_0 kv:         server_tok_s=44.9  vram=10070  p95=23.9
```

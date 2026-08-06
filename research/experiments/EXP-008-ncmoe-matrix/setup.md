# EXP-008: `--n-cpu-moe` Matrix (partial expert offload) — Setup

> **Contamination note:** the first attempt of this sweep was invalid — the
> API-server restart left orphaned llama-server subprocesses squatting on
> port 8805 (Windows does not kill children with the parent), so every config
> reported the SAME 32.8 tok/s / 8,566 MiB. Fixed by killing ALL
> llama-server.exe processes before each restart and verifying the spawned
> cmdline actually contains the expected flag (see `measure_ncmoe_matrix.py`).

## Goal

Find the path to 40+ tok/s on Qwen3.6-35B-A3B by offloading experts to the
GPU with `--n-cpu-moe N` ("keep experts of the first N layers on CPU"),
instead of `--cpu-moe` (ALL experts on CPU, measured 17.9 tok/s in the same
session). EXP-005/006's 42-46 tok/s claims were invalidated by contamination;
this is the clean remeasure.

## Hardware / software

- CPU i9-9900KF (8C/16T), 64GB DDR4-3200 (~45 GB/s), RTX 3060 12GB VRAM
- llama-server Jan b9967 win-cuda-13-common_cpus-x64 (b1-bb7049f7)
- Model: Qwen3.6-35B-A3B-UD-IQ2_M.gguf (11.52 GB, 256 experts/layer, 8 active)
- 40 layers total. `--n-cpu-moe N` = first N layers' experts on CPU, rest GPU.

## Matrix (all with `-fa on`, t=8, ctx 2048, 200 tokens, warm)

| config | WS_LLAMA_EXTRA_ARGS |
|--------|---------------------|
| cpu-moe (baseline) | `--cpu-moe -fa on` |
| n-cpu-moe 10 | `--n-cpu-moe 10 -fa on` |
| n-cpu-moe 20 | `--n-cpu-moe 20 -fa on` |
| n-cpu-moe 0 (all GPU) | `--n-cpu-moe 0 -fa on` |

## Method

1. Kill ALL llama-server.exe (orphan guard) + API server; restart with env.
2. Load model, trigger lazy spawn, **verify cmdline contains the flag**.
3. Warm-up generation → measured 200-token generation via SSE harness
   (per-token p95) + `/v1/stats` tok/s + VRAM after gen (nvidia-smi).

## Harness

`scripts/measure_ncmoe_matrix.py` + `scripts/measure_ctx_scaling.py`.

## Date / author

2026-08-06 — local agent, user-driven experiment.

# EXP-021 Results — mainline b10357 vs Jan b9967 (IQ2_XXS, default config)

## Throughput (harness, clean room, identical flags — default, t8, ctx 2048)

| engine | cold tok/s | cold faults/tok | warm tok/s | warm faults/tok |
| :--- | ---: | ---: | ---: | ---: |
| Jan b9967 (EXP-018) | 43–62 | ~2k | 52–61 | ~1.2k |
| **mainline b10357 (this run)** | **62.26** | 568 | **56.74** | 899 |

Same model (Qwen3.6-35B-A3B UD-IQ2_XXS, 10.0 GB), same harness, same
`--gen-tokens 120`, no extra args.

## Verdict
**mainline b10357 ≈ Jan b9967 — no meaningful gain.** Cold lands at the top
of Jan's measured band, warm in the middle. The 3060 + CPU lane is the
bottleneck, not the engine version.

## ❗ Lesson (why the first run measured 9 tok/s and was discarded)
The first b10357 run showed **cold 9.1 / warm 9.0 tok/s — 5-7x slower**.
Root cause: the prebuilt zip does NOT include the CUDA runtime DLLs —
`ggml-cuda.dll` silently fails to initialize and llama-server **falls back
to CPU without any error**, still "loading" and answering. The official
release ships the runtime separately (`cudart-llama-bin-win-cuda-12.4-x64.zip`).
After extracting its DLLs (cublas64_12.dll, cudart64_12.dll, …) alongside,
`--list-devices` reports `CUDA0: NVIDIA GeForce RTX 3060` and the real
number appears (62/57 tok/s).

**Honest-telemetry addendum:** a tok/s number can look perfectly real and
still be CPU-only — when swapping engines, verify the device actually
initialized (log line / `--list-devices`) before trusting the number.

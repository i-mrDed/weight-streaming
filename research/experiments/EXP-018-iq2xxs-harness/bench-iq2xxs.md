# 📊 Bench Matrix — honest measurement (real engine, clean room)

- **Model:** `D:\models\Qwen3.6-35B-A3B-GGUF\Qwen3.6-35B-A3B-UD-IQ2_XXS.gguf`
- **Platform:** Windows-11-10.0.22631-SP0
- **Generated:** 2026-08-10 15:21 UTC
- **Method:** fresh API server per config, llama-server cmdline verified, cold = first workload gen (disk-bound), warm = second gen (page-cache resident)

| config | extra args | cold tok/s | cold faults / disk MB/tok | warm tok/s | warm faults / disk MB/tok | warm VRAM |
| :--- | :--- | ---: | ---: | ---: | ---: | ---: |
| **default** | `` | 43.31 | 460 / n/a | 51.85 | 618 / n/a | n/a |

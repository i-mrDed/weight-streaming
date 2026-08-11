# 📊 Bench Matrix — honest measurement (real engine, clean room)

- **Model:** `~/models/Gemma4-26B-A4B-QAT\gemma-4-26B-A4B-it-qat-UD-Q4_K_XL.gguf`
- **Platform:** Windows-11-10.0.22631-SP0
- **Generated:** 2026-08-10 15:48 UTC
- **Method:** fresh API server per config, llama-server cmdline verified, cold = first workload gen (disk-bound), warm = second gen (page-cache resident)

| config | extra args | cold tok/s | cold faults / disk MB/tok | warm tok/s | warm faults / disk MB/tok | warm VRAM |
| :--- | :--- | ---: | ---: | ---: | ---: | ---: |
| **baseline t8** | `-fa on -t 8` | 30.89 | 1612 / n/a | 37.56 | 958 / n/a | n/a |
| **mtp t8** | `-fa on -t 8 --spec-draft-model ~/models/Gemma4-26B-A4B-QAT/MTP/mtp-gemma-4-26B-A4B-it-Q8_0.gguf --spec-type draft-mtp --spec-draft-n-max 2` | 38.68 | 1904 / n/a | 45.10 | 1239 / n/a | n/a |

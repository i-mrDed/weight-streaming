# 📊 Bench Matrix — honest measurement (real engine, clean room)

- **Model:** `~/models/Gemma4-12B-QAT\gemma-4-12B-it-qat-UD-Q4_K_XL.gguf`
- **Platform:** Windows-11-10.0.22631-SP0
- **Generated:** 2026-08-11 08:16 UTC
- **Method:** fresh API server per config, llama-server cmdline verified, cold = first workload gen (disk-bound), warm = second gen (page-cache resident)

| config | extra args | cold tok/s | cold faults / disk MB/tok | warm tok/s | warm faults / disk MB/tok | warm VRAM |
| :--- | :--- | ---: | ---: | ---: | ---: | ---: |
| **t8** | `-fa on -t 8 --spec-draft-model ~/models/Gemma4-12B-QAT/MTP/mtp-gemma-4-12B-it-Q8_0.gguf --spec-type draft-mtp --spec-draft-n-max 2` | 67.97 | 364 / n/a | 76.52 | 447 / n/a | n/a |
| **t12** | `-fa on -t 12 --spec-draft-model ~/models/Gemma4-12B-QAT/MTP/mtp-gemma-4-12B-it-Q8_0.gguf --spec-type draft-mtp --spec-draft-n-max 2` | 66.97 | 364 / n/a | 75.57 | 454 / n/a | n/a |

# 📊 Bench Matrix — honest measurement (real engine, clean room)

- **Model:** `C:\Users\dedch\models\Gemma4-26B-A4B-QAT\gemma-4-26B-A4B-it-qat-UD-Q4_K_XL.gguf`
- **Platform:** Windows-11-10.0.22631-SP0
- **Generated:** 2026-08-11 08:01 UTC
- **Method:** fresh API server per config, llama-server cmdline verified, cold = first workload gen (disk-bound), warm = second gen (page-cache resident)

| config | extra args | cold tok/s | cold faults / disk MB/tok | warm tok/s | warm faults / disk MB/tok | warm VRAM |
| :--- | :--- | ---: | ---: | ---: | ---: | ---: |
| **-fa on -t 12 --spec-draft-model C:/Users/dedch/models/Gemma4-26B-A4B-QAT/MTP/mtp-gemma-4-26B-A4B-it-Q8_0.gguf --spec-type draft-mtp --spec-draft-n-max 2** | `-fa on -t 12 --spec-draft-model C:/Users/dedch/models/Gemma4-26B-A4B-QAT/MTP/mtp-gemma-4-26B-A4B-it-Q8_0.gguf --spec-type draft-mtp --spec-draft-n-max 2` | 38.02 | 1986 / n/a | 50.38 | 1218 / n/a | n/a |

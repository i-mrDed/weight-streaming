# 📊 Bench Matrix — honest measurement (real engine, clean room)

- **Model:** `~/models/Gemma4-26B-A4B-QAT\gemma-4-26B-A4B-it-qat-UD-Q4_K_XL.gguf`
- **Platform:** Windows-11-10.0.22631-SP0
- **Generated:** 2026-08-11 07:55 UTC
- **Method:** fresh API server per config, llama-server cmdline verified, cold = first workload gen (disk-bound), warm = second gen (page-cache resident)

| config | extra args | cold tok/s | cold faults / disk MB/tok | warm tok/s | warm faults / disk MB/tok | warm VRAM |
| :--- | :--- | ---: | ---: | ---: | ---: | ---: |
| **t4** | `-fa on -t 4 --spec-draft-model ~/models/Gemma4-26B-A4B-QAT/MTP/mtp-gemma-4-26B-A4B-it-Q8_0.gguf --spec-type draft-mtp --spec-draft-n-max 2` | 31.00 | 1977 / n/a | 35.17 | 1124 / n/a | n/a |
| **t6** | `-fa on -t 6 --spec-draft-model ~/models/Gemma4-26B-A4B-QAT/MTP/mtp-gemma-4-26B-A4B-it-Q8_0.gguf --spec-type draft-mtp --spec-draft-n-max 2` | 38.59 | 1848 / n/a | 41.98 | 1250 / n/a | n/a |
| **t8** | `-fa on -t 8 --spec-draft-model ~/models/Gemma4-26B-A4B-QAT/MTP/mtp-gemma-4-26B-A4B-it-Q8_0.gguf --spec-type draft-mtp --spec-draft-n-max 2` | 35.90 | 1938 / n/a | 43.45 | 1175 / n/a | n/a |
| **t12** | `-fa on -t 12 --spec-draft-model ~/models/Gemma4-26B-A4B-QAT/MTP/mtp-gemma-4-26B-A4B-it-Q8_0.gguf --spec-type draft-mtp --spec-draft-n-max 2` | 41.78 | 1881 / n/a | 48.99 | 1200 / n/a | n/a |
| **t16** | `-fa on -t 16 --spec-draft-model ~/models/Gemma4-26B-A4B-QAT/MTP/mtp-gemma-4-26B-A4B-it-Q8_0.gguf --spec-type draft-mtp --spec-draft-n-max 2` | 35.27 | 1866 / n/a | 44.79 | 1301 / n/a | n/a |
| **fa off t8** | `-t 8 --spec-draft-model ~/models/Gemma4-26B-A4B-QAT/MTP/mtp-gemma-4-26B-A4B-it-Q8_0.gguf --spec-type draft-mtp --spec-draft-n-max 2` | 41.30 | 1931 / n/a | 43.99 | 1177 / n/a | n/a |
| **kv q8 t8** | `-fa on -t 8 -ctk q8_0 -ctv q8_0 --spec-draft-model ~/models/Gemma4-26B-A4B-QAT/MTP/mtp-gemma-4-26B-A4B-it-Q8_0.gguf --spec-type draft-mtp --spec-draft-n-max 2` | 37.24 | 1878 / n/a | 44.67 | 1058 / n/a | n/a |

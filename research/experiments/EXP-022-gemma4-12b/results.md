# EXP-022 Results — Gemma 4 12B QAT+MTP

## Throughput (harness, clean room, real engine)

| config | cold tok/s | cold faults/tok | warm tok/s | warm faults/tok |
| :--- | ---: | ---: | ---: | ---: |
| t8  | 67.97 | 365 | **76.52** | 447 |
| t12 | 66.97 | 364 | 75.57 | 454 |

Both with MTP draft (`--spec-type draft-mtp --spec-draft-n-max 2`).
Same build (Jan b9967), 120 gen tokens.

## vs the 26B (EXP-019/020, same day, same harness)

| | Gemma 4 **12B** QAT+MTP | Gemma 4 **26B** QAT+MTP (t12) |
|---|---|---|
| warm tok/s | **76.5** | 49.0 |
| cold tok/s | 68.0 | 41.8 |
| faults/tok (warm) | **447** | 1200 |
| model size | 6.72 GB | 14.25 GB |

- **+52% faster** warm (76.5 vs 49.0), +63% cold.
- Faults/tok ~2.7x lower → the 12B **fits in 12 GB VRAM** (no CPU spill);
  the 26B spills ~2.25 GB and pays for it on every token.
- t8 ≈ t12 for the 12B (75–76 both) — with full VRAM residency the GPU is
  the lane, CPU threads no longer matter (opposite of the 26B, EXP-020).

## Thai gate
Ran at t8 (4096 max tokens, temp 0) — see `gate.json` / `gate.quality.md`
and the verdict in `analysis.md`.

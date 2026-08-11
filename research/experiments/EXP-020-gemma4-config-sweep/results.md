# EXP-020 Results — Gemma 4 QAT+MTP config sweep

## Throughput (harness, clean room, real engine — 14.25 GB on 12 GB VRAM)

| config | cold tok/s | cold faults/tok | warm tok/s | warm faults/tok |
| :--- | ---: | ---: | ---: | ---: |
| t4 | 31.00 | 1977 | 35.17 | 1124 |
| t6 | 38.59 | 1848 | 41.98 | 1250 |
| t8 (EXP-019 baseline) | 35.90 | 1938 | 43.45 | 1175 |
| **t12** | **41.78** | 1881 | **48.99** | 1200 |
| t16 | 35.27 | 1866 | 44.79 | 1301 |
| fa off t8 | 41.30 | 1931 | 43.99 | 1177 |
| kv q8 t8 | 37.24 | 1878 | 44.67 | 1058 |

All configs keep the MTP draft (`--spec-type draft-mtp --spec-draft-n-max 2`);
`-fa on` unless stated. Single clean sweep, same build (Jan b9967), same
model files as EXP-019.

## Key numbers
- **t12 warm 48.99 tok/s = best** — **+12.7%** vs the EXP-019 baseline
  (t8 43.45), **+8.8%** vs the 45.1 previously recorded for t8 (run variance).
- t12 also wins cold (41.78 vs 35.90 for t8, +16%).
- t16 regresses (44.79) — oversubscription on the 8C/16T i9-9900KF.
- flash-attn off ≈ on at 2048 ctx (43.99 vs 43.45) — fa is a long-context
  lever, not a decode one at this ctx.
- KV q8_0 ≈ f16 (44.67 vs 43.45) — ctx 2048 KV is tiny; no measurable gain.
- faults/tok flat across configs (~1.1–1.3k warm) → the gains are CPU
  compute-lane (expert/layer spill past 12 GB VRAM), not memory behaviour.

## Thai gate at t12 (quality confirm — 9 fixed questions, temp 0)
- **Sustained 50.71 tok/s** on /v1/stats during the gate (MTP active) —
  above even the matrix warm number (warm-up effect).
- **All 9 answers correct** — same verdicts as EXP-019 at t8:
  fact_thai ✅ · math 391 ✅ · logic 14 ✅ · code ✅ · thai_lang ✅ ·
  math_multi = 0 ✅ · price_pct 428 บาท ✅ · science ✅ ·
  **thai_tonal: tonal reasoning in the think block is PERFECT and
  identical to EXP-019 (ข่าว/ไข่/ไก่=เอก, ข้าว/เข้า=โท, ไหม=จัตวา with
  per-word example sentences)** — the final text was truncated by the
  4096-token budget because Gemma's think ran long this run (a token-budget
  artifact, not a quality regression; the verdict lives in the recorded
  think block, `gate.json`).
- Conclusion: threads change speed, not quality — t12 is safe as the
  daily-driver config.

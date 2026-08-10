# EXP-018 Results — IQ2_XXS (10.02 GB)

## Throughput (harness, clean room, real engine)

Two clean-room runs (same config, same day) — the spread is real:

| run | cold tok/s | cold faults/tok | warm tok/s | warm faults/tok |
| :--- | ---: | ---: | ---: | ---: |
| 1 | 61.8 | 451.7 | 61.1 | 628.7 |
| 2 | 43.3 | — | 51.8 | — |

- **Cross-run variance finding:** the "cold" number depends on OS
  page-cache state, not just disk. IQ2_XXS (10 GB) fits in 64 GB RAM's
  cache, so a cold run after heavy disk activity (pytest, downloads)
  faults more than one where the file pages survived. Honest band:
  **cold 43–62, warm 52–61 tok/s**; the sustained gate number (after
  warm-up, weights resident) is **63–66 tok/s** on /v1/stats.
- Paging: light page faults (~450–630/tok) — mostly resident in VRAM +
  page cache; **no disk thrash** (unlike DS V4 Flash's 36–77k faults/tok
  in EXP-012).

## Thai quality gate (9 fixed questions)

| qid | result | note |
| :--- | :--- | :--- |
| fact_thai | ✅ | กรุงเทพมหานคร, แม่น้ำเจ้าพระยา |
| math | ✅ | 391 |
| logic | ✅ | 14 ขา (พร้อมเหตุผล) |
| code | ✅ | is_palindrome + cleaning/lowercase |
| thai_lang | ✅ | น้ำขึ้นให้รีบตัก — ความหมายโดยนัยถูกต้อง |
| math_multi | ✅ | 3²+4²−5² = 9+16−25 = 0 (ดูเหมือนผิดตอน truncate แต่ถูก) |
| price_pct | ✅ | 500 → −20% → 400 → +VAT 7% |
| science | ✅ | 1 กก. / 500 กรัม |
| **thai_tonal** | ❌ | **1/6 ถูก** — see below |

## thai_tonal — the discriminator (full answer at 4096 tokens)

IQ2_XXS assigns (from its own think block, verified twice by the model):

| word | correct tone | IQ2_XXS said | verdict |
| :--- | :--- | :--- | :--- |
| ข้าว | โท (falling) | เอก (high) | ❌ |
| ข่าว | เอก (high) | เอก (high) | ✅ |
| เข้า | โท (falling) | เอก (high) | ❌ |
| ไข่ | เอก (high) | ตรี (rising) | ❌ |
| ไก่ | เอก (high) | ตรี (rising) | ❌ |
| ไหม | จัตวา (rising) | ตรี (rising) | ❌ |

Notably the model is *confidently* wrong — its think says "Wait, let me
double-check the tones and meanings carefully" then re-confirms the wrong
assignments ("All correct"). This is the same failure class as IQ1_M in
EXP-011, not a one-off sampling fluke (temperature 0).

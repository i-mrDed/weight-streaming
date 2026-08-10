# EXP-019 Results — Gemma 4 26B-A4B QAT (+MTP)

## Throughput (harness, clean room, real engine, 14.25 GB on 12 GB VRAM)

| config | cold tok/s | cold faults/tok | warm tok/s | warm faults/tok |
| :--- | ---: | ---: | ---: | ---: |
| baseline `-fa on -t 8` | 30.9 | 1612 | 37.6 | 958 |
| **MTP** `--spec-type draft-mtp --spec-draft-n-max 2` | **38.7** | 1904 | **45.1** | 1239 |

- **MTP works on this build and buys +20%** (37.6 → 45.1 warm;
  30.9 → 38.7 cold) — unlike DS V4's embedded MTP (EXP-015, −11–18%)
  where the draft step ran full expert-gated forward. Gemma 4's separate
  0.46 GB draft is cheap to run.
- Quality-gate run measured **46.7 tok/s** on /v1/stats (MTP active,
  sustained).
- Page faults ~1–2k/tok — moderate (14.25 GB file spills past 12 GB VRAM
  + page cache), no disk thrash.

## Thai quality gate (9 fixed questions, temperature 0)

| qid | result | note |
| :--- | :--- | :--- |
| fact_thai | ✅ | กรุงเทพมหานคร, แม่น้ำเจ้าพระยา |
| math | ✅ | 391 (3 methods shown) |
| logic | ✅ | 14 ขา พร้อมเหตุผล |
| code | ✅ | is_palindrome + preprocessing |
| thai_lang | ✅ | น้ำขึ้นให้รีบตัก — ความหมายโดยนัยครบ |
| math_multi | ✅ | 3²+4²−5² = 0 พร้อมวิธีทำ |
| price_pct | ✅ | 500 → 400 → +7% = **428 บาท** (2 วิธี) |
| science | ✅ | 1 กก. / 500 กรัม |
| **thai_tonal** | ✅ **6/6** | **PERFECT — see below** |

## thai_tonal — the discriminator, perfect

Gemma 4 assigns every word correctly, with tone-mark analysis + example
sentences + a summary table:

| word | correct | Gemma 4 said | |
| :--- | :--- | :--- | :--- |
| ข้าว | โท | **โท** (ไม้โท, falling) | ✅ |
| ข่าว | เอก | **เอก** (ไม้เอก) | ✅ |
| เข้า | โท | **โท** (ไม้โท) | ✅ |
| ไข่ | เอก | **เอก** (ไม้เอก) | ✅ |
| ไก่ | เอก | **เอก** (ไม้เอก) | ✅ |
| ไหม | จัตวา | **จัตวา** (ห+ม+ไ-, rising) | ✅ |

Summary table from the answer: ข่าว/ไข่/ไก่ = เอก · ข้าว/เข้า = โท ·
ไหม = จัตวา — all correct, with example sentences per word.

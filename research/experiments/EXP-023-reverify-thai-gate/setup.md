# EXP-023: Re-verify the Thai quality gate on the auto-tiering pair

## Date
2026-08-11

## Why
EXP-022 / EXP-019 / EXP-020 proved the Gemma 4 12B/26B QAT+MTP pair in the
bench harness (clean-room loads). The auto-tiering defaults were assembled
from those numbers, but the ⚡ Auto path loads through
`POST /v1/tiering/route` — a different code path. This experiment re-runs
the SAME Thai gate (9 fixed questions, temp 0) on the pair **through the
production route**, using the exact config a user has (extra_args + threads
+ evict/reuse), so the shipped defaults are confirmed — not assumed.

## Method
- `scripts/reverify_tiering_gate.py` against a live server on 127.0.0.1:8765.
- Tier selection: short prompt → fast, 3001-char prompt → quality.
- `weight_stream/bench/thai.py` — the project's fixed 9-question gate
  (temperature 0, reasoning off, max_tokens 8192).
- Same question set as EXP-011/018/022: fact_thai, math, logic, code,
  thai_lang, math_multi, price_pct, thai_tonal, science.

## History of the run (three attempts — the first two were the bug)
1. **2048 max_tokens, route as-shipped** — every long answer truncated
   mid-thought (finish_reason stop at ~430 tokens on the 12B).
2. **4096 max_tokens** — identical truncation lengths → max_tokens was not
   the limiter; investigated and found the real causes (see results.md):
   missing `-fa on` + route's n_ctx=2048 cap.
3. **After the fix** (`-fa on` + per-tier n_ctx 8192/4096, route passes
   n_ctx) — full clean answers on both tiers, gate 9/9 with tonal 6/6.

## Files
- `gate.json` — full answers (final + think) for both tiers, post-fix run
- `results.md` — the bug write-up, A/B proof, bench numbers, verdict
- `scripts/reverify_tiering_gate.py` — reproducible runner

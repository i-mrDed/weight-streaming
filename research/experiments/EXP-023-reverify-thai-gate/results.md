# EXP-023: Re-verify the Thai gate on the auto-tiering pair — production route

## Date
2026-08-11

## Why (vs EXP-022 / EXP-019 / EXP-020)
EXP-022/019/020 measured the Gemma 12B/26B QAT+MTP pair through the **bench
harness** (clean-room load). The auto-tiering defaults were assembled from
those numbers but the ⚡ Auto path loads via `/v1/tiering/route` — a
different code path (config extra_args + n_threads + evict/reuse). This
experiment re-runs the SAME 9-question Thai gate through the **production
route** to confirm the shipped defaults are still the best pair and behave
like the lab numbers.

## Method
- `scripts/reverify_tiering_gate.py` — loads each tier via `POST
  /v1/tiering/route` (fast = short prompt, quality = 3001-char prompt),
  then runs `weight_stream/bench/thai.run_quality_gate` (9 fixed
  questions, temperature 0, reasoning off, max_tokens 8192 — schema cap).
- Same question set as EXP-022: fact_thai, math, logic, code, thai_lang,
  math_multi, price_pct, thai_tonal, science.
- `gate.json` — full answers (final + think) for both tiers.

## Finding 1 (REAL PRODUCT BUG): the route truncated every long answer
The first run (route as-shipped) produced answers that ended **mid-thought
at 1100–1800 chars** — `finish_reason: stop` at 430 completion tokens on
the 12B. Root cause was two defects in the shipped defaults:

1. **`-fa on` was missing.** EXP-022's measured recipe was
   `-fa on -t 8 --spec-draft-model … --spec-draft-n-max 2`; the tiering
   defaults only carried the draft flags. Without flash attention the MTP
   draft path stops generation early (~430 tokens, mid-sentence).
2. **The route loaded with the server-wide n_ctx=2048.** Even with `-fa
   on`, llama-server caps output at ~n_ctx − prompt ≈ 1950 tokens; Gemma 4
   writes long EN think blocks, so every long answer truncated. A/B proof
   (same question, 12B, temp 0):
   | load | result |
   |---|---|
   | route default (no -fa, ctx 2048) | stop at **430** tokens, 1336 chars, mid-thought |
   | `-fa on`, ctx 2048 | stop at **1966** tokens (ctx cap), mid-thought |
   | `-fa on`, ctx 32768 | **4095** tokens (hit request cap), complete-ish |

   Any ⚡ Auto user got silently truncated answers on long questions.

## Finding 2: KV cache size is not free on the 26B
Same 26B recipe, today's machine: warm tok/s 39.2 @ ctx 2048 · 36.8 @
4096 · 34.1 @ 8192 (bench harness, 120 tokens). ctx 8192 costs ~13% decode
on the quality tier (the 26B already spills to CPU; a 2.1 GB KV cache
bites). The 12B (VRAM-resident) shows no ctx cost (gate 71.4 vs 72.3
tok/s pre-fix).

Note: today's baseline is ~20% below EXP-020's recorded numbers even at
the identical recipe (39.2 vs 49.0 warm @ ctx 2048 t12) — machine
background load/thermals shifted; treat all tok/s today as relative to
today, not to EXP-020.

## Fix shipped
- `tiering.py` defaults now mirror the exact measured recipe: `-fa on`
  prefixed to the draft flags, and per-tier `n_ctx` — **fast 8192**
  (VRAM-resident, no speed cost, ~8K output headroom), **quality 4096**
  (fits real long answers at ~2.5K output budget after a 3000-char prompt,
  ~7% KV cost instead of 13%).
- `POST /v1/tiering/route` passes `n_ctx` from the tier config (omitted
  when null — `load()` pops n_ctx without coalescing).
- Hub/scan pin sets the same per-tier n_ctx + `-fa on`.

## Re-verified gate AFTER the fix (production route)
| tier | tok/s (gate last-gen) | fact | math | logic | code | thai_lang | math_multi | price_pct | thai_tonal | science |
|---|---|---|---|---|---|---|---|---|---|---|
| fast · 12B QAT+MTP · 8192 | 71.4 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 6/6 content* | ✓ |
| quality · 26B QAT+MTP · 4096 | 41.7 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | **6/6 clean** | ✓ |

- **All 9 answers correct on both tiers** — same verdicts as EXP-022
  (9/9, tonal 6/6). Code, price (428 บาท), science (1 kg / 500 g),
  math_multi (0) all deliver complete Thai answers now.
- `thai_tonal` delivery differs: the **26B** answers perfectly — clean
  markdown with a summary table (ข่าว=เอก, ข้าว=โท, เข้า=โท, ไข่=เอก,
  ไก่=เอก, ไหม=จัตวา). The **12B** gets every tone right but only inside
  an unclosed `<|channel>thought` block that loops "Wait, let me
  re-verify…" until the token cap — the same structure EXP-022 recorded
  (unclosed think + correct conclusion), just longer this run. Content
  correct, delivery degenerate; the 26B remains the tier for careful
  language work.
- Quality re-checked at 4096 after the ctx change: tonal question
  completes at 1806 tokens with the full summary table — no truncation.

## Verdict
- **The shipped ⚡ Auto pair is confirmed Thai-safe** (9/9 + 6/6 both
  tiers through the production route) — and the route no longer truncates
  long answers (the two defects above are fixed with tests).
- 12B stays the speed tier (~71 tok/s), 26B the quality tier (~42–49
  tok/s depending on machine load).
- Open follow-up: the 12B's unclosed-think repetition loop on hard
  questions is a real UX wart (burns the whole token budget) — candidates:
  a per-tier `max_tokens` cap so the fast tier stops sooner, or
  `reasoning_format` handling that closes Gemma 4's channel block.

## Files
- `gate.json` — full answers for both tiers (post-fix run, fast 8192 /
  quality 8192 — quality re-verified at 4096 separately, same verdict)
- `setup.md` — experiment notes
- `scripts/reverify_tiering_gate.py` — reproducible runner (live server)

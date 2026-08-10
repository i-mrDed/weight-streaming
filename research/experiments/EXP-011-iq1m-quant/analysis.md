# EXP-011: Ultra-Low-Bit Quant (IQ1_M) — Analysis

## The lever that worked

For the first time on this machine, decode passed **70 tok/s** (72.4
server-side, 77.6 raw) — up from the 53.9–56.4 ceiling that held across
EXP-005/006/008. The mechanism is exactly the one predicted in the
hardware plan: on a bandwidth-bound MoE tiering setup, **bytes-per-expert
is the currency**; a 13% smaller file (10.05 vs 11.5 GB) bought a ~30%
tok/s gain because attention + shared live fully in VRAM while expert
reads move fewer bytes.

## Why n-cpu-moe 0 specifically

- IQ2_M at n-cpu-moe 0: 56.4 tok/s but VRAM pinned at ~12,067 MiB —
  right at the ceiling, some expert layers likely spilled.
- IQ1_M at n-cpu-moe 0: 72.4 tok/s at 10,803 MiB — 1.5 GB of slack, and
  the whole model (all experts) fits the GPU. "All experts GPU" finally
  means *actually* all.
- n-cpu-moe 10 (10 experts CPU): unchanged because the win is NOT about
  tiering — it is about total bytes over the wire.

## Updated ceiling on THIS hardware

| setup | tok/s |
|-------|:---:|
| Qwen3.6-35B-A3B IQ2_M, any tiering | ≤ 56.4 |
| **Qwen3.6-35B-A3B IQ1_M, n-cpu-moe 0** | **72.4–77.6** |
| target (project goal) | 100+ |

~75 tok/s is now real, reproducible, and verified through the clean-room
gate. The remaining gap to 100+ is ~30% more bandwidth — which is a
hardware question (a 3090's 936 GB/s is 2.6× this GPU's 360 GB/s; see
`research/HARDWARE_100TPS_PLAN.md`).

## Quality eval: IQ1_M vs IQ2_M (same 9-question set, same n-cpu-moe 0)

Measured with `scripts/compare_quant_quality.py` (fixed 9-question Thai
set: facts, arithmetic, logic, code, idiom, multi-step math, percentage,
Thai tonal classification, science units; temperature 0, max_tokens 2048).

| metric | IQ1_M | IQ2_M |
|--------|:---:|:---:|
| tok/s (measured) | **79.1** | 50.3 |
| fact / math / logic / code / idiom / math_multi / price / science | ✅ all correct | ✅ all correct |
| **Thai tonal classification (thai_tonal)** | ❌ **wrong** | ✅ correct |

### The one real regression: Thai tonal classification

IQ1_M got every word's tone wrong, in a *systematic* way — it asserted
`ไม้เอก → เสียงโท` and `ไม้โท → เสียงตรี` (both false; correct mapping is
ไม้เอก → เสียงเอก, ไม้โท → เสียงโท):

- ข้าว → it said เสียงตรี (จริงคือ เสียงโท)
- ข่าว / เข้า → it said เสียงตรี (จริงคือ เสียงเอก)
- ไข่ / ไก่ / ไหม → it said เสียงโท (จริงคือ เสียงเอก)

First run (earlier session) showed a different error pattern (ข้าว =
เสียงสามัญ, ไข่/ไก่ = เสียงตรี) — also wrong. So the failure is
reproducible across runs, not a one-off. IQ2_M classified all six words
correctly in both think and final answer.

### Follow-up probe (2026-08-10): hard minimal pairs + determinism

`scripts/probe_tonal_determinism.py` — 6 words forcing real tonal
discrimination across consonant classes (ข = high-class, ค = low-class),
3 runs per quant at temp 0:

| word (correct tone) | IQ1_M (3 runs, identical) | IQ2_M (budget 4096) |
|---------------------|:---:|:---:|
| ข้าว (โท) | ตรี ❌ | **โท ✅** |
| ข่าว (เอก) | ตรี ❌ | จัตวา ❌ |
| เข้า (เอก) | สามัญ ❌ | โท ❌ |
| ค้าว (ตรี) | ตรี ❌ | จัตวา ❌ |
| ค่าว (โท) | ตรี ❌ | จัตวา ❌ |
| เข่า (เอก) | ตรี ❌ | จัตวา ❌ |
| **total** | **0/6** | **1/6** |

**IQ1_M is deterministically broken**: all 3 runs byte-identical (3157
chars), everything mapped to เสียงตรี — its tonal model is destroyed.

**Surprise — IQ2_M fails the hard pairs too.** It got ข้าว right but
classified ข่าว/เข้า/ค้าว/ค่าว/เข่า wrong, with *fabricated* reasoning:
it claims ค is a high-class consonant (จริงคืออักษรต่ำ) and invents a
`ไม้โท → จัตวา` rule that does not exist. In the 9-question set above,
IQ2_M passed the same word ข่าว — so its tonal knowledge is
**prompt-fragile**: OK on common words (ข้าว/ไข่/ไก่), wrong when the
prompt forces real consonant-class rules.

**Refined verdict:** the earlier claim "IQ2_M = quality floor for tonal
work" was too strong. For Thai tone tasks, *neither* quant is reliable;
the gap is IQ1_M is always wrong (deterministic, 0/6) while IQ2_M is
sometimes wrong (1/6 on hard pairs, correct on common words). For
general Thai chat (the other 8 dimensions) they remain equal.

### Verdict: is 79 vs 50 tok/s worth it?

**For general use — yes.** 8 of 9 dimensions are byte-identical in
quality; the +57% tok/s (79.1 vs 50.3) costs nothing there.

**For Thai-language-sensitive tasks — mostly no.** Tonal classification
is broken in IQ1_M (deterministic 0/6, not random), and tones carry
meaning in Thai (ข้าว vs ข่าว vs เข้า are distinguished *only* by tone).
But the probe showed IQ2_M is not a reliable tonal floor either (1/6 on
hard pairs, fabricated rules) — it only survives common words. So the
trade-off is: IQ1_M = always-wrong tones + 79 tok/s; IQ2_M =
common-word tones + 50 tok/s. Neither is safe for tone-critical Thai
work; both are fine for ordinary chat.

**Recommendation:** keep both files; default IQ1_M for speed, offer
IQ2_M as an explicit "quality" switch in the console load dialog
(backlog item: auto-select quant by VRAM headroom). This is the 
concrete trade-off the hardware plan predicted — quant bytes per expert
is the only lever that moved tok/s on this 12 GB machine, and it has a
real, measurable quality floor in tonal languages.

### Multi-turn real-chat test (2026-08-10, chat_test_multiturn.py)

Beyond single-shot Q&A, one realistic 6-turn work session was run per
quant (write email → shorten → summarize → formalize → debug code →
write pytest). Same config (n-cpu-moe 0, temp 0), max_tokens 2048.

| metric | IQ1_M | IQ2_M |
|--------|:---:|:---:|
| tok/s (stats) | **77.7** | 54.7 |
| wall time, 6 turns | 111.8 s | 195.4 s |
| single-shot tasks (email, summary) | ✅ complete | ✅ complete |
| follow-up context drift (asked user to resend the text it had in context) | **2/4 turns** (revise + formalize) | **1/4** (revise only) |
| code tasks (pytest) | ✅ complete, correct 3 cases | ✅ but final truncated by think-budget |

**Findings:**

1. **Speed gap holds in real chat**: 77.7 vs 54.7 tok/s (+42%), and the
   wall-clock gap is even bigger (111.8 vs 195.4 s) because IQ2_M writes
   longer think blocks.
2. **Context drift is real and quant-dependent**: on the *revise*
   follow-up BOTH quants lost the thread (asked the user to resend the
   email they had just written); on the *formalize* follow-up IQ1_M
   drifted again while IQ2_M completed the rewrite correctly. n=1
   conversation per quant — treat as observed signal, not a hard floor.
3. **Think-block starvation is a harness artifact affecting both**: the
   model writes EN think blocks even with reasoning off, eating the token
   budget and truncating finals (IQ2_M's pytest was cut mid-assert). Both
   quants hit it; real users would see it as occasional cut-off answers.

**Verdict (chat):** for single-turn/summarization work the quants are
indistinguishable; for long multi-turn conversations IQ1_M showed
weaker grounding (2 vs 1 drift). Combined with the tonal finding, the
honest guidance is: IQ1_M for fast single-shot work, IQ2_M when the
conversation is long or tone-sensitive.

## Backlog items surfaced this session (not acted on)

1. **Hub download integrity:** mid-stream EOF was treated as success —
   FIXED (integrity gate + regression test). A follow-up could verify the
   GGUF tensor table end-of-file rather than relying on Content-Length
   alone.
2. **Jan.exe llama-server orphans:** Jan spawns llama-server children the
   clean-room gate flags. Consider excluding Jan-owned PIDs (by parent
   image) from FAIL → WARN so benchmarks are possible while Jan runs, or
   document "close Jan before measuring".
3. ~~**IQ1_M quality eval**~~ — DONE (this section): 8/9 dimensions
   equal, Thai tonal classification broken; verdict above.
4. **Auto-select quant by free VRAM:** with per-quant tok/s and quality
   now known, the server could pick IQ1_M (fast) vs IQ2_M (quality) on
   load based on `gpu_layers` headroom — a small feature win for the
   console.

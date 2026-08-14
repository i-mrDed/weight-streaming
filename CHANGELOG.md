# Changelog — Speculative Weight Streaming

> รูปแบบ: [Semantic Versioning](https://semver.org/)  
> ทุกการเปลี่ยนแปลงต้องบันทึกในไฟล์นี้

---

## [0.15.0] - 2026-08-10 (updated 2026-08-13 — tag moved to current `main`; all
[Unreleased] entries below folded in. This is the release that goes public.)

### 🔒 Security hardening (2026-08-13) — pre-public deep review
- **WebSocket `/v1/stream` — Origin guard + API token**: the Origin is checked against an allowlist *before* `accept()` (rejects with 4408/4401), closing the drive-by-web-page hijack that CORS middleware cannot cover (a WS handshake is not a fetch). Optional `WS_API_TOKEN` auth. Tightened further to exact scheme+host+port matching (canonical, default-port folded) — consistent with the HTTP CORS policy.
- **MCP stdio args — code-execution flags blocked**: `-c`/`-e`/`eval`/`exec`/… (incl. `-c=…` variants) are rejected for allowlisted commands, closing an RCE primitive; `-m` stays allowed (the normal way to run an MCP server).
- Tests: `test_ws_security.py` (7) + `test_p4_security_hardening.py` (+37) — full suite green (497 passed).

### ⚡ Auto-compact + context defaults (PR #9/#10)
- **Auto-compact long conversations**: after 8 user turns the chat is summarized (side-bar action + collapsible banner), one-shot per conversation, silent failure — never blocks the UI; the manual button stays.
- **`n_ctx` default 2048 → 32768 (RAM-aware)** — long chats were stopping mid-way (root cause, not a symptom).
- **`max_tokens` default 1024/2048 → 4096** — answers were being cut mid-story.
- **Stale committed bundle regression fixed**: the served console bundle was rebuilt so these ship; a CI guard now fails when the committed bundle drifts from a fresh source build (plus a freshness test asserting the served bundle carries current sentinels).

### 🧠 Expert-routing capture (L1/A4 — PR #6)
- `WS_EXPERT` stderr reader captures per-token expert routing from the llama-server process; new `enable_routing`/`routing`/`routing_stats` API; `--reasoning` vs `--reasoning-format` flag-compat auto-detect.
- Verdict (EXP-031/031b): per-token expert prediction is a dead end on this architecture (routing changes ~97.7% of tokens) — the capture API stays as debug/paper telemetry.

### 🏗️ Refactor — `api_server.py` (1,756 lines) split into `routes/`
- New `routes/` package (`system`, `models`, `stream`, `issues`, `hub`, `agents`, `tiering`) + `ServerContext` dataclass; `api_server.py` now only wires middleware/static/lifespan. Route paths & responses unchanged (full suite green).
- mypy: `api_server` 79 → 1 error, new modules strict-clean; `llama_server.py` strict-clean + a non-strict regression fixed.

### 🧹 Stability, hygiene & docs sync (2026-08-13)
- `MCPHost.close()` swallows `GeneratorExit`/`RuntimeError` from transport teardown (clean shutdown).
- `tiering.test.ts` encoding fixed — BOM + mojibake em-dash → UTF-8 no-BOM.
- `MODEL_GUIDE`: `n_ctx` 32768 default + model compatibility table (tested 2026-08-13).
- `TASKS.md` board synced with reality; `projects.json` brain rev 75 (L1 closure + EXP-031/031b + model-guide notes, dev-machine path scrubbed); ROADMAP #3 IQ2_XXS status synced to the recorded decision.

### fix: CI — tiering tests no longer depend on the dev machine's model files
- **Hermetic defaults**: the shipped tier defaults (`~/models/Gemma4-12B-QAT/...`)
  were expanded at import time, baking the *developer's* home into the
  defaults — the pin/unpin tests passed locally only because the real Gemma
  files exist on the dev machine and failed on CI runners (no models dir).
  The literal `~` paths are now expanded lazily by `_expand()` at load/save
  time, so any machine expands them to its own home.
- **Test fixture `fake_default_models`**: stubs the default Gemma pair under a
  temp HOME (USERPROFILE+HOME) for the 4 pin/unpin tests that restore +
  validate the default tier — `test_pin_finds_files_and_wires_draft`,
  `test_pin_sets_per_tier_max_tokens`, `test_unpin_restores_default_tier`,
  `test_unpin_persists_to_disk`.
- Verified by simulating a CI-like machine (`HOME` pointing at a nonexistent
  dir): full suite 369 passed, matching the CI failure mode exactly (was
  `ValueError: ... file not found` on the runner's home path).

### ⚡ Auto-tiering round 6 — bound the fast tier's output budget (EXP-023 loop)
- **Per-tier `max_tokens`**: the tier config now carries an output budget
  per tier — fast **2048** (quick answers; a degenerate repetition loop —
  Gemma 4's temp-0 "let me re-verify…" — burns at most ~30 s instead of
  the full 8192) and quality **8192** (the 26B answers the same hard
  questions cleanly). `POST /v1/tiering/route` returns the tier's
  `max_tokens`; the ⚡ Auto chat clamps its request to it (`min(user
  setting, tier cap)`); the Thai-gate runner uses the route's budget per
  tier. Pinning a model from Hub/scan sets the same per-tier cap.
- **`/v1/models/load` now accepts `extra_args`**: the field was missing
  from `ModelLoadRequest`, so manual loads silently DROPPED llama-server
  flags (caught live in EXP-023 — a whole penalty matrix ran without its
  flags). The schema field forwards to the backend (same path the tiering
  route uses), so manual loads can carry e.g. MTP draft flags.
- **EXP-023 findings documented**: the 12B repetition loop was tested with
  repeat/presence/DRY penalties (all verified in the live cmdline) — none
  escape the temp-0 attractor; the loop is a benchmarking-path artifact
  (product chat is temp 0.7 + max_tokens 1024 and does not loop). See
  `research/experiments/EXP-023-reverify-thai-gate/results.md`.

### ⚡ Auto-tiering round 5 — live stats card, history export, gate re-verify
- **Auto-tiering card in Live Stats**: the Stats page now shows the tier
  split (big fast/quality numbers), total routes and the newest events
  — real data from `GET /v1/tiering/stats`, with an honest empty state
  when nothing has been routed yet.
- **Export route history**: the Overview drawer can now download the
  recorded routes as JSON or Markdown (one click, browser download).
- **EXP-023 — gate re-verified through the PRODUCTION route**: the Thai
  gate (9 questions) re-run on the shipped Gemma 12B/26B pair via
  `/v1/tiering/route` — **9/9 with tonal 6/6 on both tiers** (see
  `research/experiments/EXP-023-reverify-thai-gate/`).
- **BUG FIX (found by the re-verify): ⚡ Auto truncated long answers.**
  The route loaded models with the server-wide n_ctx=2048 and the shipped
  defaults were missing `-fa on` — together they stopped generation
  mid-thought at ~430 tokens (no `-fa on`) or ~1950 tokens (ctx cap),
  silently cutting every long answer. Fixes:
  - Defaults now carry `-fa on` (the exact recipe EXP-022 measured).
  - Per-tier `n_ctx` in the tier config — fast **8192** (12B fits VRAM,
    no speed cost), quality **4096** (the 26B pays ~13% decode for an
    8192 KV cache; 4096 costs ~7% and fits real long answers) — and the
    route forwards it. Hub/scan pin sets the same per-tier values.
  - Regression tests: defaults carry the recipe, route forwards n_ctx,
    a null n_ctx is omitted (never a literal None).

### ⚡ Auto-tiering — route requests to the right model (user-configurable)
- **Pin from the Models page**: every scan result now has a "Tier" menu —
  pick ⚡ fast or 🎯 quality and the scanned model becomes that tier
  (fetch-merge-save, other tier untouched). Pinning a Gemma QAT model
  auto-wires its MTP draft flags from the sibling `MTP/` file (EXP-022
  measured +20% with draft-mtp); pinning a DIFFERENT model clears the
  stale draft args so they never leak into another model's cmdline.
- **Pin from the Hub**: every "Proven on this rig" card now has
  ⚡ fast / 🎯 quality buttons that call the new `POST /v1/tiering/pin`
  endpoint — resolves the exact measured quant files on disk, wires the
  MTP draft sibling, and saves the tier without needing a full scan
  (adds `recPin*` strings to en/th hub locales).
- **Overlap fix**: the Models scan result "Tier" popup (Menu-wrapped
  button-in-button) overlapped the "Use in load form" button — replaced
  with two inline compact buttons (⚡ fast / 🎯 quality), no popup.
- `data/tiering.json` (machine-local absolute paths) is now gitignored
  — the server regenerates the default pair when the file is missing.
- **Unpin + active-tier badges**: Hub quant cards that ARE the fast/quality
  tier show a ⚡/🎯 badge and their pin button becomes ↺ Unpin (undo →
  restores the shipped default via new `POST /v1/tiering/unpin`); Settings
  shows a "Reset to default" button per non-default tier. The config
  response now carries `model_basename` + `is_default` per tier.
- **Reuse-already-loaded on route**: `/v1/tiering/route` now checks the
  loaded models by NORMALIZED PATH before loading — if the tier's file is
  already resident (even under a different model_id, e.g. loaded manually)
  it reuses it instead of evicting + reloading, and returns the effective
  `model_id` with `reused: true`.
- **Routing stats (Overview)**: every successful route is recorded into the
  usage history as a `kind: tier_route` event (shared ring + JSONL, never
  mixed into the generation history). New `GET /v1/tiering/stats`
  aggregates totals per tier/reason/model + the newest events; the Overview
  dashboard shows a live Auto-tiering card (total, ⚡/🎯 split, recent
  reasons, reused marker) with an honest empty/disabled state.
- **Test the router (Settings)**: a prompt box + reasoning selector calls
  the new `POST /v1/tiering/preview` — decides the tier from the LIVE
  config WITHOUT loading any model (verified: it never spawns a backend)
  and shows tier + reason + the model that would run.
- **Route history drawer (Overview)**: the Auto-tiering card now has
  "View all" → a drawer listing every recorded route (up to 200) with a
  fast/quality filter and per-event model/chars/reused metadata.
- **Debug context**: issue reports now carry a compact auto-tiering
  snapshot (enabled + totals per tier/reason — no prompts, no per-event
  detail) through `collect_debug_context(tiering=…)`.
  previous model's extra args so a stale draft path can never leak into
  the new model's llama-server cmdline.
- **Any two models, not hardcoded**: Settings → Auto-tiering lets the user
  pick a fast/quality pair from a model scan (or type paths); the router
  itself is model-agnostic. Shipped default = the Gemma 4 12B/26B QAT+MTP
  pair proven on this rig (EXP-022/019) with their measured flags
  (`-t 8`/`-t 12` + MTP draft) baked in.
- **Pure decision rule** (`server/tiering.py`, unit-tested): short prompt
  ≤ threshold → fast tier; long prompt or reasoning at/above the
  configured level → quality tier. Config persisted to
  `data/tiering.json` (local-first, same convention as MCP/assistants).
- **Endpoints**: `GET/PUT /v1/tiering/config` (with honest per-file
  on-disk resolution — a broken pair is visible, not silent) and
  `POST /v1/tiering/route` which auto-loads the chosen tier's model
  (409 when disabled so callers fall back explicitly).
- **Chat**: new ⚡ Auto entry at the top of the model menu routes each
  request through the server and shows which tier answered.
- `LlamaServerBackend` now takes per-model `extra_args` (precedence over
  the process-wide `WS_LLAMA_EXTRA_ARGS`) — tiering needs per-model MTP
  flags without a server restart; the env var stays as the global
  fallback (harness clean-room).
- Verified end-to-end on the real server: short prompt → 12B fast tier,
  long prompt / high reasoning → 26B quality tier, real Thai generation
  through the routed model. **pytest 348 passed** (+22 tiering), mypy
  clean, vitest 20/20, build green.

### ⚡ Daily driver upgraded — Gemma 4 12B QAT+MTP (EXP-022)
- **New fastest Thai-safe model on this rig: 75.7 tok/s sustained, Thai
  gate 9/9 + tonal 6/6** — the 6.72 GB model + 0.47 GB MTP draft fit
  entirely in 12 GB VRAM (faults/tok ~450 vs ~1200 for the 26B, no CPU
  spill, GPU-bound: t8 = t12). +52% faster than the 26B QAT at the same
  Thai quality, beating the Qwen speed kings (IQ1_M 74.7 / IQ2_XXS
  61–66) which FAIL the tonal gate.
- Leaderboard (this machine): 12B QAT+MTP 76 (daily driver speed) ·
  Qwen IQ1_M 74.7 (non-Thai) · Qwen IQ2_XXS 61–66 (non-Thai) ·
  26B QAT+MTP 49–51 (quality-first) — the 12B + 26B pair now covers
  speed AND quality with Thai safe on both.
- EXP-020 (config sweep): **26B optimum = `-t 12`** — warm 48.99
  (+12.7% vs t8), gate sustained 50.71, Thai unchanged; t16 regresses,
  fa-off and KV-q8 are no-ops at 2048 ctx.
- EXP-021 (engine swap proxy for ik_llama.cpp): mainline b10357 ≈ Jan
  b9967 (62/57 vs 43–62/52–61) → engine is not the bottleneck; ik build
  deferred (`research/IK_LLAMA_EVAL.md`). Lesson: prebuilt llama.cpp
  needs the separate `cudart-llama-bin` zip or it silently falls back to
  CPU (first run: 9 tok/s, discarded) — verify `--list-devices`.
- Hub "Proven on this rig" updated: Gemma 4 12B added as the top
  (thai) entry, 26B re-labelled quality-first, Gemma flags now carry
  the measured optimum (`-t 12` for 26B).
- Harness hardening (found by the 12B bench): after a sweep, the server
  is now restarted WITHOUT `WS_LLAMA_EXTRA_ARGS` — the last config's
  env (e.g. stale `--spec-draft-model`) used to linger and crash
  unrelated model loads; `measure.restore_clean_server()` restores the
  clean-room baseline (+ test).

### 🌐 Hub — recommendations hardened (localisation + in-app evidence)
- ``tagline``/``notes`` in the curated list now ship BOTH project languages
  (``{"en", "th"}``) — the UI picks the active locale while the measured
  numbers stay a single source of truth (locale-switch verified in-app).
- Evidence buttons open the experiment record INSIDE the app via the new
  ``GET /v1/research/experiment/{path}`` endpoint (server/research.py) —
  path-validated by realpath containment (traversal → 400, unknown → 404),
  only ``*.md`` files ever read, returned in setup → results → analysis
  order and rendered with the same XSS-safe markdown pipeline as the Docs
  page. No GitHub link needed (the repo is private).
- ``docs/CURATION_CHECKLIST.md`` — the repeatable process for a model to
  earn a "Proven on this rig" slot (clean room, Thai gate, verified bytes,
  evidence links) + role rules (a Thai-tonal-failing quant is never
  allowed a thai/balanced badge); linked from BENCHMARKING.md.
- New offline tests: locale completeness, research service containment,
  endpoint contract (3 new — suite at 325 passed).

### 🌐 Hub — "Proven on this rig" recommendations (`/v1/hub/recommended`)
- Curated list of models MEASURED on the reference machine (12 GB VRAM /
  64 GB RAM), each backed by an experiment record under
  `research/experiments/` — the honest-telemetry rule applied to curation:
  no downloads/likes ranking, only measured evidence.
- `GET /v1/hub/recommended` (static, no network): every entry carries the
  EXACT download files that were tested (byte sizes verified against HF),
  the measured tok/s range, Thai gate + tonal verdicts, and the experiment
  path as proof.
- Hub page renders the section before the latest feed: role badges
  (Thai-safe daily driver / Thai-safe·slower / speed-first), per-quant
  cards with green (pass) vs red (fail) Thai chips, llama-server flags
  used in the measurement, Evidence link to the experiment record, and a
  Download button that queues precisely the tested files.
- Ships with the first two proven entries: Gemma 4 26B-A4B QAT+MTP
  (EXP-019 — Thai 9/9 + tonal 6/6, 45–47 tok/s) and the Qwen3.6-35B-A3B
  quant family (EXP-011/EXP-018) with the honest speed/quality trade-off
  spelled out per quant.
- Integrity tests: the curated data is validated offline (experiment paths
  must exist, totals must equal the real file sums, Thai scores can never
  exceed their totals) + an endpoint contract test.

### ⚡ Bench harness — honest-measurement core (`weight_stream/bench/`)
- New package packaging the project's measurement discipline so ANY model
  can be measured reproducibly through the REAL engine (llama-server via
  the API server), never a simulation:
  - `thai` — the Thai quality gate: the 9 fixed questions proven in
    EXP-009/EXP-011 (ultra-low-bit quants fail Thai tonal accuracy), so a
    benchmark number is never reported without the quality side.
  - `measure` — clean-room measurement: kill stale llama-servers, fresh
    API server per config, load through the real backend, verify the
    ACTUAL spawned cmdline (presence + value-aware `-t/-fa/-ctk/-ctv`),
    cold + warm generations, tok/s + paging from /v1/stats.
  - `report` — JSON + markdown matrix/quality reports (honest FAILED rows
    with error, never silently dropped).
- New CLI subcommand: `python -m weight_stream bench <model.gguf>`
  (`--matrix`, `--extra-args`, `--thai`, `--quality-max-tokens`, `--export`,
  `--no-restart`, …) — replaces the legacy simulated benchmark for real
  numbers. Validated end-to-end on Qwen3.6-35B-A3B IQ2_XXS (EXP-018).
- Harness details hardened by the first real run: JSON export includes the
  quality gate with FULL answers/think (diffable records; display truncates
  but the record never does); the gate keeps the complete think block (it
  is the evidence — EXP-018's wrong Thai tones live there); the bench
  unloads the model after the gate so it leaves the machine as it found it
  (a leftover model previously tripped the single-port backend and the
  live test_server.py suite); ASCII-safe console output (the ✅ emoji
  crashed a cp1252 Windows console mid-script).
- New `scripts/resume_download.py` — resume-capable single-file downloader
  (HTTP Range append + byte-exact size verify). Recovered the stalled
  IQ2_XXS download at 97.6%; applies the EXP-011b integrity lesson (never
  claim done without a byte-count check) to plain downloads.
- New `tests/test_bench.py` (13 tests, offline-only: think-splitting,
  cmdline verification, /v1/stats shape normalization, quality-gate flow
  with fake transport, report formatting).

### 🐛 Report-ISSUE-003 fixed — loading a 2nd model no longer breaks silently
- Loading model B while model A (llama-server backend, single fixed port) is
  loaded used to register BOTH as loaded; every generate on B then failed
  with a confusing port-collision ModelError. Now `load()` evicts the idle
  llama-server model (response carries `evicted=[...]`) or fails fast with a
  clear ModelError when it is generating. Tests: `tests/test_p4_model_conflict.py`
  (6 offline tests).

### ⚡ Bench harness: `--sweep-threads` + Gemma 4 channel-think support
- New `--sweep-threads 4,8,12,16` convenience flag — builds the config
  matrix from a base `--extra-args` plus `-t N` per value (the hand-written
  `--matrix` JSON remains for arbitrary sweeps).
- `split_think` now also handles Gemma 4's `<|channel>thought …<channel|>`
  thinking format (test added).
- New `docs/BENCHMARKING.md` — official methodology (clean room, cmdline
  verify, cold/warm, page-cache variance, reproducibility checklist).

### 🧪 EXP-019: Gemma 4 26B-A4B QAT+MTP — new Thai-safe daily driver
- **Thai gate 9/9 + tonal 6/6 PERFECT** (first model on this machine to
  pass the tonal discriminator at a usable speed) — QAT sidesteps the
  IQ-quant quality cliff (EXP-011/018).
- **MTP works: +20%** (37.6 → 45.1 warm) via `--spec-type draft-mtp`,
  unlike DS V4's embedded MTP (EXP-015, −11–18%).
- Verdict: Gemma 4 QAT+MTP (45–47 tok/s) replaces Qwen3.6 IQ2_M as the
  Thai daily driver; Qwen IQ2_XXS stays the non-Thai speed king.

### 🧪 Frontend test coverage (api client)
- New `frontend/src/core/api.test.ts` (13 tests) covering the API client used
  by every page: `authHeaders()`/`setApiToken()` (B1 token store + Bearer
  attach, incl. storage-unavailable), `apiJSON()` (Content-Type only with
  body, auth on GET/POST, HTTP-error taxonomy with parsed `detail`, network
  wrapping) and `sseRequest()` (SSE auth header + `abort()`). Frontend suite
  now 20 tests (thinks 7 + api 13).

---

## [0.14.0] - 2026-08-10

### 🤖 P7 — Assistants, MCP, GPU backend & tool calling
- **P7.1b `LlamaServerBackend` (GPU)** — spawn llama-server subprocess with GPU offload (`-ngl`/`--n-cpu-moe`), native reasoning control, date injection, subprocess page-fault telemetry (`page_fault_count(pid=...)` on Windows), and honest stats for the GPU path. Readiness wait raised 60s → 300s for >RAM model loads (a 104 GB load takes ~69s cold).
- **P7.1c Jan-style chat controls** — thinking budget, per-model effort, streaming-safe thinking/answer split, `parseThinks` fixes.
- **P7.2 Assistants** — CRUD API + JSON store (`/v1/assistants`), console Assistants page + selector; assistant references now guard hub delete/clear.
- **P7.3 Tool calling** — OpenAI-compatible `tools`/`tool_calls`/`tool` role protocol.
- **P7.4 MCP host** — manage stdio/SSE MCP servers, list/call tools, settings UI section.
- **P7.5 GPU load options** — `gpu_layers` (`-ngl`) and `kv_cache_type` (`-ctk/-ctv`) on `ModelLoadRequest`, surfaced in Settings/load form; `WS_GPU_LAYERS`/`WS_KV_CACHE_TYPE` env defaults; quant advisor (`/v1/hardware` VRAM fit + sibling-quant suggestion).
- **Offline-first audit** + P7 status docs synced.

### 🔬 EXP-009…EXP-011 — quant & telemetry hardening
- **Clean-room gate** (`scripts/check_clean_environment.py`) — refuses to measure with stale servers/orphans; EXP-005/006 re-validated (old numbers were contaminated by a stale Jan llama-server on port 8805).
- **EXP-009** KV cache `q8_0` vs f16: **no-op on this machine** (~10 MiB VRAM, same tok/s) — KV lives mostly in host RAM. **EXP-010** speculative decoding: dead end recorded (no backend support).
- **Hub integrity gate** after download + `stream_timeout` + `Content-Range /total` size fallback; resume-after-truncation regression test.
- **EXP-011** IQ1_M on Qwen3.6-35B-A3B: **72–78 tok/s**, tonal determinism probe (IQ1_M 0/6 deterministic), IQ1_M vs IQ2_M quality eval (8/9 dimensions equal, Thai tonal broken).

### 📡 EXP-012 — DeepSeek-V4-Flash 0731 (104 GB) measured
- Full harness (`scripts/measure_dsv4flash.py`) with cold/warm paging + value-aware flag verification; one failed config no longer wipes the matrix.
- Download script: 4 shards, hard disk-free gate, safe target auto-selection, `--variant iq2m` fallback, synced sizes from HF tree API.
- Proved `deepseek4` arch + MXFP4 (type 39) tensors run on the pinned backend; hub learned subdir/sharded/Xet + metadata-only shard gate.
- **Result: 1.48–1.89 tok/s, disk-bound** (36–77k faults/token ≈ 150–300 MB disk/token); config moves the number ~15% only. P8 sweep (threads 4–16, fa-off, KV-q8) confirmed flat — GPU-bound configs are thread-insensitive.
- **Fixes en route**: llama-server child lowered below-normal (desktop stays usable), hub disk gate counts only remaining bytes on resume (unblocked a stuck 24 GB `.part`), `_wait_ready` 300s timeout.

### 🏠 Repo restructure, CI & packaging
- Moved to **https://github.com/i-mrDed/weight-streaming** — the project now lives at the repo root (was `.Weight-Streaming/` inside a workspace repo with unrelated projects); history rewritten clean, private/unrelated folders never pushed.
- **GitHub Actions CI green** (Python suite on Windows + frontend typecheck/build on Linux), workflow at repo-root `.github/workflows/ci.yml`.
- **Packaging fixes**: declared `gguf`, `aiofiles`, `starlette`, `pydantic`, `requests` (were imported but undeclared); GGUF fixture tests skip in CI (5.9 GB local model); `*.log` + model/env/secret ignores hardened.
- **Flake fixes**: tok/s and hub speed report real values when a generation/download finishes inside one clock tick (elapsed floored at 1e-9).
- Docs: `ARCHITECTURE_REVIEW.md`, `ADVISORY-2026-08-03-WASTE.md`, `DASHBOARD_THEME_SPEC.md`, waste-comparison research, EXP-012/013 records added.

### 🎉 Console Promoted to Production (P6) — 2026-08-04
- **Console (dashboard UI) กลายเป็น UI หลัก** — merge `feature/dashboard-theme` → `main` (`--no-ff`, HEAD `1dba698`) ตามมติผู้ใช้ trial-first
- **Route swap**: `/` → `/console/` (Console ใหม่), `/app` → `/app-legacy` (เก็บของเก่า 1 release เป็น rollback path)
- **ลบ `dashboard_server.py`** (CLI dashboard พอร์ต 8766 — เสิร์ฟค่าปลอม ขัด honest-telemetry) + call sites ใน `cli/main.py` + `cli/__init__.py`
- **Console ฟีเจอร์ครบ (P0–P5)**: Overview/Chat/Live Stats/Models/Issues/Hub/API Docs/Settings + i18n TH/EN (666 keys) + theme registry (classic/aurora) + constellation particles
- **P4 backend endpoints**: hub search/download+SSE progress, `/v1/usage/history`, `/v1/logs/tail`, `/v1/config` (+PATCH) — pytest +66
- **QA round-2 fixes**: activity table layout, sidebar server status, health gauges, classic particles, thinking prose fallback ("Thinking Process:"), per-model effort, thinking visibility toggle
- **Backup tag**: `feature/dashboard-theme-v1` (HEAD `27c6239`) — ย้อนกลับได้
- **Tests**: 192 passed / 7 skipped (GGUF fixture errors หายเพราะมี model จริงใน research/models)
- **P7 วางแผนแล้ว**: `docs/internal/P7_PLAN.md` — Jan-style chat controls + Assistant + MCP + offline-first

### 🛠️ Local Server Reliability
- Server CLI configuration now reaches `ModelManager`, so `--n-threads` applies to models loaded later from the SPA.
- Default inference threads use half of logical CPU cores, preserving headroom for the API server, browser, and operating system.
- Auto-unload is disabled by default for local chat sessions; opt in with `--idle-unload-timeout <seconds>` or `WS_IDLE_TIMEOUT`.
- Chat completions use the GGUF-native llama.cpp chat template when available, with the legacy prompt formatter retained only as a fallback.
- SPA exposes and sends `top_p` with each chat completion request.
- Added `docs/HANDOFF_STREAMING_RELIABILITY.md` and aligned task/roadmap/SPA-plan status with the remaining streaming work.

### ⚡ Streaming Reliability — Items 4–5 (2026-07-29)
- **Event loop no longer blocks during generation** (`model_manager.py`): all streaming paths consume llama.cpp's blocking iterators through a worker-thread bridge (`_iter_blocking` — bounded queue, backpressure, cooperative cancellation). While a long response generates, `/health`, `/v1/stats`, and other requests stay responsive (measured: ≤ 28 ms health latency during a 220-token / 14 tok/s generation on Qwen1.5-MoE-A2.7B Q2_K).
- **Cancellation is clean end-to-end**: client disconnect / Stop sets a stop flag the worker honors within ~0.25 s (halting llama.cpp compute), always resets `_generating`, and releases the per-model lock; the next request succeeds immediately (measured: 540 ms after abort).
- **New public chat API `WeightStreamModel.stream_chat()`** (`backends/llama_cpp.py`): native `create_chat_completion` streaming first, architecture-aware prompt-formatter fallback inside the backend, generation stats recorded on completion, error, AND early cancel, periodic OS page-cache sampling, and deliberately no synthetic prefetch (expert routing is opaque from Python). Server code no longer accesses `model._llm` for chat.
- **SPA streaming render batched** (`static/index.html`): deltas accumulate and paint at most once per animation frame via `textContent` + `white-space: pre-wrap` (no per-token `innerHTML` re-parse), SSE lines are buffered across reads, auto-scroll only pins while the user stays near the bottom, and Stop keeps the partial reply in history.
- **Honest telemetry in the Live Stats panel**: fabricated placeholder values removed (hit-rate 94.2%, prefetch 98.1%, residency 12.4 GB, "8/256 Active", random heatmap firing); metrics now show real measurements or `n/a`, and the heatmap reports the model's real expert count with an explicit "routing not observable" note.
- **Tests**: 19 focused regression tests in `tests/test_server_config_and_chat.py` (event-loop responsiveness, cancellation/error cleanup, wrapper native/fallback/telemetry contract); full suite 92 passed / 7 skipped.
- **Verification artifacts**: `scripts/verify_items_45.py` (rerunnable end-to-end check) and raw results + SPA screenshots in `docs/verification/`.

### ✅ Follow-ups completed (2026-07-30)
- **SPA PAGING DEMAND card**: fifth Live Stats metric (`generation.paging`, MB/token + fault tooltip); verified in Chrome cold 103.19 → warm 11.72 MB/tok.
- **Hard/soft fault split**: `disk_demand_mb` + `disk_demand_source` in paging stats — POSIX major faults directly, Windows estimated from model-file residency growth; real data: cold generation 237.5 MB/tok total faults but only 7.86 MB/tok disk, warm 0.0 MB disk.
- **Llama-family native template verified**: Llama-3.2-1B-Instruct Q2_K (downloaded 554 MB, gitignored) — embedded template, native path, zero leaked markers (`scripts/verify_llama_template.py`).
- **`stream_prompt()` public wrapper**: plain-prompt completions (`/v1/generate` SSE, Anthropic-compat) now stream through the wrapper with full telemetry; server code has zero direct `_llm` accesses.
- **MyPy clean**: 21 → 0 errors in default mode (43 files); `[tool.mypy]` config added; `--strict` baseline 225 recorded for incremental reduction.

### 🔬 Paging-demand telemetry (2026-07-30)
- New `weight_stream/io/page_faults.py`: cross-platform process page-fault counters (Windows `GetProcessMemoryInfo().PageFaultCount`, POSIX `getrusage()` minor+major) with a `paging_demand()` stats helper.
- `stream_chat()` and `generate()` now attach a `paging` block to generation stats (`faults`, `faults_per_token`, `fault_mb_per_token`), surfaced through `/v1/stats` — an honest telemetry channel for the `StreamingBuffer.total_accesses = 0` gap (llama.cpp reads its own mmap opaquely; verified live on Qwen1.5-MoE Q2_K at 0.129 MB/token steady-state).
- Spike `scripts/spike_page_faults.py` + raw results (`docs/verification/spike_page_faults_2026-07-30.json`): cold generation demands ~175 MB/token of paging vs ~0.55 MB/token warm (300x drop) — real-OS-data confirmation that the page cache's own LRU holds the working set (ADR-003 direction).
- Regression test added (`test_stream_chat_records_os_paging_demand`); full suite 93 passed / 7 skipped.

### 📚 Documentation sync (2026-07-30)
- `ARCHITECTURE.md`: new §0 "As-Built Summary" mapping the Phase 2 research design to the shipped product per ADR-003 (64 MB plain-LRU tracking, heuristic predictor, mmap + OS prefetch hints, llama-cpp-python adapter, honest telemetry) plus inline annotations on the diverged sections; sections 1–9 preserved as design history.
- `DECISIONS.md`: ADR-003 addendum with the first real-model validation metrics (Qwen1.5-MoE-A2.7B Q2_K: 17.9 tok/s, `/health` ≤ 23.3 ms during generation, 4.6% page residency, clean cancellation in 0.73 s) and the open buffer-tracking gap (`total_accesses = 0`).
- `ROADMAP.md` / `TASKS.md`: SPA streaming reliability marked validated on a real model; Phase 3 documentation tasks closed (stale "LFU default" note corrected).

### 🧊 Real-use fixes: CPU etiquette + thinking UI + model guide (2026-07-30)
Reported from live user testing with Jan Desktop models (Kimi R37 qwen35 4.2B F16, Ornith 9B Q6_K): 3–4 tok/s, CPU pinning the machine at 100%, and reasoning text mixed into chat answers.
- **Diagnosed 3–4 tok/s as physics, not a bug**: CPU decode is memory-bandwidth bound (`tok/s ≈ RAM bandwidth ÷ weight bytes per token`). F16 4.2B reads ~8.4 GB/token (more than the 9B Q6_K's 7.35 GB/token!); measured 2.8 tok/s vs predicted 2.4–3.6. All data points (incl. Qwen MoE 17.9 tok/s at ~1 GB/token active weights) sit on one ~23–35 GB/s bandwidth line.
- **Fixed: SPA-loaded models ignored the thread default** — `n_threads=None` (optional schema field) fell through to `os.cpu_count()` (every logical core) instead of the configured half-of-cores default; measured 56.2% of a 16-logical machine for one model. Now coalesced; per-model **THR** input added to the SPA Models tab.
- **Below-normal process priority while a model is loaded** — new `weight_stream/io/process_priority.py` (Windows `SetPriorityClass(BELOW_NORMAL_PRIORITY_CLASS)` with full ctypes prototypes; POSIX `nice +5` with honest restore-failure reporting). Lifecycle: first load lowers, last unload restores; live state in `/v1/stats` → `server.priority`; opt out via `WS_LOWER_PRIORITY=0`.
- **Measured (Kimi R37 F16, same machine)**: old code 2.8 tok/s · 56.2% process · 80.1% system → new default (8 threads, below-normal) 2.5 · 22.6% · 37.0% → THR=4: 2.3 · 16.0% · 26.5%. Bandwidth-bound: ~3.5× smaller CPU footprint for ~18% throughput.
- **Fixed: `/v1/models/scan` froze the whole server** — recursive glob + GGUF parsing ran on the event loop (discovered when scanning the Jan model store). Now in a worker thread; during a 113 s / 20-model scan, `/health` answered 45/45 polls. Default scan dirs now include the Jan Desktop store on Windows.
- **Scan reports `quant`** — dominant non-F32 tensor type by enum name (Q4_K, Q6_K, F16, …; authoritative over the `general.file_type` label). SPA shows it per option and warns ⚠️ before loading unquantized F16/F32/BF16 files on CPU.
- **SPA thinking/answer separation** — implements the thought accordion whose CSS shipped in 0.13.0 (that changelog line predated the JS; the parser is real as of this entry): ` think ` tags split stream-safely (markers arriving across token boundaries are held back, never shown raw), plus prose conventions for models that don't use tags ("Thinking Process:", "Chain of Thought", "Let's think step by step", "Reasoning") ending at explicit answer separators (Answer/Final answer/Conclusion/สรุป/คำตอบ/ตอบ). Collapsible 💭 panel, open while streaming, auto-collapsed on completion; applied to saved history too; marker-free messages render exactly as before. Verified live on Kimi R37 in Chrome (streaming + collapsed states).
- **`docs/MODEL_GUIDE.md` (new)** — the bandwidth model, measured per-model tables, quantization recommendations (Q4_K_M/Q6_K over F16 for CPU), and CPU-etiquette docs; README gained a summary section. `may_need_upgrade` scan flag drops `qwen35` (verified working on the pinned llama-cpp-python 0.3.34); remaining arches stay flagged conservatively.
- **Instrument**: `scripts/measure_cpu_attribution.py` — GetSystemTimes/GetProcessTimes sampling across idle/generating/cooldown phases; raw JSON artifacts in `docs/verification/`.
- **Tests**: +14 (priority backends incl. live round-trip; None-threads regression; priority lifecycle once-per-load/unload). Suite **113 passed**; mypy clean, 44 files.

## [0.13.0] - 2026-07-28

### 🎨 SPA Chat 2.0 & Live Stats Dashboard Redesign
- **SPA Frontend Overhaul (`static/index.html`)**:
  - **Collapsible Sidebar**: + New Chat button, grouped conversation history (Today, Yesterday, Older), model active badge, and status dot
  - **Fluid Chat Canvas**: 840px max-width centered canvas with Deep Space Glassmorphism styling (`#0b0f19`), 1-Click Code Copy button, and auto-expanding textarea
  - **Slide-over Right Drawer**: Settings for Reasoning Effort (`low`/`medium`/`high`), Temperature, Top-P, System Prompt Presets (`Coding Expert`, `Creative Writer`, `Data Analyst`, `Concise`), and Agent Tools toggles
- **Native GGUF Chat Template & Reasoning Thought Parser (`model_manager.py`)**:
  - Native template detection for ChatML (Qwen/DeepSeek), Llama-3 (`<|start_header_id|>`), and Instruct fallback formats
  - `<think>...</think>` CoT reasoning parser rendering clean thought accordions in chat UI
- **Live Stats Dashboard (`static/index.html`)**:
  - Live metric gauges for Buffer Hit Rate %, RAM Residency, Generation Speed (tok/s), and Prefetch Accuracy
  - Interactive MoE Active Expert Firing Heatmap Grid
- **Native C/C++ Acceleration & Tools**:
  - Integrated Native C-Core (`weight_stream_core.cpp`), IOCP Windows I/O (`win_iocp_stream.cpp`), SIMD INT4 kernels (`simd_kernels.cpp`), Shard Repacker tool (`shard_repacker.py`), and EAGLE-3 Dual Predictor (`eagle_dual_predictor.py`)

---

## [0.12.0] - 2026-07-27

### Issue Tracking System (full product loop)
- New package `weight_stream/issues/`: models, store, service, context, export
- API: POST/GET/PATCH `/v1/issues`, verify, export, `/v1/debug/context`
- CLI: `issues report|list|show|set-status|verify|export`
- SPA: Report Issue modal, My Issues tab, Verify/Still broken, Report this on load errors
- Lifecycle enforced: open → … → fixed → verify_pending → verified → closed
- Local storage: `data/issues/` (JSON + MD mirror + summary)
- Secret redaction in debug context
- Plan: `docs/ISSUE_SYSTEM_PLAN.md`
- Tests: 10 new issue lifecycle tests

### Engine upgrade
- llama-cpp-python **0.3.16 → 0.3.34**
- Qwen3.5/Qwen3.6 architectures (`qwen35`, `qwen35moe`) now load
- Verified: Qwen3.6-35B-A3B loads and generates coherent text

---

## [0.11.0] - 2026-07-27

### 🔌 Phase 6: API Server + Full Frontend Platform + Anthropic Support

#### API Server (`weight_stream/server/`)
- **REST API**: 7 endpoints — generate, stats, models (load/unload/list), health
- **WebSocket**: `ws://host/v1/stream` — token-by-token streaming with cancel
- **OpenAI Compat**: `POST /v1/chat/completions` — VS Code, Cursor, Continue.dev, Cline
- **Anthropic Compat**: `POST /v1/messages` — Claude Code, Anthropic SDK
- **ModelManager**: async model lifecycle, auto-idle unload, thread-safe

#### CLI — 3 commands added
- `server` — start API server with auto-load model (port 8765)
- `ui` — launch Gradio Web UI
- `tui` — launch Textual terminal UI

#### 5 Frontends
| # | Frontend | Technology | Access |
|---|----------|-----------|--------|
| 1 | SPA | Vanilla JS (single HTML) | `http://localhost:8765/app` |
| 2 | Gradio Web UI | Gradio 6.x | `python -m weight_stream ui` |
| 3 | TUI | Textual 8.x | `python -m weight_stream tui` |
| 4 | API Docs | Swagger | `http://localhost:8765/docs` |
| 5 | Marketing Site | Static HTML (5 pages) | `website/index.html` |

#### Bug Fixes
- Server startup: factory=True tuple bug fixed
- Port: default 8080 → 8765 (checked free on this machine)
- Gradio 6.x API: theme/css migrated to launch()
- Exception ** unpacking bug in ModelError/GenerationError fixed

#### Documentation
- `docs/FULL_PLATFORM_ARCHITECTURE.md` — 12-chapter platform architecture
- `docs/IDE_INTEGRATION.md` — 9 IDE/tool config examples
- `website/` — 5-page marketing site (landing, features, architecture, benchmarks, api-docs)

#### Testing
- 43 unit tests pass, 7 server e2e tests
- Anthropic endpoint: 3/3 scenarios verified

#### Security
- GitHub token removed from remote URL
- .gitignore hardened
- All mmap: ACCESS_READ only

#### Files (Phase 6)
- `weight_stream/server/` — 8 files (API server)
- `weight_stream/ui/gradio_app.py` — Gradio UI
- `weight_stream/tui/app.py` — Textual TUI
- `weight_stream/server/static/index.html` — SPA
- `weight_stream/server/anthropic_compat.py` — Anthropic compat
- `weight_stream/backends/_base.py` — abstract backend
- `weight_stream/core/exceptions.py` — 6 exception types
- `weight_stream/cli/main.py` — polished (5 commands)
- `website/` — 7 files (marketing site)
- `docs/FULL_PLATFORM_ARCHITECTURE.md`
- `docs/IDE_INTEGRATION.md`
- `README.md`
- `pyproject.toml` — v0.11.0
- `tests/test_backend.py`, `tests/test_exceptions.py`, `tests/test_server.py`

---

## [0.10.0] - 2026-07-27

### 🔬 Phase 4a: GGUF Parser — Expert-Aware Tensor Mapping

- **New Module**: `weight_stream/gguf/` — wraps official `gguf` library with expert-aware features
- **GGUFParser**: Parses GGUF metadata + maps tensor names → file offsets
- **Expert-aware API**:
  - `get_expert_map()` → `{layer_id: {expert_idx: [ExpertRange(gate, up, down)]}}`
  - `get_expert_tensors()` → list of 72 expert tensors (24 layers × 3 projections)
  - `get_tensor(name)` → file offset + size + quantization type
- **Expert size analysis (Qwen1.5-MoE-A2.7B)**:
  - Per-expert: down=1.43MB, gate=0.77MB, up=0.77MB (total ~2.9MB/expert)
  - Layer-0 prefetch: loads all 60 experts on init (cold start acceleration)
- **Backend update**: `WeightStreamModel` uses GGUF parser + prefetches layer experts during generation
- **Prefetcher update**: New `prefetch_experts()` and `prefetch_token_experts()` methods
- **Tests**: 9 new GGUF parser tests (22 total, all passing)

#### ไฟล์ที่สร้าง/แก้ไข
- `weight_stream/gguf/__init__.py` — new module
- `weight_stream/gguf/parser.py` — GGUF parser wrapper (135 lines)
- `weight_stream/backends/llama_cpp.py` — GGUF integration + expert prefetch + page monitor init
- `weight_stream/core/prefetcher.py` — expert-aware prefetch methods + buffer tracking
- `tests/test_gguf.py` — 9 tests
- `CHANGELOG.md` — อัปเดต

---

## [0.10.1] - 2026-07-27

### 🔬 Phase 4b: Windows Page Cache Monitor + Buffer Integration

- **New Module**: `weight_stream/io/win_perf.py` — WindowsPageMonitor using `QueryWorkingSetEx`
  - Samples page cache residency via `QueryWorkingSetEx` API
  - Reports resident ratio: how much of the mmap'd file is in physical RAM
  - Page size detection via `GetSystemInfo`
- **Backend fix**: `WeightStreamModel` now initializes page monitor on startup
  - Uses numpy to extract mmap virtual address for `QueryWorkingSetEx`
  - Monitor is optional — gracefully reports `None` on failure
  - Samples page cache every 5 tokens during generation
- **Prefetcher fix**: `prefetch_experts()` now tracks prefetched shards in the buffer LRU
  - Previously, expert prefetch used direct mmap reads without buffer tracking
  - Now shards are properly tracked: buffer shows 66 prefetches, 16 entries after 10-token gen
- **Cleanup fix**: `WeightStreamModel.close()` releases numpy buffer before closing mmap
- **Benchmark validation** (Qwen1.5-MoE-A2.7B, 5.5GB):
  - Page monitor confirms: 0% → 1.6% resident after cold generation
  - With/without prefetch: within noise (±3%) for small model
  - Prediction: prefetch benefit scales with model size (>68GB needed for visible effect)
- **Tests**: 22/22 passing (no new tests needed — monitor is optional and graceful)

#### ไฟล์ที่สร้าง/แก้ไข
- `weight_stream/io/win_perf.py` — WindowsPageMonitor (new, 189 lines)
- `weight_stream/backends/llama_cpp.py` — page monitor init + close fix
- `weight_stream/core/prefetcher.py` — buffer tracking in prefetch_experts
- `CHANGELOG.md` — อัปเดต

---

## [0.11.0] - 2026-07-27

### 🏭 Phase 6: Production Hardening — Full End-to-End Readiness

> "ปราการด่านสุดท้าย ก่อนก้าวขึ้นเป็น Product end-to-end เต็มตัว"

ครอบคลุม 8 มิติของ Production Readiness:

#### 1. 🔒 Security
- **GitHub token removed** จาก remote URL (เดิมแปะ ghp_ ใน `.git/config`)
- Scan git history: **no secrets found** in any committed file
- **Safe mmap**: `ACCESS_READ` ตลอด (ไม่มีการเปิดเขียน)
- **`.gitignore` อัปเดต**: เพิ่ม `credentials*`, `secrets*`, `tokens*`, `*.pem`, `*.key`, `.idea/`, `.vscode/`
- **Path validation**: model path ถูกตรวจสอบก่อนเปิดไฟล์
- **No eval/exec/subprocess**: zero remote code execution surface

#### 2. 🏗️ Architecture
- **New**: `backends/_base.py` — abstract base class `WeightStreamBackend`
  - `generate()`, `close()`, `get_stats()` as abstract methods
  - Context manager protocol (`__enter__`/`__exit__`)
  - `model_path`, `is_loaded` properties
- **`WeightStreamModel` inherits** from `WeightStreamBackend`
- **`backends/__init__.py` exports**: `WeightStreamBackend`, `WeightStreamModel`
- **`weight_stream/__init__.py` exports**: exceptions, version sync

#### 3. 🛡️ Error Handling
- **New**: `core/exceptions.py` — exception hierarchy
  - `WeightStreamError` (base) → `ModelError`, `BufferError`, `PrefetchError`, `GenerationError`, `ConfigError`
  - Each exception carries structured `details` dict
- **Model loading**: wrapped with `ModelError` (file not found, mmap fail, GGUF parse fail, llama-cpp load fail)
- **Generation**: wrapped with `GenerationError` (engine errors, stream failures)
- **Parameter validation**: `ConfigError` for `buffer_mb < 1`, `n_ctx < 8`
- **Close idempotent**: `close()` safe to call multiple times, guards all cleanup

#### 4. 📊 Logging
- Log format: `"%(levelname)s: %(message)s"` (clean, readable)
- Appropriate levels: DEBUG for internals, INFO for milestones, WARNING for degradation
- Page monitor: graceful WARNING instead of stack trace on init failure
- `force=True` in `logging.basicConfig` for CLI compatibility

#### 5. 🖥️ CLI Polish
- **`--version`** flag added
- **`-p`/`-n`/`-b`/`-t`/`-v`/`-j`** short aliases for all options
- **Parameter validation**: buffer_mb ≥ 1, max_tokens ≥ 1, temperature 0-2
- **Error display**: `ModelError` → clean "Error: ..." to stderr, exit code 1
- **Stats table**: pretty-printed with consistent indentation
- **Hit rate note**: explains why hit rate is 0% (opaque expert routing)
- **Stats command enhanced**: shows shards, mode, estimated tokens, run command example
- **Benchmark**: shows elapsed, tokens, tok/s + stats table
- **JSON output**: all commands support `--json` for machine parsing

#### 6. 🧪 Testing (43 tests, 3 test files)
- **New**: `tests/test_backend.py` (13 tests)
  - Interface contract: ABC cannot instantiate, properties work
  - Error paths: file not found, empty file, invalid params
  - Integration (Qwen model): load, generate, context manager, close-twice, generate-after-close
  - Stats structure validation
- **New**: `tests/test_exceptions.py` (8 tests)
  - All exception types: base, model, generation, config
  - Hierarchy: all subclasses of WeightStreamError
  - String representation with details
  - Edge cases: no model_path, no token_count, empty details
- **All 43 tests pass** (was 22 before Phase 6)

#### 7. 📖 Documentation
- **New**: `README.md` — full product documentation
  - How it works (5 steps)
  - Quick start (pip install + CLI commands)
  - Python API reference with examples
  - CLI reference (all commands + options)
  - Architecture diagram
  - Requirements + supported models
- **Inline docstrings**: all public methods documented

#### 8. 📦 Packaging
- **pyproject.toml**: version 0.10.1, classifiers (7 categories), keywords
- **`__version__`**: synced to 0.10.1 in both `__init__.py` and `pyproject.toml`
- **URLs**: homepage, source, documentation, issues
- **Dependencies**: `numpy>=1.24`, optional `llama-cpp-python>=0.3.0`

#### ไฟล์ที่สร้าง/แก้ไข
- `weight_stream/backends/_base.py` — abstract base class (new)
- `weight_stream/backends/__init__.py` — exports base + model (updated)
- `weight_stream/core/exceptions.py` — exception hierarchy (new)
- `weight_stream/core/llama_cpp.py` — inherits base, error handling, close idempotent (updated)
- `weight_stream/cli/main.py` — polished CLI (rewritten)
- `weight_stream/__init__.py` — exports + version sync (updated)
- `tests/test_backend.py` — 13 new tests (new)
- `tests/test_exceptions.py` — 8 new tests (new)
- `README.md` — full documentation (new)
- `pyproject.toml` — classifiers, keywords, version (updated)
- `.gitignore` — security entries added (updated)
- `CHANGELOG.md` — อัปเดต

---

## [0.9.0] - 2026-07-27

### 🏗️ Phase 3c: weight-streaming Product (MVP)

- **New Package**: `weight_stream/` — 8 modules, pip-installable product
- **core/buffer.py**: LRU StreamingBuffer — zero-copy mmap, hot-set tracker, hit/miss stats
- **core/predictor.py**: HeuristicPredictor — sequential pattern + co-occurrence, no MLP
- **core/prefetcher.py**: Background thread — speculative prefetch during compute time
- **backends/llama_cpp.py**: WeightStreamModel — wraps llama-cpp-python with mmap overlay
- **cli/main.py**: 3 commands (`run`, `stats`, `benchmark`) + JSON output
- **tests/test_buffer.py**: 13 unit tests — LRU eviction, prefetch, hit rate, zero-copy
- **ADR-003**: Product architecture decision (LRU-only, 64MB, heuristic, mmap-based)
- **End-to-end validation**: Qwen1.5-MoE-A2.7B generates at 13.43 tok/s

#### ไฟล์ที่สร้าง/แก้ไข
- `weight_stream/` — new package (11 files)
- `weight_stream/__init__.py` — public API
- `weight_stream/__main__.py` — `python -m` entry
- `weight_stream/core/buffer.py` — LRU buffer tracker
- `weight_stream/core/predictor.py` — heuristic predictor
- `weight_stream/core/prefetcher.py` — background prefetch
- `weight_stream/backends/llama_cpp.py` — llama-cpp-python adapter
- `weight_stream/cli/main.py` — 3 CLI commands
- `weight_stream/io/__init__.py` — I/O abstraction stub
- `tests/test_buffer.py` — 13 unit tests
- `pyproject.toml` — package config
- `docs/DECISIONS.md` — ADR-003 added
- `SESSION_LOG.md` — เพิ่ม S008
- `CHANGELOG.md` — อัปเดต

---

## [0.5.0] - 2026-07-27

### 🧪 Phase 3a: Prototype Simulator

- สร้าง Python simulator framework ครบ 5 modules:
  - `access_pattern.py` — synthetic K3 workload generator (Zipf + temporal)
  - `buffer.py` — cache policy simulation (LRU, LFU, LRU+priority)
  - `predictor.py` — perfect + heuristic prediction models
  - `timing.py` — NVMe I/O + compute timing model
  - `run.py` — main simulation runner + sweeps
- EXP-001: Buffer size sweep (5 sizes × 3 policies) → **LFU 512 MB = 78.2% hit rate**
- EXP-003: Timing analysis → **76.7% overlap efficiency, 2.74 tok/s**
- Findings ที่กระทบ design:
  - ต้องเพิ่ม buffer default จาก 256 MB → **512 MB**
  - เปลี่ยน eviction policy จาก LRU+priority → **LFU**
  - Priority boost ปิด จนกว่า predictor accuracy >30%
  - Predictor accuracy = leverage ที่ใหญ่ที่สุดสำหรับ performance improvement

#### ไฟล์ที่สร้าง/แก้ไข
- `simulator/README.md` — document
- `simulator/config.py` — config dataclasses
- `simulator/access_pattern.py` — workload generator
- `simulator/buffer.py` — buffer simulation
- `simulator/predictor.py` — predictor models
- `simulator/timing.py` — I/O + compute timing
- `simulator/run.py` — main runner
- `research/experiments/EXP-001-buffer-sim/` — setup, results, analysis
- `research/experiments/EXP-002-predictor-sim/` — partial setup
- `research/experiments/EXP-003-timing-sim/` — setup, analysis
- `research/experiments/index.md` — อัปเดต
- `TASKS.md` — อัปเดต
- `SESSION_LOG.md` — เพิ่ม S004

---

## [0.6.0] - 2026-07-27

### 🔬 EXP-002: Predictor Accuracy Sweep

- **Key Findings (เปลี่ยน Architecture Design อย่างมีนัยสำคัญ):**
  - LFU hit rate = 76.2% flat ทุกระดับ accuracy → LFU ไม่ใช้ prediction
  - LRU+priority hit rate แย่ลงเมื่อ accuracy สูงขึ้น → "priority clogging" (29.9% → 15.5%)
  - Throughput flat = 2.73 t/s → compute (350ms/token) ครอบงำ I/O
  - Overlap ดีขึ้น 7.6x (30.9ms → 233.8ms) แต่ไม่ช่วย throughput
- **Design Updates:**
  - predictor accuracy ไม่ critical — heuristic ก็พอ
  - priority boost → OFF for LFU
  - LFU → default eviction policy
  - Weight streaming ≈ RAM reduction tool ไม่ใช่ throughput accelerator
- **New Simulator Capabilities:**
  - shared_experts_per_token mode (K3 realistic, 72/80 layers identical)
  - simulated_accuracy mode (inject controlled prediction errors)
  - timing predictor_confidence affects overlap efficiency
  - sweep-accuracy mode (9 accuracies x 2 policies)

#### ไฟล์ที่สร้าง/แก้ไข
- `simulator/config.py` — shared_experts_per_token, accuracy_level, n_predict=64
- `simulator/access_pattern.py` — shared mode + inter_layer_similarity
- `simulator/predictor.py` — simulated_accuracy predictor
- `simulator/timing.py` — overlap_efficiency = confidence
- `simulator/run.py` — sweep-accuracy
- `research/experiments/EXP-002-predictor-sim/results.md`
- `research/experiments/EXP-002-predictor-sim/analysis.md`
- `research/experiments/index.md` — อัปเดต
- `TASKS.md` — อัปเดต
- `SESSION_LOG.md` — เพิ่ม S005
- `CHANGELOG.md` — อัปเดต

---

## [0.7.0] - 2026-07-27

### 💻 Phase 3b: Real Hardware Benchmark (EXP-004)

- **Key Finding: SYSTEM IS I/O-BOUND (flips previous conclusions)**
  - Qwen1.5-MoE-A2.7B benchmark: 44ms/token, 22.7 tok/s (CPU, 2.7B active params)
  - K3 scaling: estimated 815ms/token compute vs 1786ms NVMe full load
  - **NVMe I/O IS the bottleneck** — buffer and predictor now CRITICAL for throughput
- **Simulator Timing Update:**
  - compute_time_per_token_us: 350,000 → **815,000** (2.3x increase)
  - Bottleneck: compute-bound → **I/O-bound**
- **Design Reversal (based on real data vs simulation):**
  - EXP-002 said predictor doesn't matter — WRONG for real hardware
  - EXP-001/002 conclusions only valid for compute-bound regime
  - I/O-bound regime: predictor accuracy, buffer hit rate, priority boost ALL matter

#### ไฟล์ที่สร้าง/แก้ไข
- `research/models/Qwen1.5-MoE-A2.7B_Q2_k.gguf` — downloaded model (5.88 GB)
- `research/experiments/EXP-004-benchmark/setup.md`
- `research/experiments/EXP-004-benchmark/results.md`
- `research/experiments/EXP-004-benchmark/analysis.md`
- `research/experiments/EXP-004-benchmark/results.json`
- `research/experiments/index.md` — อัปเดต
- `TASKS.md` — อัปเดต
- `SESSION_LOG.md` — เพิ่ม S006
- `CHANGELOG.md` — อัปเดต

---

## [0.8.0] - 2026-07-27

### 🔄 Simulator Update + Re-run (EXP-001/002 v2 with Real Timing)

- **Updated `config.py` timing**: `compute_time_per_token_us`: 350,000 → **815,000** (from EXP-004 real HW benchmark)
- **Re-run EXP-001 (buffer sweep): LRU beats LFU** for shared MoE access pattern
  - LRU 64 MB → 93.8% hit rate (vs LFU 27.2% at same size!)
  - LRU 512 MB → 98.9% hit rate, 1ms stall, 1.23 t/s
  - Shared access pattern (72/80 identical layers) creates extreme temporal locality → LRU dominates
- **Re-run EXP-002 (accuracy sweep):** conclusions unchanged — LFU flat, LRU+P clogging
- **Definitive Bottleneck Analysis:**
  - Compute: 815ms/token (92% of total time)
  - I/O stall range: 0-67ms (0-8% of total time)
  - **System is ~92% compute-bound** → buffer enables inference, not throughput
- **Design Corrections (vs v0.7.0 I/O-BOUND claim):**
  - v0.7.0 said "I/O-BOUND" — CORRECTED: system is compute-bound
  - Initial NVMe estimate (1786ms) was misleading — real I/O is only 67ms stall
  - Predictor/buffer/priority boost do NOT critically affect throughput
  - Their real value: enabling 1.4TB model on 64MB RAM

#### ไฟล์ที่สร้าง/แก้ไข
- `simulator/config.py` — timing 815000us (from EXP-004)
- `simulator/run.py` — sweep-buffer now shows t/s + stall
- `research/experiments/index.md` — อัปเดต v2 findings
- `TASKS.md` — อัปเดต
- `SESSION_LOG.md` — เพิ่ม S007
- `CHANGELOG.md` — อัปเดต

---

### 🏗️ Phase 2: Architecture Design Complete

- ออกแบบระบบ Speculative Weight Streaming ทั้ง 6 components + interface contracts
- สร้าง `docs/ARCHITECTURE.md` — blueprint หลักของระบบ (286 บรรทัด)

#### Components ที่ออกแบบ

| Component | Design Decision | Key Spec |
|-----------|----------------|----------|
| **NVMe Data Layout** | Shard-based, popularity sorted, O(1) index | 4 MB shard, 3 regions (shared/routed/KV) |
| **Weight Predictor** | MLP (PreScope-style, 2-layer, 2M params) | Input 128-256 → Output 896, ~8 MB |
| **Pre-fetch Scheduler** | Priority queue + I/O batching + io_uring/IOCP | MAX_BATCH 64 MB, 3 priority levels |
| **Streaming Buffer** | LRU + priority eviction, 256 MB default | ~64 shards (K3), cold start strategy |
| **Execution Engine** | BufferReader + MmapFallback + ComputeOrch | Framework-agnostic interface |
| **Abstraction Layer** | Plugin architecture | MoE / Dense / Hybrid polymorphism |

#### ไฟล์ที่สร้าง/แก้ไข
- `docs/ARCHITECTURE.md` — เอกสารออกแบบระบบ (ใหม่)
- `TASKS.md` — อัปเดต Phase 2 → ✅ Complete
- `SESSION_LOG.md` — เพิ่ม S003
- `CHANGELOG.md` — ไฟล์นี้

---

## [0.2.0] - 2026-07-27

### 🔭 Phase 1: Research Review Complete

- **ขยายเป้าหมาย** — จาก K3 สู่โมเดลใหญ่ทุกรูปแบบ (MoE, Dense, Hybrid) แต่เริ่มที่ K3
- อัปเดต PROJECT.md และ CONCEPT.md ให้สะท้อนเป้าหมายที่กว้างขึ้น
- ค้นคว้างานวิจัย 4 หมวด + K3 architecture

#### หมวดวิจัยที่ค้นคว้า

| หมวด | # Papers | SOTA | Key Finding |
|------|---------|------|-------------|
| **Speculative Decoding** | 8 | EAGLE-3 (NeurIPS'25) | Draft head <5% params, 2-4x speedup, scaling law |
| **MoE Routing Prediction** | 10 | PreScope (2025) | Expert prediction >90% accuracy ด้วย MLP เล็ก |
| **Out-of-Core Execution** | 8 | flash-moe, llama.cpp | SSD streaming ใช้ได้จริง 1.9-4.4 tok/s แต่ยัง reactive |
| **Near-Storage Compute** | 5 | HILOS (ASPLOS'26) | ยังไม่成熟พอสำหรับ LLM — ควรรอ hardware |
| **Kimi K3 Architecture** | — | เปิด weights 27 ก.ค. 2026 | MXFP4, KDA, Quantile Balancing, 896 experts |

#### ไฟล์ที่สร้าง/แก้ไข
- `PROJECT.md` — ขยายเป้าหมาย + เพิ่ม Dense model case
- `docs/CONCEPT.md` — อัปเดตเป็น architecture-agnostic + เพิ่ม Dense case
- `research/index.md` — สรุปผลวิจัยรวม
- `research/speculative-decoding/README.md` — 8 papers
- `research/moe-routing/README.md` — 10 papers
- `research/out-of-core-execution/README.md` — 8 โครงการ
- `research/near-storage-compute/README.md` — 5 papers
- `research/kimi-k3/README.md` — K3 architecture deep dive
- `research/README.md` — อัปเดต

---

## [0.1.0] - 2026-07-27

### ✨ Initial Concept

- กำหนดแนวคิด **Speculative Weight Streaming** — รันโมเดล 2.8T+ บนเครื่องทั่วไป RAM 32–64 GB
- ออกแบบสถาปัตยกรรม 3-layer: Draft Model → Weight Predictor → Streaming Buffer
- วิเคราะห์ feasibility: bandwidth, latency, memory budget
- ระบุ novel contributions และ open problems
- บันทึกแนวทางเสริม: Computational Storage, Collaborative Inference, MoE Compression

#### ไฟล์ที่สร้าง
- `PROJECT.md` — ภาพรวมโครงการ
- `docs/CONCEPT.md` — Concept ฉบับสมบูรณ์
- `CHANGELOG.md` — ไฟล์นี้

---

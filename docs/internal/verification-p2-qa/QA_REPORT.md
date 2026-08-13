# P2 Independent QA Report — Weight Streaming Console

QA run: 2026-07-30 · worktree `~/worktrees/dashboard-theme/weight-streaming`
HEAD verified: `04363d7` (branch `feature/dashboard-theme`, tree clean before/after rebuild)
Server under test: `python -m weight_stream.server --port 8799` (worktree code) — **killed after QA; user's 8765 untouched (health 200 after my server was stopped).**

## VERDICT: FAIL — 1 blocking defect (Live Stats tok/s chart frozen). Everything else PASSES.

Dev's self-verification was largely accurate and honest; the blocking defect is in an area
Dev explicitly could not runtime-test (no model), and this box **did** have GGUFs available
(Jan store), so live verification was possible.

---

## 🛑 BLOCKING DEFECT #1 — Live Stats: tok/s session-window chart never renders data

- **File**: `frontend/src/pages/stats/StatsPage.tsx` (lines 63, 118, ~251)
- **Steps**:
  1. Have any loaded model with ≥1 completed generation (real, or `/v1/stats` mock with `generation.tokens_per_sec`)
  2. Open `#/stats`, stay ≥ 3 polls (6 s)
- **Expected** (spec §9.3): both charts (tok/s and faults-per-token) accumulate points from the client ring buffer and draw.
- **Actual**: faults chart grows correctly; **tok/s chart stays frozen at "1 point" + "waiting for first generation" overlay forever**, even though the ring buffer is full.
- **Objective evidence**:
  - Array-level probe (hooked `Array.prototype.push` on the ring's buffer): tok ring held **60 points** cycling exactly through the per-poll values (32.5/35/37.5/40/30…), while its `.spark__count` text read "1 point". Faults ring and display agreed (59–198 pts).
  - Reproduced on **real telemetry** (live qwen3.5 4B Q4_K model): faults chart "10 points", tok chart "1 point" — screenshot `05-stats-real-data-th.png` / `03-stats-tok-chart-frozen-aurora-dark.png`.
  - Theme toggle (forces Sparkline re-render via its theme signal) did NOT fix it → component is never re-executed with fresh data.
- **Root cause**: `RingBuffer.items()` returns the *same mutated array* every render, and the tok Sparkline's props are all referentially stable (`data` same ref, `unit`/`cssVar` string literals, default `format`). Under the `@preact/preset-vite` signals fine-grained transform the subtree is never re-diffed → Sparkline never re-renders after its first paint. The faults chart survives only accidentally — its `format={(n) => …}` closure + conditional `unit` expression produce fresh props each render.
  - The intended fix is half-written: `ringTick` signal is created (line 63, "bump to redraw charts") and bumped each poll (line 118) but **never subscribed** — compare ChatPage.tsx:299 `void msgTick.value // subscribe → repaint while streaming`.
- **Suggested fix**: read `void ringTick.value` in the StatsPage render body (mirror ChatPage), and/or pass `data={tokRing.current.items().slice()}` (fresh ref) to both Sparklines.
- **Severity**: blocking — one of the two §9.3 deliverables is dead-on-arrival for every real user; it just never surfaces in a no-model environment (which is why self-verify missed it).

## ⚠️ DEFECT #2 (non-blocking) — per-message tok/s footer never populates

- **File**: `frontend/src/pages/chat/ChatPage.tsx:258` (`fetchStats(c.model, 5000)`) + pre-existing server quirk in `weight_stream/server/api_server.py:178`
- **Steps**: load a model, generate, let it finish.
- **Expected** (spec §9.2): footer "▲ X tok/s · N tokens" (real values from `/v1/stats`).
- **Actual**: footer is always empty, even when the server has real numbers (live run: 3.9 tok/s / 53 tokens present in `/v1/stats`, footer stayed null).
- **Cause**: `GET /v1/stats?model=X` returns `{"models": {…stat fields…}}` (stat dict directly under `models`, verified: keys `['buffer','predictor','prefetcher','generation','page_cache','model']`) — the frontend expects `{models: {id: stats}}`, so `s.models[c.model]` is always undefined. StatsPage avoids this by calling without `?model=`. Honest (never fakes), but the feature is dead. Fix frontend-side: call `fetchStats()` and index by own model id.

---

## Gate-by-gate

### A. XSS / mXSS — **PASS**
- **Saved-conversation battery** (25 distinct `window.__xss_pwned_*` markers through the real `renderMarkdown` pipeline: script, img onerror, svg onload + animate, math-namespace mXSS, `javascript:` (incl. mixed case), iframe/object/embed, base64 `data:` anchors, noscript breakout, body/input/details handlers, style attr, markdown `[]()` js link, code-fence attribute breakout, `<think>`-internal payloads, user-message payloads): **0 markers fired; 0** script/iframe/object/embed/svg/math/noscript/img/input/style/form elements in `.msg__md`; **0** `on*` attributes; **0** `javascript:`/`data:` hrefs; `img` removed entirely (FORBID_TAGS verified in `src/core/markdown.ts:93`). Safe https links kept `target=_blank rel="noopener noreferrer"` (both markdown-authored and raw-HTML-authored via the DOMPurify hook). `<think>` accordion content sanitized (`<p><a>t</a></p>`, js href stripped).
- **Live stream-order / mXSS** (mocked SSE with payloads split mid-tag: `<scr|ipt>`, `<img sr|c…>`, `javascr|ipt:`, `<svg onlo|ad…>`, and a `<thi|nk>…</thi|nk>` block split across 3 chunks): **22 mid-stream DOM samples at 150 ms — every frame 0 dangerous elements, 0 `javascript:` hrefs, 0 markers fired.** Split `<think>` reassembled correctly; think-internal script stripped. Pipeline sanitizes the cumulative text per render (RichText → renderMarkdown on `main`/`partial`/`thinks`), so per-chunk reassembly cannot bypass DOMPurify. `<thi`/`</th` hold-back (`thinks.ts`) works.
- **Benign markdown renders correctly** (the hostile-battery adjacency swallowed some safe blocks — that's marked's raw-HTML-block semantics, not a security issue): clean message gave highlighted python (`hljs-keyword/title/number` spans), lang label, working Copy button ("Copied ✓"), lists, table, inline code, h1, safe link with noopener.
- **No unsanitized innerHTML path**: every `dangerouslySetInnerHTML` in `src/pages` goes through `renderMarkdown()` (grep-verified).
- Console stayed **0 errors / 0 warnings** through the whole battery (forbidding `img` removes the broken-image noise — Dev's claim confirmed).

### B. Honest-telemetry audit — **PASS**
- `grep Math.random|faker|synthetic src/` → only ParticleCanvas (decorative) + conversation-id generation. No fabricated metrics anywhere.
- Overview Activity: honest empty "Recording starts after your next generation / …usage history arrives in phase 4…" (EN+TH) — verified live; tooltip cites missing `/v1/usage/history` (P4).
- Charts labelled "session window · since opening this page" (client ring buffer, `ring.ts` cap 300) — no persistent-history claim.
- Buffer hit rate: **real 0%** from live run with ADR-003 caveat rendered verbatim ("Real value — always 0% in practice: llama.cpp reads its own mmap…"), not dressed up.
- Agent-mode + reasoning-effort tooltips truthful in both languages ("server does not execute tools", "sent as reasoning_effort but not applied — no effect on generation").
- Missing data → `n/a` everywhere verified live: prefetch "n/a · no prefetches", residency "n/a · not Windows" (empty page_cache) vs distinct "No model loaded", hard faults "n/a · estimated via residency" on real Windows run, uptime labelled client-measured with tooltip.
- Overview uptime/priority/server-block values are real server values (e.g. real `SetPriorityClass(BELOW_NORMAL_PRIORITY_CLASS) · win32`).

### C. Live Stats — **FAIL (tok chart, defect #1); all other items PASS**
- Polls `/v1/stats` every 2 s (network + server access log) ✓; **visibility-aware**: emulated `visibilitychange` hidden → **zero polls in 16 s**, restored → immediate jittered catch-up + resumed cadence ✓; backoff logic in `poll.ts` reviewed ✓.
- Idle state before first generation ("No generation yet" per-gauge + idle banner + Go-to-Chat) ✓ (mock + code path).
- Gauge deltas vs previous poll: **verified live** — tok/s 19.9→12.3 produced "↓ −7.6 tok/s" for exactly one poll window, then settled to 0 ✓.
- MoE heatmap degrade: `n_experts=0` → designed "not MoE — dense model" card (mock **and** real qwen3.5 dense run) ✓; MoE grid path renders when n_experts>0 (mock 64 cells, firing status line from real `active_experts` only — honest dark grid otherwise).
- Paging detail: real run showed faults 2,249 / 28.1 per token / hard faults `n/a` (Windows) / disk demand with "Windows residency estimate" source badge + real server note ✓; platform n/a path verified with empty page_cache mock ✓.
- Server block: real models_loaded/max (1/4), host:port, priority badge, queue ✓.

### D. Models — **PASS**
- All six endpoints exist server-side (`api_server.py`: `/v1/models` L187, `/v1/browse` L229, `/v1/browse-dir` L240, `/v1/models/scan` L247, `/v1/models/load` L359 (with `force` → unload-then-load L367), `/v1/models/unload` L388).
- **Live end-to-end on this box** (Jan store has GGUFs): default scan found **18 real models** with correct arch/quant-from-tensor-types/size cards; `may_need_upgrade` warning + `pip install -U llama-cpp-python` hint rendered on 3 cards; quant advisories verified live: F16 → warning banner, Q2_K → "echo/garble → use ≥Q4_K_M" caution, Q4_K_M → none; empty-dir scan → honest empty state.
- Loaded a real 2.52 GB Q4_K model via the UI: progress dialog → success toast with "open chat" action → loaded card (arch/quant/buffer/last_used/actions). **Reload(force)**: confirm dialog with honest copy (in-flight requests fail; buffer kept; context reset because server doesn't expose n_ctx) → real forced reload succeeded. **Unload**: confirm dialog + session-remember checkbox (persisted to sessionStorage, honored on next unload) → real unload; copy states "file remains on disk". Server confirmed empty afterwards (`/v1/models` = []).
- No file deletion anywhere in the console flows (grep: only benchmark tool's own temp files + tests). Native Browse buttons deliberately NOT clicked (they pop a real GUI dialog on the host) — endpoints verified by code.

### E. i18n + native Thai — **PASS**
- `npm run i18n:verify` → **✓ PASS — 310 keys, key parity + placeholders OK · 8 long** (1 warning group).
- The 8 >45%-longer strings (EN≥8 chars): `chat:drawer.maxTokens`, `common:copied`, `nav:openIssues_one/other`, `overview:hero.uptime`, `overview:widgets.issues.title`, `stats:gauge.hitRate`, `stats:paging.disk`. **All fit at 412 px** — no clipping measured (scrollWidth ≤ clientWidth on gauge labels, caveat, paging dts, window labels, hero uptime, widget titles) — screenshot `06-stats-412-th-fit.png`.
- Native read (TH): natural product Thai throughout, glossary-consistent (โมเดล/โหลด/ปลดโหลด/บัฟเฟอร์/สแกน/อัตราการฮิต/ฟอลต์/เรซิเดนซี/ช่วงเซสชัน per `translation-kit/batch-2/GLOSSARY.md`); no chat slang; honest tooltips read well ("หมายเหตุตรงๆ: …ไม่มีการกระทำใดทำงานจริง"). Minor phrasing notes below (non-blocking).
- No raw keys leaked (regex sweep EN+TH pages). EN spot-check: natural, honest copies; placeholders intact.

### F. P1 keep-green regression — **PASS**
- **Reproducible build**: `git status` clean before; `npm run build` → **still clean** (committed dist byte-identical to rebuild). Built sizes: JS 286.81 kB / **92.67 kB gzip**, CSS 58.85 kB / **10.86 kB gzip** (≈103.5 kB gzip total, within ~150 kB budget).
- **Legacy `/app` untouched**: `git diff main -- weight_stream/server/static/index.html` empty; `/` → **302 → /app/**; `/app/` → **200**, old SPA intact ("AI Workspace 2.0", Chat 2.0/Stats/Models/Issues).
- **No CDN at runtime**: grep of built `console/` + index.html for `fonts.googleapis|gstatic|jsdelivr|unpkg|cdnjs|cdn.` → **zero hits** (fonts self-hosted woff2 assets).
- **Theme fidelity**: classic-dark body bg computed **rgb(11, 15, 25) = #0b0f19** ✓, radii **6px/10px** ✓; aurora-dark particles **ON and animating** (canvas alpha: 1,341→1,489 lit px over 1 s, aria-hidden); aurora-light particles ON (2,567→2,759 px); **`prefers-reduced-motion: reduce` → particles OFF** (0 px, emulated via Playwright); classic-dark → no particles (registry `none`).
- **Responsive**: 1440 → 260px sidebar; **1200 → 64px rail**; **900 → burger + aria-modal drawer (10 nav items), Esc closes**; **412 → bottom nav (46px items ≥44)**, no horizontal overflow on all four pages, chat full-screen composer, long TH strings fit. Touch targets: bottom-nav ≥44 ✓; shell icon buttons (34 px) and quick-action buttons (37 px) are below 44 — pre-existing P1 shell styling accepted at P1 sign-off (non-blocking note).
- **Command palette**: Ctrl+K ✓ and `/` ✓ open (role=dialog, listbox, 16 options); fuzzy TH search + ArrowDown + Enter **navigated to #/stats**; Esc closes; repeatable.
- **Drawer/Dialog a11y (P1 fix, 5e2aeb3)**: ParamDrawer `role=dialog aria-modal=true`; **focus trap 30/30 Tab+Shift-Tab frames stayed inside**; **Esc closes and focus restored to the exact trigger** (aria-label "พารามิเตอร์"); body scroll locked during open.
- **Console**: **0 errors / 0 warnings** on genuine loads across classic-dark/aurora-dark/aurora-light × TH/EN (sweep over overview→stats→chat). The only error seen in the whole session was a pre-existing `favicon.ico 404` on the legacy `/app` (not P2).
- **pytest**: `98 passed, 6 skipped, 9 warnings, 9 errors in 22.29s` — **identical to baseline**; all 9 errors = `tests/test_gguf.py` FileNotFoundError (missing GGUF fixture, pre-existing).

---

## Non-blocking observations
1. **Defect #2 above** (tok/s footer dead due to `?model=` stats shape) — honest but non-functional.
2. **Dev's VERIFICATION.md size numbers are stale**: claims JS 277.99 kB / 88.92 kB gzip; actual committed+rebuilt = 286.81 kB / 92.67 kB gzip (Thai batch + rebuild). Within budget; doc accuracy only.
3. EN unit inconsistency (known): overview `faults/token` vs stats `faults/tok` (`locales/en/overview.json:37` / `stats.json:27`). TH is consistent (ฟอลต์/โทเคน vs ฟอลต์/tok mirrors EN per page).
4. Scan late-response race: two overlapping scans — the earlier (slow) response can overwrite the later scan's results (observed: Jan results rendered under a `~/models` dir input). `runScan` has no request-sequence guard.
5. Mobile touch targets <44px: P1 shell `icon-btn` (34px), `btn--md` quick actions (37px), `tip__trigger` (17px) — pre-existing, accepted at P1.
6. TH phrasing suggestions (optional polish): "อัตราการฮิตของบัฟเฟอร์" is glossary-locked but "ฮิต" transliteration reads slightly informal — consider "อัตรา命中" no — keep per glossary; `stats.idle.body` "ตัวนับ paging เริ่มจากศูนย์" is fine; `models.scan.tip` "การแยกส่วน header" → "การอ่านส่วนหัว GGUF" would read smoother; `overview.hero.uptimeTip` "เชื่อมติด" → "เชื่อมต่อ". None wrong, all understandable.
7. Heatmap tooltip (TH) is a 4-clause run-on; readable but long for a tooltip.

## Not runtime-testable on a no-model box — but this box HAD models, so most were tested live
| Item | How verified |
|---|---|
| Live SSE streaming + rAF batching | **Runtime (real model)** — qwen3.5 4B Q4_K streamed token-by-token |
| Stop-keeps-partial | **Runtime** — abort-aware stream: partial "alpha beta" retained + "stopped" badge + send restored (note: a synthetic stream that ignores AbortSignal will NOT stop — that's a harness artifact, not the app; real network SSE aborts correctly) |
| tok/s footer | Runtime attempt → exposed defect #2 |
| Desktop notification >20s | Code review only (`ChatPage.tsx:272`: >20s + `document.hidden` + granted; permission ask once, non-intrusive) — not triggered in-session |
| Load/unload/reload(force)/scan | **Runtime (real)** |
| Gauge deltas / charts with real data | **Runtime** (exposed defect #1) |
| `may_need_upgrade` | **Runtime** (3 real warnings) |

## Evidence
Screenshots in this directory: `01-overview-th-classic-dark.png`, `02-stats-idle-dense-mock-th.png`, `03-stats-tok-chart-frozen-aurora-dark.png` (defect #1), `04-models-scan-results-th.png`, `05-stats-real-data-th.png` (defect #1 with real telemetry), `06-stats-412-th-fit.png`, `07-legacy-app-untouched.png`.

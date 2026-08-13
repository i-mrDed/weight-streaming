# P2 Dev self-verification — Weight Streaming Console

Run: 2026-07-30 · worktree `~/worktrees/dashboard-theme/weight-streaming`
Server under test: `python -m weight_stream.server --port 8799` (worktree code, no models loaded).

## Gates

| Gate | Result |
|---|---|
| `npm run typecheck` | ✓ clean |
| `npm run build` | ✓ JS 277.99 kB / **88.92 kB gzip**, CSS 58.85 kB / **10.86 kB gzip** (≈ 99.8 kB gzip total, fonts unchanged; budget ~150 kB) |
| `npm run i18n:verify` | ✓ PASS — 310 keys, key parity + placeholders OK (3 length warnings only; `th` mirrors `en` until the translator agent runs) |
| `pytest tests/ -q` | 98 passed / 6 skipped / 9 errors — **identical to baseline** (the 9 errors are the pre-existing missing-GGUF-fixture FileNotFoundErrors) |
| Console errors/warnings | 0 on a fresh session across all pages (the only content-induced noise — a broken `<img src=x>` from an injected XSS payload — was eliminated by forbidding `img` in the sanitizer) |

## Browser self-check (Playwright, real Chromium)

Pages visited: Overview, Chat, Live Stats, Models (+ Issues/Hub/Docs/Settings remain honest placeholders).

- **Themes**: verified visually + via `data-theme` attribute in `classic-dark`, `aurora-dark`, `aurora-light`. All page styles reference semantic tokens only.
- **Locales**: TH (navigator default) and EN (`?locale=en`) both render; new namespaces
  (`overview`, `chat`, `stats`, `models`) resolve in both; no raw keys leaked.
- **Honest empty / idle states** (server with zero loaded models):
  - Overview: models empty state (Scan & load / Hub disabled "coming soon"), Activity =
    "Recording starts after your next generation" + P4 tooltip, Paging = "No generation yet",
    Residency = "No model loaded" (distinct from "n/a on this platform" when a model exists
    but the tracker is unsupported).
  - Stats: "No models loaded" → Go to Models; (with a model but no generation: idle banner +
    per-gauge "No generation yet" — code path present, not reachable without a GGUF).
  - Chat: no-model empty state in canvas + composer off-line; empty conversation sidebar.
  - Models: "Nothing loaded" card; scan results appear only after a real scan.

## XSS audit (spec §9.2 hard rule)

Injected a localStorage conversation (renders through the exact same
`marked → DOMPurify` pipeline as streamed model output) containing:

- `<img src=x onerror=…>` → img tag **removed entirely** (forbidden), no handler possible
- `<script>…</script>` → removed
- `<svg onload=…>` → removed (svg namespace not in the html profile)
- `<a href="javascript:…">` → href **stripped** (link kept, dead)
- `<iframe src="javascript:…">` → removed

Result: all five `window.__pwned*` markers stayed `undefined`; 0 script/iframe/svg/onerror
nodes in the DOM; safe `https:` link preserved with `target=_blank rel=noopener`.
Code block highlighted (hljs core build), copy button present and labelled per locale;
`<think>` accordion rendered collapsed with sanitized inner markdown; user messages also
render through the sanitizer.

Additional QA attack surface worth probing: very long tokens / partial `<think` tails during
streaming (hold-back logic in `src/pages/chat/thinks.ts`), markdown nesting, `data:` URIs,
and mutation-XSS vectors against DOMPurify.

## Not verifiable without a GGUF model on this box

Live SSE streaming + Stop-keeps-partial, desktop notification after >20 s, per-message
tok/s footer (needs `/v1/stats.generation`), scan/load/unload/reload flows, gauge deltas and
session-window charts with real data. These code paths are implemented and type-checked;
QA should run them against a real (small) quantized model.

## Screenshots

Captured during this session (Playwright MCP sandbox stored them outside this worktree, so
they are not committed): overview in classic-dark/aurora-dark/aurora-light (TH), all four
pages in aurora-light (TH), chat with the sanitized XSS conversation (EN). DOM assertions
above are the committed evidence.

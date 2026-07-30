# Translation Kit — Batch 1 (shell + navigation + theme + errors)

You are translating UI strings for **Weight Streaming Console**, a local-first
dashboard that manages a local LLM server. This is **batch 1** (app shell only —
navigation, theme/language switchers, command palette, boot splash, toasts,
error dialogs, page placeholders). Later batches cover chat/stats/models/etc.

## Your task
Translate every value in `en/*.json` into Thai and write the result to
`frontend/locales/th/<same filename>` (one file per namespace: common, nav,
errors, settings). **Do not read any file outside this `translation-kit/batch-1/`
directory.** Do not modify the EN files.

## Hard rules
1. **Keep every key.** No adding, no removing, no renaming keys. The key tree
   shape must match EN exactly.
2. **Preserve `{{placeholders}}` verbatim** — same names, same count, same
   braces. They are replaced at runtime (e.g. `{{host}}`, `{{count}}`, `{{page}}`,
   `{{version}}`, `{{name}}`, `{{status}}`, `{{phase}}`).
3. **Do NOT translate** (keep as-is in the Thai string): endpoint paths
   (`/v1/...`), code/commands (`python -m weight_stream server`), the brand
   `Weight Streaming`, `Console`, quant tags (`Q4_K_M`), key combos (`Ctrl+K`,
   `Ctrl K`), version/phase tokens (`P2`,`P3`,`P5`,`v{{version}}`), and theme
   proper names `Classic Dark` / `Aurora Dark` / `Aurora Light`.
4. Valid JSON, UTF-8, double quotes.

## Tone guide (Thai)
- Polite but **concise** — product UI copy, not a chat. Use ครับ/ค่ะ sparingly
  (OK in empty-state greetings; avoid in buttons, labels, and short status lines
  where brevity wins). No exclamation spam.
- UI labels should be **short** (Thai runs long — keep buttons ≤ ~14 chars where
  possible; the verifier only *warns* past EN+45%, but aim shorter).
- Second person neutral; no honorifics for the user.
- Punctuation: Thai has no spaces between words; keep spaces around Latin tokens
  and numbers (`โหลด โมเดล`, `v{{version}}`).

## Where each namespace appears (screen context)
- **common** — shared verbs/labels (buttons: retry/cancel/close/copy), the boot
  splash (`splash.*`: a branded loading screen that shows a *real* connection
  status), command palette (`palette.*`: a Ctrl+K search box), status dot
  (`health.*`), toasts (`toast.*`), accessibility labels (`a11y.*`), and the
  "page under construction" placeholder (`placeholder.*` — honest message that a
  page ships in a later build phase; `{{page}}` = the page name, `{{phase}}` = P2/P3/P5).
- **nav** — left sidebar + mobile bottom-nav item labels and the active-model
  chip. `{{count}}` in `modelsLoaded_*`/`openIssues_*` = a number; use the
  `_one`/`_other` plural forms (Thai uses the same word, that's fine — fill both).
- **errors** — generic error dialogs (`{{status}}` = an HTTP status code).
- **settings** — only the **Appearance** and **Language** sections ship in this
  batch (theme picker cards + descriptions, auto-mode, particle-background
  toggle, display-name field). The theme card names live under `theme.*`.

## Placeholders reference
- `{{host}}` = server host:port, e.g. `127.0.0.1:8765` (keep the value)
- `{{version}}` = server version number
- `{{count}}` = integer count
- `{{name}}` = a theme or language display name
- `{{page}}` = a translated page name (from nav.*)
- `{{phase}}` = build phase code (P2/P3/P5) — keep as-is
- `{{status}}` = HTTP status code (number)

Write the four Thai files, then stop. The build verifier checks key parity and
placeholder integrity automatically.

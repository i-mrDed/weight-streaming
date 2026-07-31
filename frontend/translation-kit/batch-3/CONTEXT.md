# Translation Kit — Batch 3 (P5: Hub page + Settings-server + Overview activity + Models library)

You are translating UI strings for **Weight Streaming Console**, a local-first
dashboard that manages a local LLM server. This is **batch 3 — the final full
TH sweep**: the brand-new Hub page, the now-live server config section of
Settings, the Overview activity feed, and the Models library view. Batches 1–2
are already translated; the glossary (`GLOSSARY.md`) is the locked single
source of truth — reuse those exact terms.

## Your task
Translate every value in `en/*.json` into Thai and write the result to
`frontend/locales/th/<same filename>` — ONE COMPLETE FILE PER NAMESPACE
(`hub.json` is new; `overview.json`, `settings.json`, `models.json` REPLACE
the existing Thai files in full). **Do not read any file outside this
`translation-kit/batch-3/` directory** (the glossary you need is included).
Do not modify the EN files.

## Hard rules
1. **Keep every key.** No adding, no removing, no renaming. The key tree shape
   must match EN exactly.
2. **Preserve `{{placeholders}}` verbatim** — same names, same count, same
   braces. They are replaced at runtime.
3. **Do NOT translate** (keep as-is inside the Thai string): endpoint paths
   (`/v1/...`), HTTP codes (`HTTP 403`, `HTTP 409`), the verbs `GET`/`PATCH`
   when attached to an endpoint, commands/code (`WS_*`, `data/server.log`),
   the brand `Weight Streaming` / `Console`, quant tags (`Q4_K_M`, `F16`, …),
   units kept as symbols (`MB`, `GB`, `tok/s`, `B`, `KB`, `TB`), phase codes
   (`P4`, `v1`), file/format names (`.gguf`, `GGUF`, `JSON`), product names
   (`Hugging Face`, `huggingface.co`, `localhost`), and the glyphs
   `→ ↑ ↓ – ⚠️ ✓ n/a ·`.
4. Valid JSON, UTF-8, double quotes.

## Tone guide (Thai)
- Polite but **concise** — product UI copy, not chat slang. No ครับ/ค่ะ in
  labels/buttons/stat captions.
- Thai runs long — keep button/label strings tight (the verifier only warns
  past EN+45%, but aim shorter).
- Spaces around Latin tokens and numbers (`โหลด {{count}} โมเดล`).

## Where each namespace appears (screen context)

- **hub** — the NEW Hub page (search Hugging Face for GGUF models, download
  them to a models folder with real progress).
  - `tagline` / `searchPlaceholder` / `sort*` — the search bar area.
  - `resultsCount` `{{count}}` = number of repositories found.
  - `viewFiles` — card button opening the file-picker drawer.
  - `downloads` / `likes` / `filesCount` (`{{count}}` = number of GGUF files)
    / `updated` (`{{when}}` = relative time like "3 days ago") — card stats.
  - `noQuant` — shown when the quant tag cannot be parsed from a filename.
  - `authNote` — HONEST security note: the server has no authentication, so a
    download writes internet content to this machine; keep it on localhost.
      Keep the meaning exact.
  - `shelvesLabel` = "Recommended by the team" — MUST read as an honest label
    (a small hand-made list), not as sponsored/ranked content; `shelvesHint`
    explains clicking a term just runs the normal search.
  - `shelf16gb` / `shelfMoe` / `shelfThai` — titles of the three curated rows.
  - `offlineTitle` / `offlineBody` / `offlineManual` / `offlineOpen` — shown
    when Hugging Face is unreachable. HONEST: nothing is faked while it is
    away; `offlineManual` explains the manual drop-in of a .gguf file.
  - `errorTitle` / `emptyTitle` / `emptyBody` — other result states.
  - `filesTitle` / `filesHint` / `targetDir` / `targetDirHint` / `targetDefault`
    / `targetBrowse` / `download` — the file-picker drawer. `targetDirHint`
    says only already-scanned folders are allowed (server rejects, HTTP 403).
  - `dlTitle` / `dlEmpty` — the downloads panel.
  - `dlStatus_queued|downloading|done|failed|cancelled` — short status labels
    (lowercase in EN; keep them equally short in Thai).
  - `dlCancel` / `dlRetry` / `dlRetryNote` — retry honestly means "start over
    from byte 0" (v1 has NO resume) — keep that meaning.
  - `dlBytes` (`{{done}}` / `{{total}}` = formatted sizes), `dlUnknownTotal`
    (`{{done}}`), `dlSpeed` (`{{speed}}` = e.g. "12.3 MB/s"), `dlEta`
    (`{{eta}}` = e.g. "2m 30s") — REAL progress numbers; just wrap them.
  - `dlStarted` / `dlStartedBody` (`{{filename}}`, `{{dir}}`), `dlDone` /
    `dlDoneBody` (`{{filename}}`), `dlFailed`, `dlCancelledToast` — toasts.
  - `loadNow` / `loadNowGo` / `loadNowBody` (`{{filename}}`) / `loadNowNote` /
    `loadStarted` (`{{id}}` = model id) / `loadFailed` — after a download
    finishes the console offers to load the model into the server.
  - `resumeNa` / `deleteNa` — truthful capability notes (no resume in v1;
    file deletion deliberately unavailable on an unauthenticated server).

- **overview** — the home dashboard (ONLY the `activity.*` block is new here;
  re-translate the whole file, keeping batch-2 meanings for the rest).
  - `activity.title` / `activity.tip` — the feed now shows the five most
    recent generations from the server's usage history. `tip` must keep: real
    telemetry; tok/s shows "–" when unmeasured (never fabricated).
  - `activity.emptyTitle` / `activity.emptyBody` — HONEST empty state:
    recording starts after the next generation; history began with the
    phase-4 backend, older runs are not listed.
  - `activity.colModel` / `colTokens` / `colSpeed` / `colWhen` — table column
    headers (keep `colSpeed` = "tok/s" — the unit itself is not translated).

- **settings** — Settings page (server + diagnostics blocks changed;
  re-translate the whole file, keeping batch-1 meanings elsewhere).
  - `server.readTitle` / `readHint` — values now come from GET /v1/config.
  - `server.configKeys` — heading of the per-key table.
  - `server.src_env` / `src_default` / `src_runtime` — SOURCE BADGES (where a
    value came from). Keep these three as SHORT LATIN words exactly as in EN
    (`env`, `default`, `runtime`) — they are technical labels; their `*Tip`
    strings ARE translated (explain each source in Thai).
  - `server.modelsDirs` / `modelsDirsHint` / `issuesDir` / `configVersion` —
    the folder + version rows.
  - `server.runtimeTitle` / `runtimeHint` — PATCH /v1/config applies live but
    reverts on restart.
  - `server.runtimeSafe` ("applies now") / `runtimeGated` ("next loads") —
    TINY badge labels next to form fields; keep very short.
  - `server.gatedWarn` — buffer/context/threads only take effect on the NEXT
    model load. Keep the meaning exact.
  - `server.apply` / `applied` / `appliedGated` / `applyFailed` — apply button
    + result toasts.
  - `server.restartTitle` / `restartHint` / `restartKey` / `restartValue` /
    `requestSnippet` / `snippetTitle` / `copySnippet` — the server REFUSES
    these keys (HTTP 409) and answers with an env snippet; the UI shows it for
    copy. Honest, not scary.
  - `server.applyTitle` / `applyHint` — the full start-command generator.
  - `server.field.lowerPriority` / `maxRequests` / `queueDepth` — new labels.
  - `diagnostics.logTitle` / `logLines` (`{{count}}` = number of lines) /
    `logDownload` / `logEmpty` / `logHint` — the log-tail viewer. `logHint`
    must keep: real lines from the in-memory ring buffer, starts empty each
    server start, full log in data/server.log.

- **models** — Models page (the `library.*` block is new; re-translate the
  whole file, keeping batch-2 meanings for loaded/scan/load).
  - `library.title` / `tip` — the model folders from GET /v1/config + which
    loaded models live in each.
  - `library.fetchFailed` — the folders could not be read from the server.
  - `library.loadedCount` (`{{count}}` = how many loaded models point here) —
    keep it compact, e.g. "โหลดแล้ว {{count}}".
  - `library.onDisk` — label for files present on disk.
  - `library.noneHere` — no loaded model points at this folder yet.
  - `library.scanThis` / `findHub` — action buttons (scan this folder / go
    find models in the Hub).
  - `library.noDelete` — HONEST capability note: deleting model files is
    deliberately NOT available in v1 because the server has no authentication;
    removal stays a manual job on the host. Keep the meaning exact.

## Placeholder reference (batch 3)
- `{{count}}` = integer (repositories, files, lines, loaded models)
- `{{when}}` = relative time ("today"/"3 days ago")
- `{{done}}` / `{{total}}` = formatted byte sizes ("12.3 MB")
- `{{speed}}` = formatted speed ("1.2 MB/s")
- `{{eta}}` = formatted duration ("2m 5s")
- `{{filename}}` = a .gguf filename · `{{dir}}` = a folder path
- `{{id}}` = model id

Write the four Thai files, then stop. The build verifier checks key parity and
placeholder integrity automatically.

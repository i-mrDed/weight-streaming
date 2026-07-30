# Translation Kit — Batch 2 (Overview / Chat / Live Stats / Models pages)

You are translating UI strings for **Weight Streaming Console**, a local-first
dashboard that manages a local LLM server. This is **batch 2** — the four main
product pages: Overview (home dashboard), Chat, Live Stats, and Models. Batch 1
(shell/navigation/theme/errors/settings-appearance) is already translated; its
glossary carries over (see `GLOSSARY.md`).

## Your task
Translate every value in `en/*.json` into Thai and write the result to
`frontend/locales/th/<same filename>` (one file per namespace: overview, chat,
stats, models). **Do not read any file outside this `translation-kit/batch-2/`
directory.** Do not modify the EN files.

## Hard rules
1. **Keep every key.** No adding, no removing, no renaming. The key tree shape
   must match EN exactly.
2. **Preserve `{{placeholders}}` verbatim** — same names, same count, same
   braces. They are replaced at runtime.
3. **Do NOT translate** (keep as-is inside the Thai string): endpoint paths
   (`/v1/...`), commands/code (`pip install -U llama-cpp-python`), the brand
   `Weight Streaming` / `Console`, quant tags (`Q4_K_M`, `F16`, `Q2_K`, …),
   units kept as symbols (`MB`, `GB`, `tok/s`, `tokens`, `pp`), phase codes
   (`P4`), ADR ids (`ADR-003`), file/format names (`.gguf`, `.md`, `GGUF`,
   `Markdown`, `localStorage`), platform/product names (`Windows`, `POSIX`,
   `llama.cpp`, `Jan Desktop`), and the glyphs `↑ ↓ → ▲ ⚠️ 💭 🧩 ✓ n/a`.
4. Valid JSON, UTF-8, double quotes.

## Tone guide (Thai)
- Polite but **concise** — product UI copy, not chat slang. Avoid ครับ/ค่ะ in
  labels, buttons, stat captions (OK once in a friendly empty-state body).
- Short labels: Thai runs long — keep button/label strings tight (verifier
  only *warns* past EN+45%, but aim shorter).
- Spaces around Latin tokens and numbers (`โหลด {{count}} โมเดล`, `v{{version}}`).

## Where each namespace appears (screen context)

- **overview** — the home dashboard.
  - `hero.*` — status strip at top: online/offline state, `uptime` ("up 3m 12s"
    — measured by the browser session, `uptimeTip` explains it honestly),
    process priority badges.
  - `quick.*` — four shortcut buttons (scan / load / chat / report issue).
  - `models.*` — row of loaded-model cards + unload confirm dialog
    (`unloadBody` names the model id via `{{id}}`) + empty state.
  - `widgets.*` — three health cards: paging demand (faults per token),
    page-cache residency (Windows-only — `unavailable` shows elsewhere),
    open-issues counter linking to the Issues page.
  - `activity.*` — **deliberately empty panel**: generation history needs a
    server endpoint from a later phase (P4). The copy must stay honest: it
    says recording starts after the next generation and nothing is stored yet.
    Do not make it sound like history exists.

- **chat** — full chat page.
  - `side.*` / `group.*` — conversation sidebar (localStorage): Today /
    Yesterday / Older groups, rename / delete (confirm) / export as Markdown.
  - `model.*` — model picker in the toolbar.
  - `agent.*` — mode selector. **Honest capability copy**: `tip` must keep the
    meaning that Agent mode only wires a system prompt — the server executes
    no tools yet. `suffix` is text appended to the system prompt when Agent
    mode is on (translate it too; it is shown to the model but lives in the
    UI strings).
  - `effort.*` — reasoning-effort segmented control; `tip` must keep the
    meaning that the value is sent but has **no effect** server-side yet.
  - `composer.*` — input box + send/stop; `estimate` = live char/token counter
    (`{{chars}}`, `{{tokens}}` are numbers).
  - `empty.*` — empty conversation states.
  - `drawer.*` — parameter drawer: temperature / top-p / max-tokens sliders,
    param preset chips (`preset.precise|balanced|creative`), system-prompt
    textarea, save custom presets.
  - `presets.*` — four system-prompt presets (name + body text). The `.text`
    values are instructions shown to the model — translate them naturally.
  - `notif.*` — desktop notification when a long generation finishes while the
    tab is hidden.
  - `thinking` / `thinkingLive` — labels of the model's `<think>` accordion.

- **stats** — live telemetry page (polls every 2s).
  - `gauge.*` — five gauge cards. **Critical honesty strings**:
    `hitRateCaveat` explains the buffer hit rate is genuinely 0% in real runs
    (llama.cpp reads its own mmap — ADR-003) and to use Paging Demand instead.
    Keep the meaning exact; do not soften or dress up.
  - `chart.*` — two time-series charts fed by a **session-only** client buffer;
    `window` = the label "session window · since opening this page" — must NOT
    read as persistent history.
  - `paging.*` — detail card: hard/soft faults, disk demand per token, source
    badges (`srcFaults` = POSIX major faults, `srcResidency` = Windows
    residency estimate), and n/a states.
  - `heatmap.*` — MoE expert grid; `notMoe*` is the degrade for dense models
    (no expert routing to show — not an empty grid). `firing` only appears
    when real telemetry exists.
  - `server.*` — server block labels.
  - `idle.*` / `empty.*` — before the first generation / with no model.

- **models** — models page.
  - `loaded.*` — loaded-model cards + actions (unload with "remember this
    session" checkbox, force-reload confirm, shortcuts to Stats/Chat).
    `reloadNote` discloses that the context window resets to default because
    the server does not expose the current value — keep that honesty.
  - `scan.*` — scan panel: folder input + native browse + results (with
    `may_need_upgrade` warning suggesting `pip install -U llama-cpp-python`).
  - `load.*` — load form: path/browse, model id, buffer MB, context, threads,
    quant advisories (`advFull` = unquantized F16/F32/BF16 warning; `advLow` =
    Q2_K may echo/garble — recommend Q4_K_M+), load progress (not cancellable —
    `progressNote` says so honestly).

## Placeholder reference
- `{{duration}}` = human uptime, e.g. `3m 12s`
- `{{id}}` = model id
- `{{mb}}` = a number (MB)
- `{{when}}` = relative day ("today"/"yesterday"/…)
- `{{count}}` = integer
- `{{title}}` = conversation title
- `{{chars}}` / `{{tokens}}` = numbers (composer estimate)
- `{{quant}}` = quant tag, e.g. `F16`, `Q2_K` (do not translate the value)

Write the four Thai files, then stop. The build verifier checks key parity and
placeholder integrity automatically.

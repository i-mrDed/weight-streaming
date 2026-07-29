# Issue Tracking System — Full Product Plan

> **Status:** Historical plan; implemented in v0.12.0. Current reported issues are stored under `data/issues/` and summarized in `ISSUES.md`.
> **Date:** 2026-07-27  
> **Goal:** Zero-gap feedback loop for end users and maintainers  
> **Related:** `ISSUES.md` (current lightweight tracker)

---

## 1. Problem Statement

Today:
- Users report bugs only via chat with the developer
- `ISSUES.md` exists but is manual and incomplete
- No in-app report button, no auto-captured debug context
- Risk of dropped reports, incomplete reproduction info, no verify loop

When the product is used by others, we need a **closed-loop system**:

```
User sees problem
  → reports easily (in-app)
  → system captures context automatically
  → maintainer triages / tracks
  → fix + test
  → user verifies
  → issue closed
```

No step should depend on memory or informal chat alone.

---

## 2. Goals & Non-Goals

### Goals
1. **Easy reporting** — 1–2 clicks from SPA / CLI
2. **Complete context** — version, model, OS, error, last actions
3. **Durable storage** — nothing lost if chat ends
4. **Clear lifecycle** — Open → In Progress → Fixed → Verified → Closed
5. **Maintainer workflow** — list, filter, update status, link commits
6. **Works offline/local-first** — same as product (no cloud required for MVP)
7. **Exportable** — markdown/JSON for git or future GitHub Issues sync

### Non-Goals (MVP)
- Full GitHub Issues replacement / two-way sync (Phase 2)
- Multi-tenant cloud SaaS issue tracker
- AI auto-fix without human review
- Public anonymous internet reporting (local product first)

---

## 3. Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Frontends                                                   │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                   │
│  │ SPA      │  │ Gradio   │  │ CLI      │                   │
│  │ Report   │  │ Report   │  │ report   │                   │
│  │ button   │  │ panel    │  │ command  │                   │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘                   │
│       └─────────────┴─────────────┘                         │
│                         │ HTTP                               │
├─────────────────────────┼───────────────────────────────────┤
│  API Server             ▼                                    │
│  POST   /v1/issues              create issue                 │
│  GET    /v1/issues              list (filter by status)      │
│  GET    /v1/issues/{id}         detail                       │
│  PATCH  /v1/issues/{id}         update status / notes        │
│  POST   /v1/issues/{id}/verify  user verification            │
│  GET    /v1/issues/export       export markdown/json         │
│  GET    /v1/debug/context       auto debug bundle            │
│                                                                  │
│  IssueStore (JSONL + index)                                      │
│  data/issues/issues.jsonl                                        │
│  data/issues/ISSUE-xxx.md  (human-readable mirror)               │
├──────────────────────────────────────────────────────────────┤
│  Maintainer tools                                                │
│  - SPA Admin tab (local only) or CLI: weight-stream issues       │
│  - Sync to ISSUES.md summary                                     │
│  - Optional later: GitHub export                                 │
└──────────────────────────────────────────────────────────────┘
```

---

## 4. Issue Data Model

```json
{
  "id": "ISSUE-019",
  "title": "Browse dialog closes without selection",
  "description": "User-visible symptom in plain language",
  "steps_to_reproduce": ["1. Open Models", "2. Click Browse Model File", "..."],
  "expected": "Dialog stays open until user selects or cancels",
  "actual": "Dialog closes immediately",
  "severity": "medium",
  "status": "open",
  "created_at": "2026-07-27T12:00:00Z",
  "updated_at": "2026-07-27T12:00:00Z",
  "created_by": "local-user",
  "context": {
    "app_version": "0.11.0",
    "llama_cpp_version": "0.3.16",
    "python_version": "3.14.2",
    "os": "Windows-10-...",
    "model_path": "...",
    "model_architecture": "qwen35moe",
    "endpoint": "/v1/models/load",
    "last_error": "unknown model architecture: 'qwen35moe'",
    "server_log_tail": ["..."],
    "browser_user_agent": "..."
  },
  "analysis": {
    "root_cause": null,
    "hypothesis": null
  },
  "resolution": {
    "fix_summary": null,
    "commit": null,
    "test_notes": null,
    "verify_steps": null
  },
  "timeline": [
    {"at": "...", "event": "created", "by": "user"},
    {"at": "...", "event": "status:in_progress", "by": "maintainer"}
  ]
}
```

### Status lifecycle (strict)

```
open → triaged → in_progress → fixed → verify_pending → verified → closed
                              ↘ wontfix / duplicate → closed
```

Rules:
- `fixed` requires: root_cause + fix_summary + verify_steps
- `verified` requires: user or maintainer confirmation note
- `closed` only from `verified`, `wontfix`, or `duplicate`

---

## 5. User Experience

### 5.1 SPA — Report Issue button (always visible)

Header button: **Report Issue**

Form fields:
- Title (required)
- What happened (required)
- Steps to reproduce (optional textarea)
- Expected vs Actual (optional)
- Severity: low / medium / high / critical
- Contact note (optional, local only)

**Auto-attached (user can review/edit before submit):**
- App version, llama-cpp version, Python, OS
- Current model path + architecture
- Last API error (if any)
- Recent server log lines (last 50)
- Active tab / last endpoint

After submit:
- Show `ISSUE-0xx created`
- Button: Copy issue ID
- Link: View my reports

### 5.2 CLI

```bash
weight-stream issues list
weight-stream issues show ISSUE-019
weight-stream issues report --title "..." --desc "..."
weight-stream issues set-status ISSUE-019 in_progress
weight-stream issues export --format md
weight-stream debug-context   # print/save debug bundle
```

### 5.3 Maintainer view (SPA Admin or CLI)

- Filter by status / severity
- Edit analysis + resolution
- Mark fixed with commit hash
- Request verification
- Export to `ISSUES.md` summary

---

## 6. Storage Design (local-first)

```
data/issues/
  issues.jsonl          # append-only event log + current snapshots
  ISSUE-001.json        # current state per issue
  ISSUE-001.md          # human-readable mirror
  attachments/          # optional screenshots later
  ISSUES_SUMMARY.md     # auto-generated index (replaces/extends root ISSUES.md)
```

Why JSONL + per-issue JSON:
- Durable, git-friendly enough
- Easy backup
- No DB dependency for MVP

Config:
- `WS_ISSUES_DIR` (default: `./data/issues`)
- `WS_ISSUES_ADMIN_TOKEN` (optional simple token for status changes from UI)

---

## 7. API Contract (MVP)

| Method | Path | Who | Purpose |
|--------|------|-----|---------|
| GET | `/v1/debug/context` | anyone local | Collect debug bundle |
| POST | `/v1/issues` | user | Create issue |
| GET | `/v1/issues` | user/maintainer | List |
| GET | `/v1/issues/{id}` | user/maintainer | Detail |
| PATCH | `/v1/issues/{id}` | maintainer | Update fields/status |
| POST | `/v1/issues/{id}/verify` | user | Confirm fix works |
| GET | `/v1/issues/export?format=md\|json` | maintainer | Export |

Validation:
- title min 5 chars
- description min 10 chars
- status transitions enforced server-side

---

## 8. Workflow (no gaps)

```
[1] DETECT
    - User hits error in UI → error banner offers "Report this"
    - Or user opens Report Issue manually

[2] CAPTURE
    - Auto debug context attached
    - User adds human description

[3] RECORD
    - POST /v1/issues → ISSUE-ID assigned
    - Written to JSON + MD mirror
    - Appears in list immediately

[4] TRIAGE
    - Maintainer sets severity + status=triaged/in_progress
    - Adds root_cause hypothesis

[5] FIX
    - Code change + tests
    - Commit message includes ISSUE-ID
    - Maintainer sets status=fixed + verify_steps + commit hash

[6] VERIFY
    - User notified in UI (open issues panel shows "Ready to verify")
    - User runs verify_steps, clicks "Verified" or "Still broken"
    - If still broken → back to in_progress automatically

[7] CLOSE
    - status=closed after verified
    - Summary export updates ISSUES_SUMMARY.md
```

Gap prevention checklist (enforced in code where possible):
- [ ] Cannot mark `fixed` without `verify_steps`
- [ ] Cannot mark `closed` without `verified` (unless wontfix/duplicate)
- [ ] Every status change appends timeline event
- [ ] Create always persists before response returns
- [ ] Export regenerates summary index

---

## 9. Implementation Phases

### Phase A — Foundation (1–2 days)  ← MVP must-have
1. `weight_stream/issues/` package: models, store, service
2. API endpoints above
3. Debug context collector
4. CLI: `issues list/show/report/export`
5. Persist under `data/issues/`
6. Unit tests for store + status transitions

### Phase B — User-facing report UX (1 day)
1. SPA: Report Issue modal + auto context
2. SPA: "Report this error" on failed API calls
3. SPA: My Issues panel (list + verify button)
4. Gradio: simple report form (optional same API)

### Phase C — Maintainer workflow (1 day)
1. CLI status updates + notes
2. Auto-generate `data/issues/ISSUES_SUMMARY.md`
3. Optional local Admin tab in SPA (token-protected)
4. Commit message convention documented

### Phase D — Hardening & polish (0.5–1 day)
1. Attachment support (optional screenshot path/text)
2. Dedup hint (similar title within 24h)
3. Retention/export settings
4. Docs in README + api-docs website page

### Phase E — Future (not MVP)
1. GitHub Issues one-way export
2. Email/webhook notifications
3. Multi-user auth

---

## 10. File Plan

```
weight_stream/issues/
  __init__.py
  models.py          # pydantic Issue, Status enum, transitions
  store.py           # JSON/JSONL persistence
  service.py         # create/list/update/verify/export
  context.py         # debug context collector
  export_md.py       # markdown summary generator

weight_stream/server/
  api_server.py      # mount issue routes
  ...

weight_stream/cli/main.py   # issues subcommands
weight_stream/server/static/index.html  # Report UI

data/issues/         # runtime data (gitignore except .gitkeep)
tests/test_issues.py
docs/ISSUE_SYSTEM.md # operator guide
```

`.gitignore`:
```
data/issues/*.json
data/issues/*.jsonl
data/issues/ISSUE-*.md
!data/issues/.gitkeep
!data/issues/ISSUES_SUMMARY.md   # optional tracked summary
```

---

## 11. Testing Strategy

| Test | What |
|------|------|
| Unit | status transition rules |
| Unit | store create/load/update atomicity |
| Unit | debug context fields present |
| API | create → list → patch → verify → close |
| API | reject illegal transitions |
| UI | report modal submits and shows ID |
| UI | error banner "Report this" pre-fills last error |
| E2E | full loop with sample issue |

Success criteria:
- 100% of API issue routes covered by tests
- Illegal transition attempts return 400
- Issue survives server restart
- User can verify without CLI

---

## 12. Security & Privacy

- Local-first: default bind 127.0.0.1
- No secrets in issue context (redact env vars matching TOKEN/KEY/SECRET/PASSWORD)
- Admin mutations optionally require `WS_ISSUES_ADMIN_TOKEN`
- Do not auto-upload anywhere
- User can edit/remove context fields before submit

---

## 13. Effort Estimate

| Phase | Effort | Priority |
|-------|--------|----------|
| A Foundation | 1–2 days | P0 |
| B User report UX | 1 day | P0 |
| C Maintainer tools | 1 day | P1 |
| D Hardening | 0.5–1 day | P1 |
| **Total MVP (A+B)** | **~2–3 days** | |
| **Full (A–D)** | **~4–5 days** | |

---

## 14. Rollout Plan

1. Implement Phase A behind API only
2. Add SPA report button (Phase B)
3. Dogfood: convert recent chat-reported bugs into system issues
4. Replace manual root `ISSUES.md` workflow with generated summary + keep legacy file as pointer
5. Document in website api-docs + README

---

## 15. Open Decisions (need your OK)

| # | Decision | Recommendation |
|---|----------|----------------|
| 1 | Storage location | `data/issues/` under project (local) |
| 2 | Admin protection | optional token for PATCH (default open on localhost) |
| 3 | Track summary in git? | yes: `ISSUES_SUMMARY.md` only; raw issue files gitignored |
| 4 | Gradio report form in MVP? | no — SPA + CLI first |
| 5 | GitHub sync in MVP? | no — Phase E |
| 6 | Auto-open report on every API error? | offer button, don't force modal |

---

## 16. Implementation Order (after approval)

```
Day 1:  issues package + store + API + tests
Day 2:  debug context + CLI + export markdown
Day 3:  SPA Report modal + error "Report this" + My Issues/Verify
Day 4:  Maintainer CLI polish + summary generator + docs
Day 5:  Buffer / dogfood / fix gaps found in dogfood
```

---

## 17. Definition of Done

- [ ] User can file an issue from SPA in < 60 seconds
- [ ] Debug context auto-attached and redacted
- [ ] Maintainer can list/filter/update via CLI
- [ ] Status lifecycle enforced
- [ ] Verify loop works (fixed → verify_pending → verified/closed)
- [ ] Issues persist across restart
- [ ] Tests cover store + API transitions
- [ ] Docs explain user + maintainer flows
- [ ] No reliance on chat history to track bugs

---

**Next step after approval:** implement Phase A (foundation API + store + tests), then Phase B (SPA report UX).

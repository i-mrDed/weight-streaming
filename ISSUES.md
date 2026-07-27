# Issues — Weight Streaming

> Template สำหรับรายงาน + แก้ไข + ยืนยัน issue อย่างเป็นระบบ

---

## Active Issues

<!-- 
  Template:
  ### [ISSUE-001] Short Title
  - Reported: YYYY-MM-DD
  - Status: 🔴 Open | 🟡 In Progress | 🟢 Fixed | ⚪ Verified
  - Symptom: What the user sees
  - Root Cause: Technical reason
  - Fix: What was changed
  - Verification: How to confirm it's fixed
  - Files: changed files
  - Commit: commit hash
-->

---

## Closed Issues

### [ISSUE-001] SPA: "Error: Not Found" on Models tab + Chat broken
- Reported: 2026-07-27
- Status: 🟢 Fixed → ⚪ Verified
- Symptom: Models tab shows "Error: Not Found", dropdown doesn't populate, chat fails
- Root Cause: `GET /v1/models` route was accidentally removed when adding `/v1/models/scan` endpoint. FastAPI returned 404 for the missing route, and without model listing, `currentModel` stayed wrong.
- Fix:
  - Re-added `@app.get("/v1/models")` route before `/v1/models/scan`
  - Rewrote SPA JS with proper error handling, force reload support, and status messages
  - Added Browse button for local file selection
  - Form values preserved after load (no more path clearing)
- Verification: 9/9 API tests pass (empty list, scan, load, list, generate, force reload, generate again, unload, empty list)
- Files: `api_server.py`, `static/index.html`
- Commit: (pending)

### [ISSUE-002] SPA: Scan button redundant with auto-populate
- Reported: 2026-07-27
- Status: 🟢 Fixed
- Symptom: Scan button re-triggers dropdown population and loses selection
- Fix: Replace Scan button with Refresh button (only shows when needed). Auto-scan on first Models tab visit. Dropdown preserves selection.
- Files: `static/index.html`
- Commit: (pending)

### [ISSUE-003] SPA: "already loaded" error on Load Model
- Reported: 2026-07-27
- Status: 🟢 Fixed
- Symptom: Loading same model ID fails with "already loaded" error
- Fix: Added force=True parameter support. When model already loaded, show Reload button instead of Load. Detect "already loaded" error and show helpful message with Reload option.
- Files: `static/index.html`
- Commit: (pending)

### [ISSUE-004] SPA: Path input clears after load
- Reported: 2026-07-27
- Status: 🟢 Fixed
- Symptom: Model path input cleared after successful load
- Fix: Form values preserved after load. Model info displayed in status area. Loaded path/ID shown in form for reference.
- Files: `static/index.html`
- Commit: (pending)

### [ISSUE-006] Browse button can't load external models
- Reported: 2026-07-27
- Status: 🟢 Fixed
- Symptom: Browse button selects file but only gets filename (no path). "Model file not found" when trying to load models from D:\models\ or Jan Desktop directories.
- Root Cause: HTML file input returns only filename (browser security). Can't get full path.
- Fix: Replace Browse with Scan Directory text input. User types custom directory path, scan endpoint supports `?dir=` parameter. Models from Jan app: scan `C:\Users\dedch\AppData\Roaming\Jan\data\llamacpp\models`.
- Verification: `/v1/models/scan?dir=C:\Users\dedch\AppData\Roaming\Jan\data\llamacpp\models` returns .gguf files
- Files: `static/index.html`, `api_server.py`

### [ISSUE-007] Chat generates gibberish for Qwen
- Reported: 2026-07-27
- Status: 🟢 Fixed
- Symptom: Model answers irrelevant/random text
- Root Cause: Raw `/v1/generate` endpoint passes raw prompt without chat template. Qwen MoE models need system prompt + proper message formatting.
- Fix:
  - SPA now uses `/v1/chat/completions` (OpenAI endpoint) instead of raw `/v1/generate`
  - Added system prompt: "You are a helpful, respectful, and honest assistant"
  - Temperature lowered from 0.7 to 0.3
  - Conversation history maintained (up to 20 messages)
- Verification: "What is 2+2?" → "The answer is 4." (correct!)
- Files: `static/index.html`

### [ISSUE-008] Tab resets to Chat on page reload
- Reported: 2026-07-27
- Status: 🟢 Fixed
- Symptom: Refreshing page always goes to Chat tab, even when on Models
- Root Cause: Tab state not persisted across reloads
- Fix: URL hash-based tab persistence (#chat, #stats, #models). `restoreTab()` reads hash on load. `switchTab()` updates hash. `hashchange` event handles browser back/forward.
- Verification: Navigate to Models tab → refresh → stays on Models tab
- Files: `static/index.html`

---

## Issue Workflow

```
Report → Analyze → Fix → Test → Verify → Close
  1. User reports symptom
  2. Developer identifies root cause
  3. Code fix + tests pass
  4. Deploy + user verifies
  5. Move to Closed
```

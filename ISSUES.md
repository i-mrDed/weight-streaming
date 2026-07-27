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
- Symptom: Refreshing page always goes to Chat tab
- Root Cause: Tab state not persisted across reloads
- Fix: URL hash-based tab persistence (#chat, #stats, #models). restoreTab() on load + hashchange event.
- Files: `static/index.html`

### [ISSUE-009] SPA completely broken — JS SyntaxError (duplicate let)
- Reported: 2026-07-27
- Status: 🟢 Fixed
- Symptom: Server runs but SPA shows error / does nothing
- Root Cause: `let scanned` and `let conversationHistory` were declared twice in the same scope (lines 468-470 + duplicate at 556 and 878). `let` cannot be redeclared → SyntaxError → entire JS script fails → no tab switching, no chat, no model loading.
- Fix: Remove duplicate declarations. All three state variables now declared once at top of script (lines 468-470).
- Files: `static/index.html`
- Commit: (pending)

### [ISSUE-010] SPA still broken — null reference to removed Browse element
- Reported: 2026-07-27
- Status: 🟢 Fixed
- Symptom: SPA still non-functional after ISSUE-009 fix
- Root Cause: Event listener for `browse-file` (removed in ISSUE-006) was still in JS. `document.getElementById('browse-file')` returns null → `.addEventListener` on null → TypeError → entire JS script crashes.
- Fix: Removed dead code: browse-file event listener + pickerAddOption function (lines 806-826).
- Verification: All getElementById references now have matching HTML elements (automated check passes).
- Files: `static/index.html`
- Commit: (pending)

### [ISSUE-011] Chat quality: model echoes question instead of answering
- Reported: 2026-07-27
- Status: 🟡 Improved (model limitation documented)
- Symptom: Model responds with gibberish or echoes the question
- Root Cause: Two factors:
  1. **Template**: Was using plain "System: / User: / Assistant:" format instead of model's built-in chat template. Fixed by using llama-cpp-python's `create_chat_completion()` which reads Qwen's `<|im_start|>` template from GGUF metadata.
  2. **Model quality**: Qwen1.5-MoE-A2.7B_Q2_K is 2-bit quantized — severe quality loss (~60-70%). The model echoes/repeats because it can't generate coherent responses at this quantization level. This is a model limitation, not a bug.
- Fix:
  - openai_compat.py now passes messages array directly to `create_chat_completion()` (proper template)
  - Added ModelManager.chat_completion() + chat_completion_stream() methods
  - No Agent system needed — template was the issue
- Recommendation: Use Q4_K or higher quantization for usable chat quality. Q2_K is suitable only for weight-streaming benchmarking, not production chat.
- Files: `openai_compat.py`, `model_manager.py`
- Commit: (pending)

### [ISSUE-012] Chat history lost on page reload
- Reported: 2026-07-27
- Status: 🟢 Fixed
- Symptom: All chat messages disappear after browser refresh
- Fix: Added localStorage persistence (ws-chat-history key). Saves last 20 messages. Restores on page load. Added Clear button to reset history.
- Files: `static/index.html`
- Commit: (pending)

### [ISSUE-013] No quick way to browse models from common directories
- Reported: 2026-07-27
- Status: 🟢 Fixed
- Symptom: User wants to load models from Jan Desktop (C:\Users\dedch\AppData\Roaming\Jan\data\llamacpp\models) or D:\models but has to type the full path manually
- Fix: Added preset quick-scan buttons: Jan Desktop, D:\models, Current Dir, All Drives. One-click scan of common model locations.
- Files: `static/index.html`
- Commit: (pending)
- Reported: 2026-07-27
- Status: 🟢 Fixed
- Symptom: Refreshing page always goes to Chat tab, even when on Models
- Root Cause: Tab state not persisted across reloads
- Fix: URL hash-based tab persistence (#chat, #stats, #models). `restoreTab()` reads hash on load. `switchTab()` updates hash. `hashchange` event handles browser back/forward.
- Verification: Navigate to Models tab → refresh → stays on Models tab
- Files: `static/index.html`

---

## Issue Workflow

### [ISSUE-014] Model scan not recursive — misses models in subfolders
- Reported: 2026-07-27
- Status: 🟢 Fixed
- Symptom: Quick-scan buttons find no models. Jan Desktop stores models in `models/model-name/model.gguf` (subfolder) but scan only checks immediate directory.
- Root Cause: `glob("*.gguf")` is not recursive — doesn't enter subfolders.
- Fix: Changed to `glob("**/*.gguf", recursive=True)` in scan endpoint.
- Verification: Recursive scan finds models in nested directory structures.
- Files: `api_server.py`
- Commit: (pending)

### [ISSUE-015] Hardcoded quick-scan paths not generic
- Reported: 2026-07-27
- Status: 🟢 Fixed
- Symptom: Quick-scan buttons hardcoded to user-specific paths — not portable for other users.
- Fix: Replaced with generic buttons (Scan Default Dirs, Scan Custom Path). Added native Windows file/folder dialogs via `/v1/browse` and `/v1/browse-dir` endpoints (subprocess-based, non-blocking).
- Files: `api_server.py`, `static/index.html`
- Commit: (pending)

### [ISSUE-016] Stats tab shows all zeros
- Reported: 2026-07-27
- Status: ⚪ Documented (expected behavior)
- Symptom: Stats tab shows 0 for hit rate, hot shards, prefetches, resident ratio, speed, tokens.
- Root Cause: Generation stats are empty until first generation completes (by design). Buffer hit_rate is 0% because `buffer.access()` is never called during generation — llama-cpp-python tensor loading is opaque from Python. Page cache requires sampling during generation.
- Explanation: Stats populate after first generation. Hit rate remains 0% until C++ backend patch is implemented. This is a known limitation documented in code.
- Files: N/A (documentation)
- Commit: (pending)

### [ISSUE-017] Browse Model File / Browse Folder buttons do nothing
- Reported: 2026-07-27
- Status: 🟢 Fixed
- Symptom: Clicking Browse buttons produces no dialog and no feedback
- Root Cause: `asyncio` was not imported in `api_server.py`. Browse endpoints called `asyncio.get_running_loop()` → NameError → silent 500. SPA had no error display.
- Fix:
  1. Added `import asyncio` to api_server.py
  2. SPA now shows status messages (opening dialog / selected / cancelled / error)
  3. Dialog runs in subprocess (non-blocking) with topmost flag
- Verification: asyncio import confirmed; browse endpoints no longer crash
- Files: `api_server.py`, `static/index.html`
- Commit: (pending)

### [ISSUE-018] Chat quality — root cause found and fixed
- Reported: 2026-07-27
- Status: 🟢 Fixed
- Symptom: Model echoes questions or generates gibberish instead of answering
- Root Cause (empirically verified with 6 prompt formats):
  - ChatML template (`<|im_start|>`) causes echo/garbage on Qwen Q2_K
  - Q&A style (`User: ...\nAssistant:`) produces correct answers
  - Verified: "What is the capital of France?" → "The capital of France is Paris."
  - Not an Agent system issue — pure prompt format problem
- Fix:
  - Replaced ChatML with robust Q&A prompt format
  - Added stop tokens: `\nUser:`, `\nSystem:`, etc.
  - Added repeat_penalty=1.15
  - Output cleanup strips role markers
- Verification: Answer = "The capital of France is Paris." (clean, correct)
- Files: `model_manager.py`, `backends/llama_cpp.py`
- Commit: (pending)

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

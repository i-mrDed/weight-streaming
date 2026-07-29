# Handoff — SPA Streaming Reliability (items 4–5)

## Status: COMPLETED (2026-07-29, session S017)

Items 4 and 5 below were implemented and validated end-to-end on 2026-07-29:

- **Item 4** — `ModelManager._iter_blocking()` runs blocking iterators in a worker thread (bounded queue + cooperative cancellation); SPA renders via `requestAnimationFrame` + `textContent`; Stop cancels cleanly and always releases the model lock.
- **Item 5** — `WeightStreamModel.stream_chat()` is the public chat-stream API (native template → fallback, real stats incl. cancelled runs, page-cache sampling, no synthetic prefetch). Server code no longer touches `model._llm` for chat. SPA stats panel de-faked.
- **Verified** with `research/models/Qwen1.5-MoE-A2.7B_Q2_k.gguf` + live SPA in Chrome: 3/3 checks passed (`/health` ≤ 28 ms during 220-token generation at 14–15 tok/s; cancellation releases the lock with regeneration in 540 ms; `/v1/stats` reflects real wrapper measurements). Raw results: `docs/verification/items_45_2026-07-29_raw.txt`; rerunnable via `scripts/verify_items_45.py`.
- **Not covered**: Llama-family native-template check (no Llama GGUF available locally); before/after baseline comparison (old code already replaced — only "after" metrics retained).
- Tests: `tests/test_server_config_and_chat.py` (19 tests); full suite 92 passed / 7 skipped.

The original handoff content follows for reference.

---

## Current State

- **Date:** 2026-07-28
- **Session / agent:** Codex
- **Latest commit / rollback point:** `6f2f3e9` (`fix: Separate issue ID prefixes — ISSUE-NNN (dev log) vs Report-ISSUE-NNN (user reports)`)
- **Source of truth:** current worktree; it contains uncommitted user work and the reliability changes below.

## What Changed

Completed reliability work, not committed because the same files already contained user changes:

1. `ModelManager` now receives the `ServerConfig` supplied by `create_app()`. CLI `--n-threads` therefore applies to models loaded from the SPA.
2. Default inference threads are half of logical CPU cores. Local interactive servers default to `idle_unload_timeout = 0`; a positive `--idle-unload-timeout` explicitly enables reclamation.
3. Chat uses `llama-cpp-python.create_chat_completion()` so the GGUF-native template is used when available. The raw prompt formatter remains only as a fallback. The SPA now exposes and sends `top_p`.

Primary files:

- `weight_stream/server/config.py`
- `weight_stream/server/api_server.py`
- `weight_stream/server/model_manager.py`
- `weight_stream/backends/llama_cpp.py`
- `weight_stream/cli/main.py`
- `weight_stream/server/__main__.py`
- `weight_stream/server/static/index.html`
- `tests/test_server_config_and_chat.py`

## Verification

- **Passed:** `python -m compileall -q weight_stream tests\test_server_config_and_chat.py`
- **Passed:** `python -m pytest -q tests/test_server_config_and_chat.py tests/test_exceptions.py` → `12 passed`
- **Passed:** CLI help exposes `--n-threads` and `--idle-unload-timeout` for both `python -m weight_stream server` and `python -m weight_stream.server`.
- **Not verified:** end-to-end generation against a running GGUF model and SPA. No server was listening on `127.0.0.1:8765` during this work.
- **Test environment limitation:** the broader suite reached `66 passed` but `13` `tmp_path` tests could not create their temporary directory under the sandbox. This is not an assertion failure in the reliability changes.

## Next Steps

### Item 4 — prevent streaming from blocking the event loop and reduce browser work

**Goal:** During a long chat response, `/health`, `/v1/stats`, cancellation, and other server work remain responsive; the browser must not re-render the full response for every token.

**Server implementation constraints:**

1. Keep the per-model `asyncio.Lock` and `_generating` lifecycle contract.
2. Run the blocking iterator returned by llama.cpp in a worker thread. Transfer token/error/end events to the async response with a bounded queue and a sentinel; do not call `next()` directly from the event-loop coroutine.
3. Handle client disconnect/cancellation: stop forwarding output, release the queue/worker safely, and always reset `_generating` in `finally`.
4. Preserve OpenAI SSE chunk shape from `weight_stream/server/openai_compat.py` and the existing WebSocket path.

**SPA implementation constraints:**

1. Keep one text node or buffer for the active assistant message.
2. Batch DOM updates with `requestAnimationFrame` (or a short timer), instead of assigning `innerHTML` to the complete accumulated response at every token.
3. Auto-scroll only when the user was already near the bottom; preserve the existing AbortController stop action.

**Acceptance checks:**

- While generating a long response, `GET /health` and `GET /v1/stats` return promptly.
- Stop/cancel leaves the send controls usable and does not retain a busy model lock.
- Browser CPU is materially lower than the old full-response-per-token rendering path.
- Unit test both successful stream and cancellation/error cleanup; then perform a real SPA test.

### Item 5 — route SPA chat through the weight-streaming wrapper

**Goal:** Chat must use the project's streaming/prefetch/page-cache instrumentation rather than directly invoking `model._llm`.

**Current gap:** `ModelManager.chat_completion_stream()` calls `model._llm.create_chat_completion(...)` directly. This preserves native templates but bypasses `WeightStreamModel` orchestration and makes live streaming metrics incomplete.

**Recommended design:**

1. Add a public chat-stream method to `WeightStreamModel` (do not expose `_llm` from server code) that accepts already-normalized messages/sampling options and yields text chunks.
2. Inside that method, use native `create_chat_completion()` first, record generation stats, update page-cache sampling, and invoke only prefetch operations that are supported by actual routing evidence.
3. Refactor `ModelManager.chat_completion_stream()` to consume this public method. Keep the explicit fallback for GGUFs without a usable native template.
4. Do not claim prefetch accuracy or active experts unless the values originate from actual routing/telemetry; current synthetic UI values must remain clearly separated from real values.

**Acceptance checks:**

- Server code no longer accesses `model._llm` for SPA chat streaming.
- Native template output remains correct for at least one Qwen-family and one Llama-family GGUF.
- `/v1/stats` changes during generation and reflects the wrapper's real measurements.
- Compare before/after CPU, token throughput, page residency, and response quality on the same prompt/model/config.

## Suggested Reading Order

1. `docs/HANDOFF_STREAMING_RELIABILITY.md` (this file)
2. `weight_stream/server/model_manager.py`
3. `weight_stream/backends/llama_cpp.py`
4. `weight_stream/server/openai_compat.py`
5. `weight_stream/server/static/index.html`
6. `tests/test_server_config_and_chat.py`

## Rollback

- There is no commit for this round because the worktree was already dirty. Preserve a copy of the edited files before changes.
- The last repository rollback point is `6f2f3e9`; it predates both the user's uncommitted work and this reliability round.

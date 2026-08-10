# Report-ISSUE-003: Loading a 2nd model while one is loaded registers it as loaded but generate fails with port-collision

- **Status:** open
- **Severity:** medium
- **Created:** 2026-08-10T15:29:03Z by local-user
- **Updated:** 2026-08-10T15:29:03Z

## Description
Repro: load model A (llama-server backend, fixed port 8805), then POST /v1/models/load for model B without unloading A. The load returns 200 {'status': 'loaded'} and B appears in /v1/models, but any generate on B raises ModelError 'llama-server on our port serves a DIFFERENT model — port collision' (the _verify_model_path guard). Root cause: the manager registers a model as loaded before the backend's lazy llama-server spawn; the spawn cannot bind the shared fixed port because A's server (registered in _OWNED_PIDS) owns it and _sweep_stale_owner correctly refuses to kill a sibling. Net effect: only the FIRST llama-server model can ever generate; B is a ghost entry. Found while running the new bench harness (it left IQ2_XXS loaded, then the live test_server.py suite's test_load_model+test_generate_stream failed). Expected: either (a) loading B auto-unloads A with a clear message, or (b) load B fails fast with 'only one llama-server model at a time; unload A first' — never a silently-broken loaded state.

## Expected
Loading B while A is loaded either cleanly evicts A or returns a clear error at load time

## Actual
load returns 200 loaded; generate on B fails with port-collision ModelError

## Context
```json
{
  "app_version": "0.15.0",
  "llama_cpp_version": "0.3.34",
  "python_version": "3.14.2",
  "os": "Windows-11-10.0.22631-SP0",
  "cwd": "D:\\.opencode\\.Weight-Streaming",
  "model_path": null,
  "model_architecture": null,
  "last_error": null,
  "last_endpoint": null,
  "env": {}
}
```

## Timeline
- `2026-08-10T15:29:03Z` **created** by local-user

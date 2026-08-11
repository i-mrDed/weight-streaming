# Lesson — Tests that pass locally but fail on CI: the machine-dependent test

> **TL;DR:** The auto-tiering pin/unpin tests passed on the dev machine for
> **six commits straight** while CI was red the whole time. Root cause: the
> tests validated the *shipped default* tier paths — which pointed at real
> model files in `~/models/Gemma4-12B-QAT/...`. Those files exist on the
> developer's machine (so tests passed locally) and don't exist on a fresh
> CI runner (`C:\Users\runneradmin\...`), so validation 400'd there. One
> layer deeper, the default paths were expanded at **import time**, baking
> the developer's home into the module constants. Fix: lazy `~` expansion +
> a hermetic test fixture + a CI guard job that runs the suite with an
> empty HOME.

---

## Timeline

| When | What |
|---|---|
| 2026-08-11 ~09:55 | First red CI run (`Auto-tiering round 3`) — ignored, work continued |
| 09:41 → 11:25 | **5 more pushes to main, all red**, all with the same 4 failing tests |
| 11:25 | `Auto-tiering round 6` pushed; CI red again — investigation started |
| 12:35 | Fix pushed (`4a88b1c`) — **all 4 CI jobs green** |

## The failure (what CI said)

```
Python tests (Windows, 3.13) — Run tests ✗
E  ValueError: quality: file not found:
   C:\Users\runneradmin\models\Gemma4-26B-A4B-QAT\gemma-4-26B-A4B-it-qat-UD-Q4_K_XL.gguf
FAILED tests/test_p4_tiering.py::test_pin_finds_files_and_wires_draft
FAILED tests/test_p4_tiering.py::test_pin_sets_per_tier_max_tokens
FAILED tests/test_p4_tiering.py::test_unpin_restores_default_tier
FAILED tests/test_p4_tiering.py::test_unpin_persists_to_disk
```

Identical on Python 3.11 / 3.12 / 3.13. Frontend always green. Same 4 tests,
every run — but **never seen locally**, because the full suite passed 369/369
with zero failures on the dev machine.

## Root cause (two layers)

### Layer 1 — the tests were not hermetic

The pin/unpin flow restores the *shipped default* tier and then validates the
whole config with `Path(model_path).is_file()`. The default tier points at
`~/models/Gemma4-12B-QAT/...` — real files that happen to exist on the
developer's machine. The tests therefore silently depended on **files outside
the repository** that only exist on one machine. Any other machine (CI,
another dev, a fresh install) fails.

This is the classic "works on my machine" test — the most insidious form,
because the suite *is* green locally, so nothing forces the author to look
again.

### Layer 2 — the defaults were baked at import time

`DEFAULT_FAST` / `DEFAULT_QUALITY` called `os.path.expanduser("~/models/...")`
**at module import**, freezing `C:\Users\dedch\models\...` into the module
constants. Consequences:

- The "shipped default" pair was tied to the developer's home directory —
  on any other machine the default config pointed at paths that could never
  exist there.
- Tests could not redirect `~` via a temp `HOME`/`USERPROFILE` — the
  expansion already happened.

## The fix (`4a88b1c`)

1. **`tiering.py`** — store the literal `~/models/...` paths in the defaults;
   `_expand()` (already called by `normalize_config`/`load_config`/
   `save_config`) expands them lazily at load/save time. Any machine now
   expands the defaults to its **own** home.
2. **`tests/test_p4_tiering.py`** — new `fake_default_models` fixture: stubs
   the two default Gemma files under a temp home and redirects
   `USERPROFILE` + `HOME` there. The 4 restoring tests use it, so they never
   touch real model files.
3. **Verification** — reproduced the exact CI failure locally by running the
   suite with `HOME=C:/nohome` (a nonexistent dir): 4 failed before, 369
   passed after. CI then went green on all 4 jobs.

## Prevention (the guard)

The CI workflow now runs a **hermetic pass**: `pytest` with `HOME` /
`USERPROFILE` pointed at an empty temp dir, on one Python version. Any future
test that quietly depends on files outside the repo will fail on CI even if
it passes locally — turning "works on my machine" into a CI failure instead
of a silent landmine.

## Rules for future tests (the actual lesson)

1. **A test may only read files it created itself** (`tmp_path` fixtures) or
   files committed to the repo. Real models, dev caches, `~/...` paths → never.
2. **If a test needs a model file**, write a stub (`b"GGUF"`) in `tmp_path` —
   validation only checks existence, not content.
3. **If the code under test uses `~` expansion**, monkeypatch both
   `USERPROFILE` (Windows) **and** `HOME` (POSIX) to a temp dir — and make
   sure the expansion happens at *call* time, not import time.
4. **Before pushing, run the hermetic simulation once:**
   `HOME=C:/nohome USERPROFILE=C:/nohome python -m pytest -q` — green there
   is the real "works on a fresh machine" proof. CI runs this automatically
   now, but the local run catches it 2 minutes faster.
5. **A red CI run is a bug report, not noise** — this one was red for 6
   consecutive pushes before anyone looked. First red run = stop and read
   the log.

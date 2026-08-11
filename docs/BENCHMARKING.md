# Benchmarking — how to measure honestly

> **Ground rule (from the project README): every number is a real
> measurement through the REAL engine (llama-server via the API server),
> never a fabricated value.** This document explains the harness that
> enforces that rule and how to read its output.

## The one command

```bash
# Single config + cold/warm throughput + Thai quality gate
python -m weight_stream bench path/to/model.gguf --thai --export research/bench-my-model

# Config matrix (each config runs in its own clean room)
python -m weight_stream bench path/to/model.gguf \
  --matrix '{"t8": "-fa on -t 8", "mtp t8": "-fa on -t 8 --spec-draft-model C:/draft.gguf --spec-type draft-mtp"}'

# Thread sweep shortcut (same as a hand-written matrix)
python -m weight_stream bench path/to/model.gguf --extra-args "-fa on" --sweep-threads 4,8,12,16

# Against an already-running server (skips the clean-room restart)
python -m weight_stream bench path/to/model.gguf --no-restart
```

## What the harness does (per config)

1. **Clean room** — kills every stale `llama-server` on the machine and
   restarts the API server with the exact `WS_LLAMA_EXTRA_ARGS` under test.
   A leftover server answering on the fixed backend port is the classic way
   measurements get silently contaminated (EXP-005/006/007).
2. **Load + verify** — loads the model through the real backend, then
   inspects the ACTUAL spawned `llama-server` cmdline: requested flags must
   be present AND value-aware checks for `-t / -fa / -ctk / -ctv` (a silent
   override would invalidate a sweep while passing a presence-only check).
3. **Cold + warm** — two generations per config:
   - *cold*: the first real workload generation — weights are being faulted
     in from disk, so this is the disk-bound number;
   - *warm*: the second generation with weights in the OS page cache.
4. **Record paging** — `faults/token` and `disk MB/token` from `/v1/stats`,
   so "fast on paper" cannot hide disk thrashing every token (EXP-012).
5. **Thai quality gate** (optional, `--thai`) — the 9 fixed questions from
   EXP-009/011, temperature 0. This is the project's quality floor: an
   ultra-low-bit quant can be fast and still fail Thai tonal accuracy, and
   a tok/s number without the quality side is not a win.

## Reading the output

- **JSON** (`--export x` → `x.json`) is the full diffable record: matrix
  rows + the complete quality gate with FULL answers and think blocks.
  Display layers truncate; the record never does.
- **Markdown** (`x.md` + `x.quality.md`) is the human summary.
- Failed configs are recorded honestly (`❌ error`) — never dropped.

## Known measurement caveats

- **Page-cache variance (EXP-018):** for a model smaller than RAM, the
  "cold" number depends on OS page-cache state, not just disk. A cold run
  after heavy disk activity faults more than one where the file pages
  survived. Report a band (e.g. "cold 43–62 tok/s") or the sustained
  (warm/gate) number, not a single cold reading.
- **`n_ctx` matters for VRAM (EXP-007):** KV cache size affects VRAM
  residency; compare numbers measured at the same ctx.
- **Windows console encoding:** the CLI prints ASCII-safe output; run with
  `PYTHONIOENCODING=utf-8` if you redirect to a file and see Unicode errors.
- **The backend owns ONE fixed port:** only one llama-server model can be
  loaded at a time; loading a new one evicts the old (Report-ISSUE-003).

## Reproducibility checklist

- [ ] `git status` clean; no model loaded on the server (`/v1/models` empty)
- [ ] Note the llama-server build: `python -c "from weight_stream.backends.llama_server import _find_llama_server; print(_find_llama_server())"`
- [ ] Same `n_ctx` / threads for side-by-side comparisons
- [ ] Record cold AND warm AND the gate number — never only one
- [ ] Save the JSON export next to the experiment doc (see `research/experiments/`)

> Once a model passes the gate AND has a full experiment record, it can
> earn a slot in the Hub's "Proven on this rig" recommendations — see
> [`docs/CURATION_CHECKLIST.md`](CURATION_CHECKLIST.md) for the exact
> requirements (clean room, Thai gate, verified file sizes, evidence links).

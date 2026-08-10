# weight-streaming

**Run LLMs larger than your RAM — using NVMe as an extension of memory, measured honestly.**

`weight-streaming` is a local inference platform for large language models
(100B–3T+ parameters, especially MoE) on consumer hardware with 32–64 GB
RAM. Instead of pretending a 104 GB model fits in 12 GB of VRAM, it runs
the model anyway and **reports the real cost** — tok/s, page faults per
token, and disk traffic — so you can see exactly what the machine is
doing and where the bottleneck is.

## What it is now

A full local platform in one package (not just a library):

- **API server** (`python -m weight_stream.server`) — OpenAI-compatible
  `/v1/*` endpoints, model load/unload with per-model context, threads,
  GPU layers and KV-cache type, request queueing, process-priority
  etiquette (the inference child runs below-normal so your desktop stays
  usable while a 100 GB model thrashes CPU/disk)
- **Web console** (SPA at `http://localhost:8765/app`) — live stats
  (tok/s, page-fault demand, VRAM), MoE expert heatmap, chat, model
  library, hub downloads, issue reporting, settings
- **Dual backend** — llama-server subprocess (GPU offload + native
  reasoning control) with graceful fallback
- **Hub** — download GGUF models directly from Hugging Face (sharded
  repos, subdirectories, Xet storage, resumable `.part` downloads with a
  GGUF structural gate before rename)
- **MCP host** — connect stdio/SSE MCP servers for tool calling

## Real measured results (EXP-012, 2026-08-10)

Machine: i9-9900KF (8C/16T), RTX 3060 12 GB, 64 GB RAM.

| model | size | config | cold | warm | verdict |
|---|---|---|---:|---:|---|
| Qwen3.6-35B-A3B IQ1_M | 10 GB (fits VRAM) | `n-cpu-moe 0 -t 8` | **75.9 tok/s** | 73.9 | GPU-bound, light CPU |
| Qwen3.6-35B-A3B IQ1_M | 10 GB | `--cpu-moe` (all experts CPU) | 14.2 | 14.6 | CPU-bound |
| DeepSeek-V4-Flash-0731 UD-IQ3_XXS | **104 GB** | `--cpu-moe -t 8` | 1.48 | 1.76 | **disk-bound** |
| DeepSeek-V4-Flash-0731 UD-IQ3_XXS | 104 GB | `--n-cpu-moe 42 -t 8` | 1.46 | **1.89** | disk-bound |
| DeepSeek-V4-Flash-0731 UD-IQ3_XXS | 104 GB | `--cpu-moe -t 16` | **1.71** | 1.75 | disk-bound |
| DeepSeek-V4-Flash-0731 UD-IQ3_XXS | 104 GB | `n-cpu-moe 10` | — | — | **OOM** (77 GB → 12 GB VRAM) |

The honest headline: a 104 GB model **does run** on this 64 GB machine at
**~1.5–1.9 tok/s**, and the page-fault telemetry (36–77k faults per token,
≈150–300 MB read from disk per token) proves the bottleneck is the
disk→RAM→CPU pipeline — not the GPU, not the CPU. Config tweaks move the
number only ~15%. The path to 15–30+ tok/s is more RAM (128 GB keeps the
whole file in page cache) or more VRAM (see
[`research/experiments/EXP-012`](research/experiments/EXP-012-dsv4flash-103gb/)).
That is the whole point of the project: measure the real cost of running
models bigger than your hardware, then close the gap.

## How it works

Large models (especially MoE) only use a fraction of their parameters per
token. The platform:

1. **Memory-maps** the model file (zero-copy access, no redundant loading)
2. **Tracks** hot weight regions via the OS page cache (Windows
   `QueryWorkingSetEx` residency monitoring)
3. **Measures** the real paging demand per token (faults/tok, disk MB/tok)
4. **Streams** weights from NVMe as needed instead of loading everything
   into RAM
5. **Reports honestly** — every number on the stats page comes from real
   telemetry, never fabricated zeros

## Quick start

```bash
# install (server extras: fastapi/uvicorn; test: pytest/httpx)
pip install -e ".[server,test]"

# start the API server + web console
python -m weight_stream.server --port 8765

# open http://localhost:8765/app
```

```bash
# run the test suite (287 tests)
python -m pytest
```

## Downloading big models (hub)

Models are downloaded from Hugging Face through the hub — sharded repos,
per-quant subdirectories, resumable partials, and a GGUF structural gate
(byte-count parity + header/tensor-table parse) before a `.part` is ever
renamed into place. See `scripts/download_dsv4flash.py` and
`research/experiments/EXP-012-dsv4flash-103gb/` for the 104 GB
DeepSeek-V4-Flash walkthrough.

## Documentation & research

- [`docs/`](docs/) — architecture, issue system, IDE integration
- [`research/experiments/`](research/experiments/) — EXP-001..EXP-012:
  buffer/prefetch simulation, KV-cache scaling, MoE CPU/GPU tiering,
  quant quality (Thai tonal probes), and the DS V4 Flash >RAM measurement
- [`research/HARDWARE_100TPS_PLAN.md`](research/HARDWARE_100TPS_PLAN.md) —
  hardware roadmap informed by measured results

## License

MIT (see `pyproject.toml`).

---
title: weight-streaming
description: Run LLMs larger than your RAM — out-of-core local inference with honest telemetry.
---

# Weight Streaming

**Run LLMs larger than your RAM — using NVMe as an extension of memory,
measured honestly.**

A local, out-of-core inference platform for large language models
(100B–3T+ parameters, especially MoE) on consumer hardware — memory-mapping
the GGUF from NVMe and reporting the *real* cost: tok/s, page faults per
token, and disk traffic. Every number comes from real measurement, or it
shows `n/a` — never a fabricated value.

## Explore

| | |
|---|---|
| [📖 README](../README.md) | features, quick start, config, API overview |
| [🖼️ Screenshots](screenshots/) | real captures + demo GIF from the console |
| [📄 Paper draft](../research/paper/paper.md) | full write-up — abstract, architecture, evaluation (auto fact-checked) |
| [🧪 Experiments](../research/experiments/index.md) | EXP-001…EXP-030 — what was tried, what worked, what's a dead end |
| [📝 EXP-012 write-up](../research/writeups/2026-08-10-exp012-104gb-on-64gb-ram.md) | the honest 104 GB model on 64 GB RAM story (EN + TH) |
| [📣 Launch posts](../research/writeups/2026-08-13-exp012-hn-post.md) | HN/blog + r/LocalLLaMA copy from the fact-checked paper |
| [🗺️ Hardware plan](../research/HARDWARE_100TPS_PLAN.md) | cheapest measured path to 100+ tok/s |
| [🔩 Architecture](../docs/ARCHITECTURE.md) | engine, backends, telemetry |
| [🗓️ Changelog](../CHANGELOG.md) | semantic-version release history |
| [✅ Go-public checklist](GO_PUBLIC_CHECKLIST.md) | the private → public runbook |

## The honest headline

A **104 GB** DeepSeek-V4-Flash GGUF **does run** on an i9-9900KF + RTX 3060
12 GB + 64 GB RAM at **~1.5–1.9 tok/s** — proven disk-bound by OS-level
telemetry (36–77k page faults per token ≈ 150–300 MB read from disk per
token). Config tweaks move the number only ~15%. The path forward is
measured, not marketed: fewer bytes per token, or more RAM/VRAM.

## Getting started

```bash
pip install -e ".[server,test]"
weight-streaming server            # http://localhost:8765/console/
```

See the [README](../README.md) for the full quick start, environment
variables, and the API reference.

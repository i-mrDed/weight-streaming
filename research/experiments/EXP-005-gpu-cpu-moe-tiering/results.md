# EXP-005: GPU `--cpu-moe` Tiering Proof — Results

> **⚠️ INVALIDATED (2026-08-06, EXP-007):** these numbers were measured
> while a stale Jan llama-server (Qwythos-9B dense, `-c 1024`) was listening
> on **port 8805 — the same port our backend uses** — and `_wait_ready()`
> accepted its `/health` without verifying the process. Requests therefore
> went to Qwythos-9B, not the 35B. Verified-clean rerun gives **~18.4 tok/s**
> for the 35B + `--cpu-moe` (see EXP-007). The tiering MECHANISM (experts
> streamed from RAM, page-cache effect) is still real, but every tok/s and
> MB/token number below is untrustworthy.

> **Earlier correction note (kept for the record):** the first draft
> conflated the Qwen1.5-MoE smoke test with the 35B cold run. Fixed below —
> the 35B cold run was **44.42 tok/s**.

## Smoke test first (mechanism check) — Qwen1.5-MoE-A2.7B Q2_K

Small model (5.9 GB, fits VRAM entirely) — validates the `--cpu-moe -fa on`
injection path end-to-end, NOT a tiering result.

| Metric | Value |
|--------|-------|
| tokens | 200 |
| elapsed | 5.40 s |
| tokens/sec | 37.0 |
| page faults (subprocess) | 0 (whole file resident) |

## Qwen3.6-35B-A3B-UD-IQ2_M — cold run (first generation after load)

| Metric | Value |
|--------|-------|
| tokens | 200 |
| elapsed | 4.50 s |
| **tokens/sec** | **44.42** |
| page faults (subprocess) | 152,646 |
| faults/token | 763.2 |
| **fault MB/token** | **3.13** (expert pages pulled from NVMe on first touch) |
| VRAM used | 8.4 / 12 GB |

## Qwen3.6-35B-A3B-UD-IQ2_M — warm run (same process, seconds later)

| Metric | Value |
|--------|-------|
| tokens | 200 |
| elapsed | 4.80 s |
| **tokens/sec** | **41.7** |
| page faults (subprocess) | **0** |
| **fault MB/token** | **0.00** |
| VRAM used | 9.0 / 12 GB |

> Cold vs warm used DIFFERENT prompts (story vs sky-colour) — treat the 44.4 vs
> 41.7 difference as run-to-run noise, not a cache regression.

## Context (directional only — NOT apples-to-apples)

| Configuration | tok/s | Honest framing |
|--------------|-------|----------------|
| EXP-004 CPU-only Qwen1.5-MoE-A2.7B (Q2_K, 5.9GB) | 22.7 | different engine + model |
| Research claim: Qwen3-30B-A3B **Q8 (32GB)** full-mmap NVMe, **16GB-RAM machine** | 2.5–4.3 | different model version, ~3× bigger file, ~4× heavier quant, 4× less RAM |
| **EXP-005: Qwen3.6-35B-A3B IQ2_M (11.5GB) GPU + `--cpu-moe` (warm)** | **41.7** | **this experiment** |

The 41.7 tok/s is *directional evidence* that GPU + expert-RAM tiering is the
right direction — not a measured speedup against the 2.5–4.3 claim, which ran a
different model/quant/machine.

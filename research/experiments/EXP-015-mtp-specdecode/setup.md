# EXP-015: MTP Speculative Decoding on the GPU Backend — Setup

## Goal

Close the last open question from EXP-010 (speculative decoding was a dead
end on the CPU path): does llama-server's built-in **MTP** (multi-token
prediction) head — `--spec-type draft-mtp` — raise tok/s on the MoE-tiered
GPU backend, where a dedicated draft model would add too much memory?

EXP-014 listed MTP as ROADMAP Phase 4 candidate #4 (speculative decode on
the GPU backend), with the note that a draft model with a matching vocab is
hard to find — the Qwen3.6-35B-A3B **MTP variant** embeds the draft head in
the SAME file, so vocab matches by construction and no extra download is
needed beyond the model itself.

## Hypothesis

For a disk/PCIe-bound MoE (experts streamed from RAM), a cheap MTP head that
predicts 2-3 tokens per step should cut the number of full target-model
forwards per accepted token — a win if the MTP head's extra compute is
smaller than the expert-streaming cost it avoids.

## Method

Same skeleton as EXP-008/011/012 harnesses, on the MTP variant of the model
we already know:

- **Model:** `unsloth/Qwen3.6-35B-A3B-MTP-GGUF` → `Qwen3.6-35B-A3B-UD-IQ1_M.gguf`
  (11.37 GB, same quant as EXP-011's IQ1_M **plus** the embedded MTP head:
  4 extra `blk.40.nextn.*` tensors, `qwen35moe.nextn_predict_layers = 1`)
- **Server:** our own API server (dogfood — model downloaded through the
  hub), llama-server b9967 (bb7049f7) — confirmed it supports
  `--spec-type draft-mtp` and initializes an MTP draft context.
- **Configs** (each restarts the API server with WS_LLAMA_EXTRA_ARGS):
  1. baseline: `--n-cpu-moe 0 -fa on -t 8` (all experts GPU, as EXP-011)
  2. MTP t8:  `+ --spec-type draft-mtp`
  3. MTP t12: `+ --spec-type draft-mtp -t 12`
- Each config: warmup gen (8 tok) + 3 × 300-token Thai idiom generations,
  median tps. VRAM sampled with nvidia-smi during generation.
- **Control:** same harness on IQ2_M (11.52 GB) to validate the measurement
  path against EXP-011 numbers (EXP-011: 56.4 tps server-side).

## Environment

- i9-9900KF, RTX 3060 12 GB, 64 GB RAM (fixed — cannot upgrade)
- llama-server b9967 (Jan CUDA build, bb7049f7)
- API server 0.14.0, harness `scripts/measure_mtp_specdecode.py`

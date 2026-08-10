# EXP-015: MTP Speculative Decoding on the GPU Backend — Results

## Headline: MTP does NOT help on this hardware — it costs 11–18%

Measured on the **MTP variant** of Qwen3.6-35B-A3B UD-IQ1_M (11.37 GB),
n-cpu-moe 0 (all experts GPU), 3 × 300-token Thai idiom prompt, median tps:

| config | median tps | Δ vs baseline |
|--------|:---:|:---:|
| baseline (t8) | **49.7** | — |
| + `--spec-type draft-mtp` t8 | 40.9 | **−18%** |
| + `--spec-type draft-mtp` t12 | 44.4 | **−11%** |

MTP is confirmed ACTIVE (llama-server log: `[spec] adding 66 MiB`,
`creating MTP draft context against the target model`,
`adding speculative implementation 'draft-mtp', n_max=3`) — the slowdown is
not a silent no-op.

## Why it loses (not just noise)

1. **The MTP variant is bigger than VRAM.** The embedded head adds 1.32 GB
   to the file (10.05 → 11.37 GB). EXP-011's IQ1_M fit in 10.8 GB VRAM with
   headroom (72–77 tps); this file shows **10.5/12 GB during generation** —
   the model no longer fits, so part of the working set spills back to RAM
   every token.
2. **Control run validates the method, not the file.** Same harness on IQ2_M
   (11.52 GB, also >VRAM): 52.4 tps — close to EXP-011's 56.4 for IQ2_M.
   The 49.7 baseline on the MTP file is what a *bigger-than-VRAM* file costs
   (~77 → ~50 tps); the MTP head itself adds the extra −11–18% on top.
3. **MTP draft isn't free on a MoE.** The draft step still runs the full
   expert-gated forward pass (256 experts), so it buys fewer tokens than a
   tiny dense draft would — and the acceptance savings don't beat the extra
   compute on a machine that's already VRAM-bound.

## Raw data

- `scripts/.mtp_out.json` — per-config medians
- `scripts/.iq2m_cal.json` — IQ2_M control
- VRAM during gen (MTP t12): 10,515–10,520 MiB, GPU util 38–47%
- Server log: `scripts/.ws-server-mtp.log` (spec init lines at -lv 5)

## Conclusion for the roadmap

**Speculative decoding is now closed on BOTH paths** (EXP-010 CPU dead end,
EXP-015 GPU MTP costs more than it saves). ROADMAP Phase 4 candidates #4
(spec decode) is retired; the remaining software-only levers are:

1. Expert-popularity census → auto `n-cpu-moe` tiering
2. CPU lane by host-cache residency (already measurable)
3. IQ2_XXS on DS V4 Flash (bytes/token ↓ → resident ↑)

The honest takeaway: on a 12 GB card the ceiling is set by
**bytes-per-token vs VRAM+PCIe**, not by decode-side tricks. More RAM
(lifts the whole curve per EXP-012) or a bigger card (32 GB) are the real
levers — neither available on this machine, so the software path is to cut
bytes (quant) and keep hot experts resident (tiering).

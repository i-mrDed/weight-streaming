# EXP-020: Gemma 4 QAT+MTP — config sweep (threads / flash-attn / KV cache)

## Date
2026-08-11

## Why
EXP-019 found Gemma 4 26B-A4B QAT+MTP is the Thai-safe daily driver at
45–47 tok/s (with `-fa on -t 8 --spec-type draft-mtp --spec-draft-n-max 2`).
That single config was NOT tuned. EXP-006 (threads scaling on the CPU lane)
showed threads matter on this i9-9900KF; flash-attn and KV cache type
change VRAM/compute balance. Question: how much headroom is left in the
DEFAULT-ish config — can the daily driver go past 47 tok/s?

## Method
`python -m weight_stream bench <gemma-main> --model-id gemma4 --gen-tokens 120
--matrix '<7 configs>'` — harness clean room per config (fresh API server,
cmdline verified, cold + warm gen). Every config keeps the MTP draft
(`--spec-draft-model <draft> --spec-type draft-mtp --spec-draft-n-max 2`)
because MTP is the +20% lever proven in EXP-019.

Matrix (base = MTP flags):
| name | threads | flash-attn | KV type |
|---|---|---|---|
| t4  | 4  | on  | f16 |
| t6  | 6  | on  | f16 |
| t8  | 8  | on  | f16 |  (EXP-019 baseline)
| t12 | 12 | on  | f16 |
| t16 | 16 | on  | f16 |
| fa off t8 | 8 | off | f16 |
| kv q8 t8 | 8 | on | q8_0 |

Model (byte-exact, same files as EXP-019):
- `unsloth/gemma-4-26B-A4B-it-qat-GGUF` main `UD-Q4_K_XL` 14.25 GB
- `MTP/mtp-gemma-4-26B-A4B-it-Q8_0.gguf` 0.46 GB draft

## Files
- `bench.json` / `bench.md` — harness matrix export (per-config cold/warm)
- `results.md` / `analysis.md`

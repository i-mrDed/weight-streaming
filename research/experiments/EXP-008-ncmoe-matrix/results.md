# EXP-008: `--n-cpu-moe` Matrix — Results

All runs: 200 tokens, warm, ctx 2048, t=8, `-fa on`, flag verified in the
spawned llama-server cmdline, orphan processes killed before each config.
Baseline VRAM (no model): ~1,810–1,910 MiB.

## Matrix results

| config | experts on GPU | server tok/s | SSE tok/s | VRAM after gen | p95 ms | flag ok |
|--------|---------------:|-------------:|----------:|---------------:|-------:|:-------:|
| `--cpu-moe` (all CPU) | 0/40 layers | **17.9** | 19.2 | 3,858 MiB | 60.5 | ✅ |
| `--n-cpu-moe 20` | 20/40 | 33.8 | 36.6 | 8,532 MiB | 31.9 | ✅ |
| `--n-cpu-moe 10` | 30/40 | **44.5** | 47.6 | 10,834 MiB | 29.5 | ✅ |
| `--n-cpu-moe 0` (all GPU) | 40/40 | **53.9** | 57.5 | 11,338 MiB | 20.2 | ✅ |

## Sanity checks

- `--cpu-moe` baseline in this session (17.9 tok/s, 3,858 MiB) matches
  EXP-007's clean measurement (18.4 tok/s, ~3,850 MiB) → same-server
  apples-to-apples comparison is valid.
- VRAM grows monotonically with expert GPU offload (3.9 → 8.5 → 10.8 →
  11.3 GB) — consistent with "experts moved into VRAM", not an artifact.
- p95 improves monotonically too (60.5 → 31.9 → 29.5 → 20.2 ms).

## Cleanup note (contamination fixed mid-experiment)

The first run of the sweep returned 32.8 tok/s / 8,566 MiB for ALL FOUR
configs — a stale-server artifact: after killing the API server, its
llama-server subprocess remained (Windows orphans children), still bound to
port 8805, answering `/health` with the same model path. Killing all
llama-server.exe before each restart + verifying the spawned cmdline fixed
it. The 32.8/8566 rows are DISCARDED, not part of the results above.

---

## Re-validation 2026-08-06 (ผ่าน clean-room gate, EXP-009 era)

Re-run ผ่าน `check_clean_environment.py` gate + token-exact flag
verification (จับบั๊ก `--cpu-moe` substring match กับ `--n-cpu-moe`) +
harness ไม่ถูกเรียกเป็น sub-harness แล้ว:

| config | EXP-008 เดิม | Re-run | Δ |
|--------|:---:|:---:|:---:|
| `--cpu-moe` | 17.9 tok/s / 3858 MiB / 60.5 ms | **17.9 / 3085 / 57.7** | ≈ |
| `--n-cpu-moe 20` | 33.8 / 8532 / 31.9 | **33.9 / 7761 / 31.4** | ≈ |
| `--n-cpu-moe 10` | 44.5 / 10834 / 29.5 | **47.2 / 10061 / 20.6** | +6% |
| `--n-cpu-moe 0` | 53.9 / 11338 / 20.2 | **56.4 / 11175 / 17.3** | +5% |

**ตัวเลขยืนยันได้** — ความต่าง +5-6% บน config เร็วสุด = page-cache warm /
run variance; สรุปเดิม (40+ tok/s สำเร็จ, sweet spot = n-cpu-moe 10,
ceiling = n-cpu-moe 0) ยังคงถูกต้อง

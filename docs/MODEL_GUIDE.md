# Model Selection Guide — Choosing GGUFs for CPU Inference

> **Purpose:** set honest expectations for generation speed on CPU, and
> document the server's CPU-etiquette features. All measured numbers below
> come from this project's verification runs (2026-07-29 → 2026-07-30).

---

## 1. The one formula that predicts speed

Token generation on CPU is **memory-bandwidth bound**: to produce one token
the engine reads (almost) all model weights from RAM once.

```
tok/s  ≈  effective RAM bandwidth (GB/s)  ÷  weight bytes read per token
```

- **Dense models** read the whole file per token.
- **MoE models** read only the active experts per token — far less than the
  file size. That is why a 5.5 GB MoE can outrun a smaller-looking dense file.

## 2. Measured on this machine

Machine: Intel CPU Family 6 Model 158, 16 logical CPUs, DDR4.
Bandwidth implied by the measurements below: ~23–35 GB/s effective.

| Model | Arch | Quant | File | Read/token | Measured |
|-------|------|-------|------|-----------|----------|
| Qwen1.5-MoE-A2.7B | qwen2-MoE | Q2_K | 5.48 GB | ~1 GB (active experts) | **17.9 tok/s** |
| Ornith 9B | qwen35 (dense) | Q6_K | 7.36 GB | ~7.35 GB | **3–4 tok/s** (user test) |
| Kimi R37 4.2B ("Agents-A1") | qwen35 (dense) | **F16** | 8.42 GB | ~8.4 GB | **2.8 tok/s** (measured 2026-07-30) |

Cross-check — all three points sit on the same bandwidth line:

- Kimi R37: 8.4 GB/token ÷ 2.8 tok/s ≈ **23.5 GB/s** consumed ✓
- Qwen MoE: ~1 GB/token × 17.9 tok/s ≈ **18 GB/s** ✓ (similar order)

**Key insight:** the 4.2B model in F16 reads *more* bytes per token than the
9B model in Q6_K — quantization matters more than parameter count. The 3–4
tok/s seen on both test models is physics, not a bug.

## 3. Recommendations

| Want | Pick | Expected effect |
|------|------|-----------------|
| Fast chat on CPU | **Q4_K_M** GGUF (~0.55 B/param) | ~2.5–3× faster than F16 at near-equal quality (estimate, not measured here) |
| Best quality per GB/s | **Q6_K** | ~15% slower than Q4_K, measurably better quality |
| Avoid on CPU | F32 / F16 / BF16 | 2–4× slower for no perceptible quality gain in chat |

The SPA shows a ⚠️ warning when you select an unquantized (F16/F32/BF16)
file from a scan result.

## 4. CPU etiquette (keeping the machine usable)

Inference threads legitimately saturate the cores they use. The server
mitigates this three ways:

1. **Below-normal process priority** — while any model is loaded, the server
   process runs one Windows priority class below normal (POSIX: nice +5).
   Your browser/desktop/IDE preempt it, so the PC stays responsive; on an
   idle machine throughput is unchanged (the scheduler still hands over
   unused cores). Disable with `WS_LOWER_PRIORITY=0`. Status is reported
   honestly in `GET /v1/stats` → `server.priority`.
2. **Thread control** — the Models tab exposes **THR** per load; empty =
   server default (`WS_N_THREADS`, default: half of logical cores). Fewer
   threads → slower generation but lighter machine load.
3. **Thinking/answer separation** — thinking models (Qwen3.5 family etc.)
   emit ` think ` blocks; the SPA folds them into a collapsible "💭
   Thinking" panel above the real answer. Note: thinking models also
   *generate far more tokens* (the reasoning chain), so wall-clock time to
   a useful answer can be many× the visible answer length — collapsing the
   panel makes this legible even when tok/s is low.

## 5. Environment variables (server)

| Variable | Default | Meaning |
|----------|---------|---------|
| `WS_N_THREADS` | half of logical CPUs | Default inference threads per model |
| `WS_LOWER_PRIORITY` | `1` | Run below-normal priority while a model is loaded |
| `WS_BUFFER_MB` | `64` | Streaming buffer size |
| `WS_N_CTX` | `2048` | Default context window |
| `WS_IDLE_TIMEOUT` | `0` (keep loaded) | Seconds before idle unload; 0 = never |
| `WS_MODELS_DIR` | — | Extra directory for `/v1/models/scan` |

Scan defaults also include the Jan Desktop model store
(`%APPDATA%\Jan\data\llamacpp\models`) on Windows.

---

*Raw measurements: `docs/verification/cpu_attribution_2026-07-30.json`,
`docs/verification/spike_page_faults_2026-07-30.json`.*

# weight-streaming

**Run LLMs larger than your RAM using NVMe as extension of memory.**

`weight-streaming` is a Python library that enables running large language models (100B–3T+ parameters) on consumer hardware with 32–64 GB RAM. It uses speculative weight streaming to predictively load expert weights from NVMe storage during inference, keeping only hot shards in memory.

## How it works

Large models (especially MoE) only use a fraction of their parameters per token. `weight-streaming` exploits this by:

1. **Memory-mapping** the model file (zero-copy access, no redundant loading)
2. **Tracking** which weight shards are hot via an LRU buffer
3. **Predicting** which experts will be needed next using heuristic patterns
4. **Prefetching** predicted shards from NVMe during compute time (overlapping I/O with inference)
5. **Monitoring** OS page cache residency via Windows API (QueryWorkingSetEx)

## Quick Start

```bash
# Install with llama-cpp-python support
pip install weight-streaming[llama-cpp]

# Or install minimal (GPU-less stats only)
pip install weight-streaming
```

### Generate text

```bash
python -m weight_stream run model.gguf --prompt "The future of AI is" --max-tokens 128
```

### Show model info

```bash
python -m weight_stream stats model.gguf
```

### Benchmark throughput

```bash
python -m weight_stream benchmark model.gguf --max-tokens 256
```

## Python API

```python
from weight_stream import WeightStreamModel

# Load model with 64 MB streaming buffer
model = WeightStreamModel(
    "model.gguf",
    buffer_mb=64,     # LRU buffer size (default: 64 MB)
    n_ctx=512,        # context window
)

# Generate with speculative weight prefetch
output = model.generate(
    "The capital of France is",
    max_tokens=100,
    temperature=0.7,
)

# Get performance statistics
stats = model.get_stats()
print(f"Hits: {stats['buffer']['hit_rate']:.1%}")
print(f"Page cache: {stats['page_cache']['resident_ratio']:.1%}")

# Clean up
model.close()

# Or use context manager
with WeightStreamModel("model.gguf", buffer_mb=64) as model:
    output = model.generate("Hello", max_tokens=50)
```

## CLI Reference

```
usage: weight-streaming [-h] [--version] {run,stats,benchmark} ...

Run LLMs larger than your RAM — speculative weight streaming from NVMe

Commands:
  run          Generate text with weight streaming
  stats        Show model metadata and buffer configuration
  benchmark    Benchmark generation throughput
```

### `run`

```
python -m weight_stream run <model> [options]

Options:
  -p, --prompt TEXT       Input prompt (default: "Hello")
  -n, --max-tokens INT    Maximum tokens to generate (default: 128)
  -b, --buffer-mb INT     Buffer size in MB (default: 64)
  -t, --temperature FLOAT Sampling temperature 0.0-2.0 (default: 0.7)
  -v, --verbose           Enable debug logging
  -j, --json              Output as JSON
```

### `stats`

```
python -m weight_stream stats <model> [options]

Options:
  -b, --buffer-mb INT     Buffer size for estimation (default: 64)
```

### `benchmark`

```
python -m weight_stream benchmark <model> [options]

Options:
  -b, --buffer-mb INT     Buffer size in MB (default: 64)
  -n, --max-tokens INT    Tokens for measurement (default: 256)
  --no-warmup              Skip warmup phase
  -j, --json               Output as JSON
```

## Architecture

```
┌─────────────────────────────────────────────────────┐
│  User Code                                          │
│  from weight_stream import WeightStreamModel         │
└────────────────────────┬────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────┐
│  WeightStreamModel (backends/llama_cpp.py)           │
│  ┌────────────────────────────────────────────────┐ │
│  │  StreamingBuffer  (core/buffer.py)             │ │
│  │  • LRU eviction (64 MB default)                │ │
│  │  • Shard-based tracking (4 MB shards)          │ │
│  │  • Hit/miss stats + zero-copy mmap access      │ │
│  └────────────────────────────────────────────────┘ │
│  ┌────────────────────────────────────────────────┐ │
│  │  Prefetcher      (core/prefetcher.py)          │ │
│  │  • Background thread + queue                   │ │
│  │  • Expert-aware prefetch (GGUF metadata)       │ │
│  │  • Staggered confidence loading                │ │
│  └────────────────────────────────────────────────┘ │
│  ┌────────────────────────────────────────────────┐ │
│  │  HeuristicPredictor (core/predictor.py)        │ │
│  │  • Sequential pattern detection                │ │
│  │  • Co-occurrence tracking                      │ │
│  └────────────────────────────────────────────────┘ │
│  ┌────────────────────────────────────────────────┐ │
│  │  WindowsPageMonitor (io/win_perf.py)            │ │
│  │  • QueryWorkingSetEx page sampling             │ │
│  │  • Reports resident ratio in physical RAM      │ │
│  └────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────┘
```

## Requirements

- **Python** ≥ 3.11
- **OS**: Windows (Linux/macOS planned)
- **RAM**: 32–64 GB (for models >100 GB)
- **Storage**: NVMe SSD recommended (any drive works)
- **Optional**: `llama-cpp-python` ≥ 0.3.0 (for inference)

## Supported Models

| Model | Type | Params | Experts | Active |
|-------|------|--------|---------|--------|
| Kimi K3 | MoE | 2.8T | 896 | 16 |
| Qwen1.5-MoE-A2.7B | MoE | 2.7B | 60 | 2 |
| Mixtral 8x7B | MoE | 47B | 8 | 2 |
| Dense models (any) | Dense | any | N/A | all |

The abstraction layer supports both MoE and Dense architectures. For dense models, prefetch focuses on sequential layer access.

## License

MIT

## Research

This project is based on research into speculative decoding, MoE routing prediction, out-of-core execution, and near-storage computing. See the [research](/research) directory for details.

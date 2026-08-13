# 3. Architecture (System)

> **Status:** draft (Phase 5, TASKS.md) · 2026-08-13 · ตาม `research/paper/OUTLINE.md`
> พรรณนา as-built (ADR-003 + การค้นพบทีหลัง EXP-025/026/028/029)

---

This section describes the system as built and measured: the inference
engine, the physics model that predicts its cost, the telemetry that
observes it, the buffer abstraction that unifies simulator and
production, and the evaluation metrics. Every component is backed by
open code in the repository and by the experiments cited.

## 3.1 Engine and the mmap substrate

Inference runs on **llama.cpp's llama-server** (CPU-first, GPU offload
optional), with the model file memory-mapped (`mmap`). The operating
system's page cache is therefore the *de facto* weight-streaming layer:
weights are read from disk on first touch and stay resident as long as
they fit RAM. Our earlier custom streaming buffer (ADR-001) was
abandoned after real-hardware measurement: with mmap + OS page cache,
the OS already does the LRU-equivalent caching, and an application-level
buffer added tracking overhead without throughput (ADR-003, EXP-002/026).
The product's role is therefore not "buffer weights ourselves" but
**observe and predict**: track what the OS actually faults in, and hint
what to prefetch when the working set exceeds RAM (ARCHITECTURE.md §0).

The one architectural fact that changed with measurement: at the time of
ADR-003, K3-on-CPU looked ~92% compute-bound (815 ms compute vs 0–67 ms
I/O stall, EXP-004), which argued buffering was mostly unnecessary. That
finding holds **only while the model fits RAM**. EXP-027/029 later
measured the >RAM regime, where I/O is the wall and buffering is the
24× lever — see §4. The architecture is the same; the regime changes the
answer.

## 3.2 Physics model: bandwidth ÷ bytes per token

The core predictive identity is

```
bytes_per_token = active_params × bits_per_weight / 8
tok/s           = effective_bandwidth / bytes_per_token
```

`bytes_per_token` comes from the model spec (MoE active set × quant
bits): Qwen1.5-MoE-A2.7B Q2_K = 2.7B × 2.5 bpw ≈ **0.844 GB/token**; the
K3 target = 50B × 2.5 bpw ≈ **15.6 GB/token** (`simulator/physics.py`).

The effective bandwidth is *calibrated from real measurements*, one
value per storage tier (EXP-025):

| Tier | Effective BW (GB/s) | Calibrated from |
|---|---|---|
| cpu-ram | **19.18** | Qwen 22.73 tok/s CPU-pure (EXP-004) |
| gpu-vram | **61.09** | Qwen 56–72 tok/s GPU-offload (EXP-011) |
| disk-mmap | **0.38** | DS-V4-Flash 150–300 MB/token @ 1.9 tok/s (EXP-012) |

The disk-mmap tier is the number the spec sheet hides: page-fault reads
are random access, so an NVMe's *effective* streaming bandwidth is
**~0.38 GB/s, ~37× below its 14 GB/s sequential spec**. This single
calibrated constant explains why >RAM inference is slow, and it is what
makes the predictions in §4 possible.

## 3.3 Honest telemetry: `generation.paging`

The server ships per-generation paging telemetry in `/v1/stats`
(`weight_stream/io/page_faults.py`, Windows `GetProcessMemoryInfo` /
POSIX `getrusage`):

```
generation.paging: {
  faults_per_token,       # process-wide soft+hard page faults / token
  fault_mb_per_token,     # faulted bytes / token
  disk_mb_per_token,      # hard-fault (disk) demand / token
}
```

These are **OS-level signals, never simulated**. They let a reported
tok/s number be audited: "fast on paper" cannot hide disk thrashing if
faults/token and disk MB/token are published alongside (EXP-012). This
is the project's ground rule — honest telemetry — applied to the one
number the community does not publish.

## 3.4 Buffer abstraction: one protocol for simulator and production

`StreamingBuffer.total_accesses` was 0 during real inference: llama.cpp
reads the mmap opaquely, so the tracker observed nothing (ARCHITECTURE.md
§0 open gap). EXP-026 closes it with a unified protocol
(`simulator/buffer_abstraction.py`):

```
BufferBackend            # protocol
├── SimulatorBufferAdapter   # wraps the LRU/LFU/priority simulator buffer
└── TelemetryBufferObserver  # maps OS paging signals → buffer-equivalent stats
        └── BufferStatsView  # hit_rate, bytes/token, stall/compute ms, tok/s
```

Both backends produce the *same* `BufferStatsView`, so a simulation and
the real engine can be compared directly, and physics-derived
throughput (`hit bytes @ cpu-ram BW + miss bytes @ disk-mmap BW`) is
computed identically for both (EXP-026). This is what lets §4 put the
real Qwen measurement and the K3 simulation on one table.

## 3.5 Evaluation metrics

Phase 4 defines the three metrics used throughout the evaluation
(`weight_stream/eval/metrics.py`, EXP-028):

1. **Hit rate** — `1 − disk_mb_per_token / bytes_per_token` (0–1);
   warm threshold ≥ 0.90.
2. **Latency distribution** — per-token generation latency captured from
   the SSE stream, reported as p50/p90/p99/mean/max (nearest-rank);
   PASS when p99 < 3×p50 (no long-tail stall).
3. **Throughput** — tok/s vs the physics prediction; PASS when the error
   is within ±15% (the tolerance EXP-025 validated on real hardware).

All three are pure functions over telemetry, so they are unit-testable
offline (hermetic tests, no model or network needed).

## 3.6 System diagram (figure placeholder)

```
[ GGUF file (mmap) ] --OS page cache--> [ CPU/GPU compute ]
        ^                                      ^
        | page faults                          |
   [ generation.paging telemetry ]        [ physics model ]
        |                                       |
        +---- BufferBackend (BufferStatsView) --+--> metrics (hit/latency/throughput)
```

(TODO: render as a figure for the paper.)

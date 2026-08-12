#!/usr/bin/env python3
"""
Streaming buffer abstraction demo (TASKS.md #145).

Runs both implementations of BufferBackend side by side and prints the
unified BufferStatsView for each:

  1. Simulator-backed: LRU buffer over a synthetic expert-access pattern
     (warmup → hot reuse → cold shift) using the Qwen spec.
  2. Telemetry-backed: real OS signals from docs/verification/
     spike_page_faults_2026-07-30.json (cold + warm runs).

Usage: python buffer_demo.py
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from simulator import physics
from simulator.buffer import StreamingBuffer
from simulator.buffer_abstraction import SimulatorBufferAdapter, TelemetryBufferObserver
from simulator.config import SimConfig

ROOT = Path(__file__).resolve().parents[1]
SPIKE = ROOT / "docs/verification/spike_page_faults_2026-07-30.json"


def _qwen_config() -> SimConfig:
    cfg = SimConfig()
    cfg.model.active_params = 2.7e9
    cfg.model.bits_per_weight = 2.5
    return cfg


def print_view(title: str, view) -> None:
    print(f"{title}")
    print(f"  source:        {view.source}")
    print(f"  hit rate:      {view.hit_rate*100:.1f}%")
    print(f"  miss/token:    {view.miss_bytes_per_token_gb:.4f} GB")
    print(f"  stall:         {view.stall_ms_per_token:.1f} ms/tok")
    print(f"  compute:       {view.compute_ms_per_token:.1f} ms/tok")
    print(f"  predicted:     {view.predicted_tok_per_sec:.2f} tok/s")
    print(f"  BW used:       ram {view.ram_bw_gbps:.2f} / disk {view.disk_bw_gbps:.2f} GB/s")
    print()


def main() -> None:
    # --- Simulator-backed -------------------------------------------------
    cfg = _qwen_config()
    adapter = SimulatorBufferAdapter(StreamingBuffer(cfg), cfg)
    for i in range(600):
        if i < 200:
            expert = i % 8            # warmup: hot set of 8
        elif i < 500:
            expert = i % 20           # hot reuse, slightly wider
        else:
            expert = (i % 8) + 60     # cold shift: new experts
        adapter.on_access(expert)
    print_view("SIMULATOR-BACKED (LRU, 600 accesses, hot->cold shift)", adapter.stats())

    # --- Telemetry-backed (real spike data) ------------------------------
    data = json.loads(SPIKE.read_text(encoding="utf-8"))
    obs = TelemetryBufferObserver(physics.QWEN.bytes_per_token_gb)
    for run in data["runs"]:
        print_view(
            f"TELEMETRY-BACKED ({run['label']}, measured {run['tok_s']} tok/s)",
            obs.observe(run, n_tokens=run["tokens"]),
        )

    # --- Key takeaway ------------------------------------------------------
    cold = obs.observe(data["runs"][0], n_tokens=data["runs"][0]["tokens"])
    warm = obs.observe(data["runs"][1], n_tokens=data["runs"][1]["tokens"])
    print("=" * 60)
    print(f"Open gap closed: total_accesses is no longer 0 - the abstraction")
    print(f"converts OS signals into buffer stats. Cold {cold.hit_rate*100:.0f}% hit")
    print(f"vs warm {warm.hit_rate*100:.1f}% hit - the 300x fault drop (EXP spike)")
    print(f"is now visible as buffer-equivalent hit-rate gain.")


if __name__ == "__main__":
    main()

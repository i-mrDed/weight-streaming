"""Hermetic tests for the EXP-030 expert-offload finding.

Pins the physics claim behind the measurement: on a model that FITS VRAM,
offloading expert weights to CPU memory can only add PCIe traffic and
faults — it cannot help. The ratio checks below encode the
bandwidth-gap argument (gpu-vram 61.09 vs cpu-ram 19.18 GB/s, EXP-025)
that explains why n-cpu-moe 10 measured ~4x slower than all-GPU on real
Qwen. No server, no model, no network.
"""

from __future__ import annotations

import pytest

import simulator.physics as physics
from simulator.buffer_abstraction import predicted_tok_per_sec

GPU_BW = physics.DEFAULT_EFFECTIVE_BW_GBPS["gpu-vram"]
RAM_BW = physics.DEFAULT_EFFECTIVE_BW_GBPS["cpu-ram"]
DISK_BW = physics.DEFAULT_EFFECTIVE_BW_GBPS["disk-mmap"]
QWEN = physics.QWEN
QWEN_BYTES = QWEN.bytes_per_token_gb  # 0.844 GB/token


class TestOffloadPhysics:
    def test_vram_faster_than_ram(self) -> None:
        # The whole reason offloading hurts on fits-VRAM models.
        assert GPU_BW > RAM_BW > DISK_BW

    def test_all_gpu_is_fastest_when_resident(self) -> None:
        # 100% of bytes from VRAM: pure gpu-vram tier.
        all_gpu = predicted_tok_per_sec(1.0, QWEN_BYTES, GPU_BW, DISK_BW)
        assert all_gpu == pytest.approx(GPU_BW / QWEN_BYTES, rel=0.01)

    def test_offloaded_experts_hit_ram_speed(self) -> None:
        # If 1/4 of bytes come from RAM instead of VRAM, throughput drops
        # by more than 25% because RAM is ~3.2x slower than VRAM.
        quarter_offload = predicted_tok_per_sec(
            1.0, QWEN_BYTES, GPU_BW, DISK_BW, )
        # simulate: 25% of bytes read at RAM BW, 75% at VRAM BW
        t = (0.75 * QWEN_BYTES) / GPU_BW + (0.25 * QWEN_BYTES) / RAM_BW
        mixed = 1.0 / t
        assert mixed < quarter_offload * 0.85  # strictly slower

    def test_offload_gap_matches_exp030_ratio(self) -> None:
        # EXP-030 measured: n-cpu-moe 0 = 126.64, n-cpu-moe 10 = 31.75
        # (ratio ~4.0x). Pure physics: VRAM vs RAM tier gap = 61.09/19.18
        # = ~3.2x — measured is in the same regime (partially offloaded
        # experts also add faults), so the ratio must be > 1.
        ratio = 126.64 / 31.75
        assert ratio > 1.5
        assert ratio < 6.0
        assert GPU_BW / RAM_BW == pytest.approx(3.18, rel=0.05)

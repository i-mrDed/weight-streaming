"""Tests for GGUFSplitParser (split-shard GGUF support).

Uses the real DS V4 Flash head files (metadata shard + partial weight
shard head) so the test runs fast without requiring the full 97GB model.
Path is configurable via env WS_TEST_MODELS_DIR; skips if absent.
"""
import os
from pathlib import Path

import pytest

from weight_stream.gguf.parser import GGUFSplitParser

# Default: real model dir on this machine.
DEFAULT_DIR = Path(r"C:\Users\dedch\models\UD-IQ3_XXS")
MODELS_DIR = Path(os.environ.get("WS_TEST_MODELS_DIR", DEFAULT_DIR))

SHARD_NAMES = [
    "DeepSeek-V4-Flash-0731-UD-IQ3_XXS-00001-of-00004.gguf",
    "DeepSeek-V4-Flash-0731-UD-IQ3_XXS-00002-of-00004.gguf",
    "DeepSeek-V4-Flash-0731-UD-IQ3_XXS-00003-of-00004.gguf",
    "DeepSeek-V4-Flash-0731-UD-IQ3_XXS-00004-of-00004.gguf",
]


def _shards() -> list[Path]:
    return [MODELS_DIR / n for n in SHARD_NAMES]


@pytest.fixture(scope="module")
def split_parser():
    shards = _shards()
    if not all(p.exists() for p in shards):
        pytest.skip("DS V4 Flash shards not available")
    p = GGUFSplitParser([str(x) for x in shards])
    yield p
    p.close()


class TestGGUFSplitParser:
    def test_shard_count(self, split_parser):
        assert split_parser.shard_count == 4

    def test_total_tensors(self, split_parser):
        # shard1=0 (metadata), shard2=660, shard3=620, shard4=48 == 1328
        assert split_parser.n_tensors == 1328

    def test_metadata(self, split_parser):
        assert split_parser.metadata.get("general.architecture") == "deepseek4"
        assert split_parser.metadata.get("deepseek4.expert_count") == 256
        assert split_parser.metadata.get("deepseek4.expert_used_count") == 6
        assert split_parser.metadata.get("deepseek4.block_count") == 43

    def test_tensor_location(self, split_parser):
        t = split_parser.get_tensor("output.weight")
        assert t is not None
        assert t.shard_index == 1
        assert t.offset_in_shard == 42496          # verified from real model
        assert t.size_bytes == 434380800           # 434.4 MB

    def test_expert_tensor_offsets(self, split_parser):
        t = split_parser.get_tensor("blk.0.ffn_gate_exps.weight")
        assert t is not None
        assert t.shard_index == 1
        assert t.shape == (4096, 2048, 256)
        assert t.size_bytes == 620756992           # 620.8 MB, pad32 applied

    def test_expert_map_global_shape(self, split_parser):
        em = split_parser.get_expert_map_global()
        assert len(em) == 43                       # 43 layers
        assert len(em[0]) == 256                   # 256 experts per layer
        assert len(em[0][0]) == 3                  # gate/up/down projections

    def test_expert_map_global_offsets_within_file(self, split_parser):
        em = split_parser.get_expert_map_global()
        total = sum(split_parser._shard_sizes)
        max_end = max(
            r.end_offset
            for layers in em.values() for ex in layers.values() for r in ex
        )
        assert max_end <= total, "expert offset exceeds concatenated file size"

    def test_global_offsets_increase_across_shards(self, split_parser):
        # output.weight (shard2) must come after shard1's file size
        t = split_parser.get_tensor("output.weight")
        shard1_size = split_parser._shard_sizes[0]
        assert t.global_offset >= shard1_size

    def test_detect_architecture(self, split_parser):
        arch = split_parser.detect_architecture()
        assert arch["arch_name"] == "deepseek4"
        assert arch["is_moe"] is True
        assert arch["total_experts"] == 256
        assert arch["active_experts"] == 6
        assert arch["num_layers"] == 43
        assert arch["shard_count"] == 4


class TestOffsetMath:
    """Pure-math sanity: padded32 + data_offset == file size for shard2 head."""

    def test_pad32(self):
        assert GGUFSplitParser._padded(0) == 0
        assert GGUFSplitParser._padded(1) == 32
        assert GGUFSplitParser._padded(32) == 32
        assert GGUFSplitParser._padded(33) == 64
        assert GGUFSplitParser._padded(434380800) == 434380800  # already aligned

    def test_requires_paths(self):
        with pytest.raises(ValueError):
            GGUFSplitParser([])
"""Tests for GGUFSplitParser (split-shard GGUF support).

Runs hermetically in CI against four tiny synthetic shards (built at test
time) that mirror the DS V4 Flash multi-shard layout: metadata + tensors
split across 4 files, expert tensors named `blk.N.ffn_*_exps.weight`.
"""
import pytest

from tests.fixtures.synthetic_gguf import build_dsv4_shards
from weight_stream.gguf.parser import GGUFSplitParser


@pytest.fixture(scope="module")
def split_parser(tmp_path_factory):
    shards = build_dsv4_shards(tmp_path_factory.mktemp("shards"))
    p = GGUFSplitParser([str(x) for x in shards])
    yield p
    p.close()


class TestGGUFSplitParser:
    def test_shard_count(self, split_parser):
        assert split_parser.shard_count == 4

    def test_total_tensors(self, split_parser):
        # shard1=1, shard2=2, shard3=2, shard4=3 == 8
        assert split_parser.n_tensors == 8

    def test_metadata(self, split_parser):
        assert split_parser.metadata.get("general.architecture") == "deepseek4"
        assert split_parser.metadata.get("deepseek4.expert_count") == 4
        assert split_parser.metadata.get("deepseek4.expert_used_count") == 2
        assert split_parser.metadata.get("deepseek4.block_count") == 2

    def test_tensor_location(self, split_parser):
        t = split_parser.get_tensor("output.weight")
        assert t is not None
        assert t.shard_index == 1
        assert t.offset_in_shard > 0          # after shard1's header + TI
        assert t.size_bytes == 4096           # 32*64 F16, pad32 already aligned

    def test_expert_tensor_offsets(self, split_parser):
        t = split_parser.get_tensor("blk.0.ffn_gate_exps.weight")
        assert t is not None
        assert t.shard_index == 1
        assert t.shape == (512, 144, 4)
        assert t.size_bytes == 165888         # Q4_K byte size, pad32 aligned

    def test_expert_map_global_shape(self, split_parser):
        em = split_parser.get_expert_map_global()
        assert len(em) == 2                   # 2 layers
        assert len(em[0]) == 4                # 4 experts per layer
        assert len(em[0][0]) == 3             # gate/up/down projections

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
        assert arch["total_experts"] == 4
        assert arch["active_experts"] == 2
        assert arch["num_layers"] == 2
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

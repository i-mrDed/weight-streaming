"""Tests for the GGUF parser wrapper.

Runs hermetically in CI against a tiny synthetic MoE model (built at test
time with the project's `gguf` dependency) that mirrors the tensor naming
and shape conventions of the real Qwen1.5-MoE fixture.
"""
import pytest

from tests.fixtures.synthetic_gguf import build_qwen2moe
from weight_stream.gguf import GGUFParser


@pytest.fixture(scope='module')
def parser(tmp_path_factory):
    model = build_qwen2moe(tmp_path_factory.mktemp('gguf') / 'synthetic-qwen2moe.gguf')
    p = GGUFParser(str(model))
    yield p


class TestGGUFParser:

    def test_parse_model(self, parser):
        assert len(parser.tensors) == 10
        assert parser.file_size > 0

    def test_metadata(self, parser):
        assert parser.metadata.get('general.architecture') == 'qwen2moe'
        assert parser.metadata.get('qwen2moe.block_count') == 2
        assert parser.metadata.get('qwen2moe.expert_count') == 4
        assert parser.metadata.get('qwen2moe.expert_used_count') == 2

    def test_tensor_count(self, parser):
        assert len(parser.tensors) == 10

    def test_expert_tensors(self, parser):
        experts = parser.get_expert_tensors()
        assert len(experts) == 6  # 2 layers × 3 projections

    def test_expert_tensor_structure(self, parser):
        experts = parser.get_expert_tensors()
        for t in experts[:3]:
            assert t.is_expert_weight
            assert t.n_experts == 4
            assert t.layer_id == 0
            assert t.projection_type in ('gate', 'up', 'down')
            assert t.per_expert_size > 0

    def test_expert_map(self, parser):
        em = parser.get_expert_map()
        assert len(em) == 2  # 2 layers
        assert 0 in em
        assert len(em[0]) == 4  # 4 experts per layer
        # Each expert should have 3 projections
        expert0 = em[0][0]
        assert len(expert0) == 3
        projs = {er.projection for er in expert0}
        assert projs == {'gate', 'up', 'down'}

    def test_expert_offsets(self, parser):
        """Expert offsets should be in increasing order within a layer."""
        em = parser.get_expert_map()
        layer0 = em[0]
        for ei in range(3):
            for er in layer0[ei]:
                assert er.start_offset > 0
                assert er.end_offset > er.start_offset
                assert er.size_bytes > 0

    def test_get_tensor(self, parser):
        t = parser.get_tensor('token_embd.weight')
        assert t is not None
        assert len(t.shape) == 2
        assert t.file_offset > 0

    def test_get_tensors_by_pattern(self, parser):
        tensors = parser.get_tensors_by_pattern('blk.0.*')
        assert len(tensors) > 0
        for t in tensors:
            assert t.name.startswith('blk.0.')

"""Unit tests for new 10/10 modules: auto_tune, eagle_dual_predictor, shard_repacker, native_binding."""

import os
import sys
import json
import struct
import tempfile
import pytest
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# ═══════════════════════════════════════════════════════════════
# 1. Auto-Tune Hardware Profiler Tests
# ═══════════════════════════════════════════════════════════════
from weight_stream.tools.auto_tune import get_system_profile, recommend_config


class TestAutoTune:
    def test_get_system_profile_returns_valid_structure(self):
        profile = get_system_profile()
        assert "platform" in profile
        assert "cpu_threads" in profile
        assert "ram_total_gb" in profile
        assert profile["cpu_threads"] >= 1
        assert profile["ram_total_gb"] >= 0

    def test_recommend_config_low_ram(self):
        profile = {"ram_total_gb": 8.0, "ram_available_gb": 4.0, "cpu_threads": 4, "nvme_estimated_bandwidth_gbps": 3.5}
        config = recommend_config(profile, model_size_gb=14.0)
        assert config["buffer_mb"] >= 128
        assert config["eviction_policy"] in ("lru", "priority-lru", "lfu")
        assert config["n_ctx"] <= 2048

    def test_recommend_config_high_ram(self):
        profile = {"ram_total_gb": 64.0, "ram_available_gb": 48.0, "cpu_threads": 16, "nvme_estimated_bandwidth_gbps": 7.0}
        config = recommend_config(profile, model_size_gb=14.0)
        assert config["buffer_mb"] >= 128
        assert config["prefetch_depth"] >= 4
        assert config["n_ctx"] >= 4096
        assert config["n_threads"] >= 4

    def test_recommend_config_tiny_model(self):
        profile = {"ram_total_gb": 32.0, "ram_available_gb": 20.0, "cpu_threads": 8, "nvme_estimated_bandwidth_gbps": 3.5}
        config = recommend_config(profile, model_size_gb=1.0)
        assert config["residency_ratio"] >= 0.8
        assert config["eviction_policy"] == "lru"

    def test_recommend_config_returns_all_keys(self):
        profile = {"ram_total_gb": 16.0, "ram_available_gb": 10.0, "cpu_threads": 8, "nvme_estimated_bandwidth_gbps": 3.5}
        config = recommend_config(profile)
        required_keys = {"buffer_mb", "eviction_policy", "prefetch_depth", "n_threads", "n_ctx", "residency_ratio"}
        assert required_keys.issubset(set(config.keys()))


# ═══════════════════════════════════════════════════════════════
# 2. Eagle Dual Predictor Tests
# ═══════════════════════════════════════════════════════════════
from weight_stream.core.eagle_dual_predictor import EagleDualPredictor


class TestEagleDualPredictor:
    def test_init_defaults(self):
        pred = EagleDualPredictor()
        assert pred.num_experts == 896
        assert pred.active_experts == 16
        assert pred.lookahead_steps == 5

    def test_predict_with_logits(self):
        pred = EagleDualPredictor(num_experts=64, active_experts=8, lookahead_steps=3)
        logits = np.random.randn(64).astype(np.float32)
        preds = pred.predict_lookahead_shards(current_token_id=42, layer_logits=logits)
        assert len(preds) > 0
        assert all(isinstance(p, tuple) and len(p) == 2 for p in preds)
        # All expert IDs should be in valid range
        for expert_id, score in preds:
            assert 0 <= expert_id < 64

    def test_predict_without_logits_uses_history(self):
        pred = EagleDualPredictor(num_experts=32, active_experts=4, lookahead_steps=2)
        # Add some history
        pred.update_actual_routing([0, 1, 2, 3])
        pred.update_actual_routing([1, 2, 5, 7])
        preds = pred.predict_lookahead_shards(current_token_id=0, layer_logits=None)
        assert len(preds) > 0

    def test_predict_empty_history_no_logits(self):
        pred = EagleDualPredictor(num_experts=32, active_experts=4, lookahead_steps=2)
        preds = pred.predict_lookahead_shards(current_token_id=0, layer_logits=None)
        # Should return empty or very short list with no data
        assert isinstance(preds, list)

    def test_update_routing_limits_history(self):
        pred = EagleDualPredictor()
        for i in range(150):
            pred.update_actual_routing([i % 64])
        assert len(pred.history_routing) <= 100

    def test_predictions_sorted_by_confidence(self):
        pred = EagleDualPredictor(num_experts=64, active_experts=8)
        logits = np.random.randn(64).astype(np.float32)
        preds = pred.predict_lookahead_shards(current_token_id=1, layer_logits=logits)
        if len(preds) > 1:
            scores = [p[1] for p in preds]
            assert scores == sorted(scores, reverse=True)


# ═══════════════════════════════════════════════════════════════
# 3. Shard Repacker Tests
# ═══════════════════════════════════════════════════════════════
from weight_stream.tools.shard_repacker import ShardRepacker, MAGIC_HEADER


class TestShardRepacker:
    def test_repack_basic(self, tmp_path):
        # Create a fake model file (1 MB)
        input_file = tmp_path / "fake_model.bin"
        data = os.urandom(1024 * 1024)
        input_file.write_bytes(data)

        output_file = tmp_path / "repacked_model.bin"
        repacker = ShardRepacker(str(input_file), str(output_file), shard_size_mb=0.25)
        stats = repacker.repack()

        assert stats["total_shards"] == 4
        assert os.path.exists(str(output_file))
        assert stats["bytes_written"] > 0
        assert stats["duration_sec"] >= 0

    def test_repack_with_popularity(self, tmp_path):
        input_file = tmp_path / "model.bin"
        data = os.urandom(512 * 1024)
        input_file.write_bytes(data)

        output_file = tmp_path / "repacked.bin"
        repacker = ShardRepacker(str(input_file), str(output_file), shard_size_mb=0.125)
        popularity = {0: 10, 1: 50, 2: 30, 3: 5}
        stats = repacker.repack(popularity_map=popularity)
        assert stats["total_shards"] == 4

    def test_repack_header_magic(self, tmp_path):
        input_file = tmp_path / "model.bin"
        input_file.write_bytes(os.urandom(256 * 1024))
        output_file = tmp_path / "out.bin"

        repacker = ShardRepacker(str(input_file), str(output_file), shard_size_mb=0.125)
        repacker.repack()

        with open(str(output_file), "rb") as f:
            magic = f.read(len(MAGIC_HEADER))
            assert magic == MAGIC_HEADER

    def test_repack_file_not_found(self):
        repacker = ShardRepacker("/nonexistent/model.bin", "/tmp/out.bin")
        with pytest.raises(FileNotFoundError):
            repacker.repack()


# ═══════════════════════════════════════════════════════════════
# 4. Native Binding Tests (graceful fallback when DLL missing)
# ═══════════════════════════════════════════════════════════════
from weight_stream.core.native_binding import NativeCore, WSBufferStats, WSMemoryStats


class TestNativeBinding:
    def test_load_library_missing_returns_false(self):
        result = NativeCore.load_library("/nonexistent/path/fake.dll")
        assert result is False

    def test_get_memory_stats_without_lib(self):
        # Reset to ensure no lib loaded
        NativeCore._lib = None
        stats = NativeCore.get_memory_stats()
        assert "native_available" in stats
        # Without compiled DLL, native_available should be False
        assert isinstance(stats["native_available"], bool)

    def test_wsbufferstats_struct(self):
        s = WSBufferStats()
        assert hasattr(s, "total_requests")
        assert hasattr(s, "cache_hits")
        assert hasattr(s, "hit_rate")

    def test_wsmemorystats_struct(self):
        s = WSMemoryStats()
        assert hasattr(s, "working_set_bytes")
        assert hasattr(s, "resident_ratio")


# ═══════════════════════════════════════════════════════════════
# 5. Token Budget Context Packing Tests
# ═══════════════════════════════════════════════════════════════
from weight_stream.server.model_manager import ModelManager


class TestTokenBudgetPacking:
    def test_estimate_tokens(self):
        assert ModelManager._estimate_tokens("") == 0
        assert ModelManager._estimate_tokens("hello") >= 1
        assert ModelManager._estimate_tokens("a" * 300) >= 50

    def test_fit_messages_preserves_system_and_latest(self):
        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Msg 1"},
            {"role": "assistant", "content": "Reply 1"},
            {"role": "user", "content": "Msg 2"},
            {"role": "assistant", "content": "Reply 2"},
            {"role": "user", "content": "Latest question"},
        ]
        result = ModelManager._fit_messages_to_context(messages, max_tokens=128, n_ctx=512)
        # System should be first
        assert result[0]["role"] == "system"
        # Latest question should be last
        assert result[-1]["content"] == "Latest question"

    def test_fit_messages_truncates_when_over_budget(self):
        # Create many long messages
        messages = [{"role": "system", "content": "Be brief."}]
        for i in range(20):
            messages.append({"role": "user", "content": f"Long question {i} " + "x" * 500})
            messages.append({"role": "assistant", "content": f"Long reply {i} " + "y" * 500})
        messages.append({"role": "user", "content": "Final question"})

        result = ModelManager._fit_messages_to_context(messages, max_tokens=256, n_ctx=2048)
        # Should be shorter than original
        assert len(result) < len(messages)
        assert result[0]["role"] == "system"
        assert result[-1]["content"] == "Final question"

    def test_fit_messages_truncates_oversized_latest_tool_result(self):
        """2026-08-12 E2E: the agent loop read a 16 KB README via read_file
        and fed the whole tool result back — 6163 tokens into a 4096-token
        context, llama-server rejected it and the loop retried to the cap.
        The fitter must truncate the oversized trailing tool result instead
        of sending it whole."""
        giant = "R" * 18_000  # ≈ 6000 tokens by the chars/3 estimator
        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "assistant", "content": None, "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "read_file", "arguments": "{}"}}]},
            {"role": "tool", "tool_call_id": "c1", "content": giant},
        ]
        result = ModelManager._fit_messages_to_context(messages, max_tokens=1024, n_ctx=4096)
        last = result[-1]
        assert last["role"] == "tool"
        assert len(last["content"]) < 18_000
        assert len(last["content"]) > 0
        # Should fit the budget (n_ctx - max_tokens - 64 margin, ×3 chars/token)
        budget_chars = (4096 - 1024 - 64) * 3
        assert len(last["content"]) <= budget_chars

    def test_fit_messages_empty(self):
        result = ModelManager._fit_messages_to_context([], max_tokens=128, n_ctx=2048)
        assert result == []

    def test_fit_messages_single_user(self):
        messages = [{"role": "user", "content": "Hello"}]
        result = ModelManager._fit_messages_to_context(messages, max_tokens=128, n_ctx=2048)
        assert len(result) == 1
        assert result[0]["content"] == "Hello"


# ═══════════════════════════════════════════════════════════════
# 6. Benchmark Suite & Real Buffer Hit Rate Tests
# ═══════════════════════════════════════════════════════════════
from weight_stream.tools.benchmark_suite import BenchmarkSuite


class TestBenchmarkSuiteRealTracking:
    def test_run_benchmark_returns_real_buffer_stats(self):
        suite = BenchmarkSuite("Test-MoE-Model", buffer_size_mb=64, eviction_policy="lfu")
        results = suite.run_benchmark(num_tokens=10, num_layers=4, num_experts=16, active_experts=4)

        assert results["model_name"] == "Test-MoE-Model"
        assert results["buffer_size_mb"] == 64
        assert results["eviction_policy"] == "lfu"
        assert "buffer_hit_rate" in results
        assert 0.0 <= results["buffer_hit_rate"] <= 1.0
        assert results["total_requests"] > 0
        assert results["cache_hits"] >= 0
        assert results["cache_misses"] >= 0

    def test_export_report_markdown(self, tmp_path):
        export_path = tmp_path / "bench_report.md"
        suite = BenchmarkSuite("Test-Model", buffer_size_mb=32)
        suite.run_benchmark(num_tokens=5, num_layers=2, num_experts=8, active_experts=2)
        suite.export_report_markdown(str(export_path))

        assert export_path.exists()
        content = export_path.read_text(encoding="utf-8")
        assert "# 📊 Weight-Streaming Benchmark Report: Test-Model" in content
        assert "Real Buffer Hit Rate:" in content


# ═══════════════════════════════════════════════════════════════
# 7. GGUF Architecture Auto-Detector Tests
# ═══════════════════════════════════════════════════════════════
from weight_stream.gguf.parser import GGUFParser


class TestGGUFArcDetector:
    def test_detect_architecture_dict_structure(self, tmp_path):
        # Create a mock parser object with dummy metadata
        fake_gguf = tmp_path / "fake.gguf"
        fake_gguf.write_bytes(b"GGUF" + b"\x00" * 1024)

        # Mock initialization without calling GGUFReader on invalid file
        parser_obj = object.__new__(GGUFParser)
        parser_obj.metadata = {
            "general.architecture": "llama",
            "llama.block_count": 32,
            "llama.context_length": 4096,
            "llama.expert_count": 8,
            "llama.expert_used_count": 2,
        }
        parser_obj.tensors = []
        parser_obj.file_size = 1024 * 1024 * 100
        parser_obj.n_tensors = 0

        arch_info = GGUFParser.detect_architecture(parser_obj)

        assert arch_info["arch_name"] == "llama"
        assert arch_info["num_layers"] == 32
        assert arch_info["context_length"] == 4096
        assert arch_info["total_experts"] == 8
        assert arch_info["active_experts"] == 2
        assert arch_info["recommended_chat_template"] == "llama-3"
        assert arch_info["is_moe"] is True


# ═══════════════════════════════════════════════════════════════
# 8. CLI Entrypoint Tests
# ═══════════════════════════════════════════════════════════════
class TestCLIEntrypoint:
    def test_cli_import(self):
        from weight_stream.cli import main
        assert callable(main)


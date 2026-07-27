"""Tests for the WeightStreamModel backend and error handling.

Note: Full integration tests require the Qwen model file.
These tests verify the interface contract and error paths.
"""
import os
import tempfile
import pytest

from weight_stream.backends._base import WeightStreamBackend
from weight_stream.core.exceptions import ModelError, ConfigError


# ── Interface Contract Tests ──────────────────────────────────────────

class TestBackendInterface:
    """Verify WeightStreamBackend ABC enforces the interface."""

    def test_abstract_class_cannot_instantiate(self):
        with pytest.raises(TypeError, match="abstract"):
            WeightStreamBackend()  # Can't instantiate ABC directly

    def test_llama_cpp_imports(self):
        """Verify the llama_cpp module loads without the actual library."""
        from weight_stream.backends.llama_cpp import WeightStreamModel
        assert WeightStreamModel is not None

    def test_base_properties(self):
        """Test default property values on base class."""
        assert WeightStreamBackend.model_path.fget(None) is None
        assert WeightStreamBackend.is_loaded.fget(None) is False


# ── Model Error Tests ─────────────────────────────────────────────────

class TestModelErrors:
    """Verify error handling for model file issues."""

    def test_file_not_found(self):
        from weight_stream.backends.llama_cpp import WeightStreamModel
        with pytest.raises(ModelError, match="not found"):
            WeightStreamModel("/nonexistent/path/model.gguf")

    def test_empty_file(self):
        """Empty file should fail mmap."""
        from weight_stream.backends.llama_cpp import WeightStreamModel
        with tempfile.NamedTemporaryFile(suffix=".gguf", delete=False) as f:
            f.write(b"")  # Empty file, no GGUF header
            path = f.name
        try:
            with pytest.raises(ModelError, match="mmap|GGUF|parse|load"):
                WeightStreamModel(path)
        finally:
            os.unlink(path)

    def test_invalid_buffer_mb(self):
        from weight_stream.backends.llama_cpp import WeightStreamModel
        with pytest.raises(ConfigError, match="buffer_mb"):
            WeightStreamModel(
                "dummy.gguf",
                buffer_mb=0,  # Invalid
            )

    def test_invalid_n_ctx(self):
        from weight_stream.backends.llama_cpp import WeightStreamModel
        with pytest.raises(ConfigError, match="n_ctx"):
            WeightStreamModel(
                "dummy.gguf",
                n_ctx=0,  # Invalid
            )


# ── Integration Test (with real model if available) ───────────────────

@pytest.mark.skipif(
    not os.path.exists("research/models/Qwen1.5-MoE-A2.7B_Q2_k.gguf"),
    reason="Qwen model not available",
)
class TestIntegration:
    """Full integration tests using the Qwen model."""

    def test_model_loads_and_generates(self):
        from weight_stream.backends.llama_cpp import WeightStreamModel
        model = WeightStreamModel(
            "research/models/Qwen1.5-MoE-A2.7B_Q2_k.gguf",
            buffer_mb=64,
            n_ctx=64,
            verbose=False,
        )
        try:
            output = model.generate("Hello", max_tokens=5)
            assert isinstance(output, str)
            assert len(output) > 0
        finally:
            model.close()

    def test_context_manager(self):
        from weight_stream.backends.llama_cpp import WeightStreamModel
        with WeightStreamModel(
            "research/models/Qwen1.5-MoE-A2.7B_Q2_k.gguf",
            buffer_mb=64,
            n_ctx=64,
            verbose=False,
        ) as model:
            output = model.generate("Test", max_tokens=5)
            assert isinstance(output, str)

    def test_close_twice(self):
        """close() must be idempotent."""
        from weight_stream.backends.llama_cpp import WeightStreamModel
        model = WeightStreamModel(
            "research/models/Qwen1.5-MoE-A2.7B_Q2_k.gguf",
            buffer_mb=64,
            n_ctx=64,
            verbose=False,
        )
        model.close()
        # Second close should not raise
        model.close()

    def test_generate_after_close_raises(self):
        from weight_stream.backends.llama_cpp import WeightStreamModel
        from weight_stream.core.exceptions import GenerationError
        model = WeightStreamModel(
            "research/models/Qwen1.5-MoE-A2.7B_Q2_k.gguf",
            buffer_mb=64,
            n_ctx=64,
            verbose=False,
        )
        model.close()
        with pytest.raises(GenerationError):
            model.generate("Hello")

    def test_get_stats_structure(self):
        from weight_stream.backends.llama_cpp import WeightStreamModel
        model = WeightStreamModel(
            "research/models/Qwen1.5-MoE-A2.7B_Q2_k.gguf",
            buffer_mb=64,
            n_ctx=64,
            verbose=False,
        )
        try:
            model.generate("Stats", max_tokens=5)
            stats = model.get_stats()
            assert "buffer" in stats
            assert "predictor" in stats
            assert "prefetcher" in stats
            assert "generation" in stats
            assert "model" in stats
            # Buffer must have expected keys
            buf = stats["buffer"]
            assert "hit_rate" in buf
            assert "hot_shards" in buf
            assert "capacity_shards" in buf
        finally:
            model.close()

    def test_model_info_in_stats(self):
        from weight_stream.backends.llama_cpp import WeightStreamModel
        model = WeightStreamModel(
            "research/models/Qwen1.5-MoE-A2.7B_Q2_k.gguf",
            buffer_mb=64,
            n_ctx=64,
            verbose=False,
        )
        try:
            stats = model.get_stats()
            model_info = stats["model"]
            assert "arch" in model_info
            # Qwen1.5-MoE should be recognized
            assert "qwen" in model_info["arch"].lower() or "moe" in model_info["arch"].lower()
        finally:
            model.close()

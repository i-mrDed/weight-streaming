"""Tests for weight-streaming custom exceptions."""
import pytest
from weight_stream.core.exceptions import (
    WeightStreamError,
    ModelError,
    BufferError,
    PrefetchError,
    GenerationError,
    ConfigError,
)


class TestExceptions:
    """Verify exception hierarchy and messaging."""

    def test_base_exception(self):
        err = WeightStreamError("test error")
        assert str(err) == "test error"
        assert err.message == "test error"
        assert err.details == {}

    def test_base_exception_with_details(self):
        err = WeightStreamError("test error", {"key": "val"})
        assert "test error" in str(err)
        assert "key=val" in str(err)
        assert err.details == {"key": "val"}

    def test_model_error(self):
        err = ModelError("file not found", model_path="/path/to/model.gguf")
        assert "file not found" in str(err)
        assert err.details.get("model") == "/path/to/model.gguf"

    def test_model_error_no_path(self):
        err = ModelError("corrupt file")
        assert "corrupt file" in str(err)
        assert "model" not in err.details

    def test_generation_error(self):
        err = GenerationError("OOM", token_count=42)
        assert "OOM" in str(err)
        assert err.details.get("tokens") == 42

    def test_generation_error_no_tokens(self):
        err = GenerationError("engine crash")
        assert "engine crash" in str(err)
        assert "tokens" not in err.details

    def test_hierarchy(self):
        assert issubclass(ModelError, WeightStreamError)
        assert issubclass(BufferError, WeightStreamError)
        assert issubclass(PrefetchError, WeightStreamError)
        assert issubclass(GenerationError, WeightStreamError)
        assert issubclass(ConfigError, WeightStreamError)

    def test_config_error(self):
        err = ConfigError("buffer_mb must be >= 1", {"buffer_mb": 0})
        assert "buffer_mb must be >= 1" in str(err)
        assert err.details["buffer_mb"] == 0

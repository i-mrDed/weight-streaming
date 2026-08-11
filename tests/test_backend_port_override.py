"""Tests for WS_LLAMA_BACKEND_PORT env override (side-by-side servers)."""
import os

import pytest

from weight_stream.backends.llama_server import (
    LlamaServerBackend,
    _backend_port,
    DEFAULT_SERVER_PORT,
    BACKEND_PORT_ENV,
)
from weight_stream.core.exceptions import ModelError


class TestBackendPortEnv:
    def test_default_when_env_unset(self, monkeypatch):
        monkeypatch.delenv(BACKEND_PORT_ENV, raising=False)
        assert _backend_port() == DEFAULT_SERVER_PORT

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv(BACKEND_PORT_ENV, "8806")
        assert _backend_port() == 8806

    def test_constructor_uses_env(self, monkeypatch):
        monkeypatch.setenv(BACKEND_PORT_ENV, "8806")
        b = LlamaServerBackend(model_path="x.gguf", n_ctx=16, server_binary=None)
        assert b._port == 8806
        assert b._base_url == "http://127.0.0.1:8806"

    def test_explicit_port_wins_over_env(self, monkeypatch):
        monkeypatch.setenv(BACKEND_PORT_ENV, "8806")
        b = LlamaServerBackend(model_path="x.gguf", n_ctx=16,
                               server_binary=None, port=8807)
        assert b._port == 8807

    def test_invalid_env_raises(self, monkeypatch):
        monkeypatch.setenv(BACKEND_PORT_ENV, "not-a-port")
        with pytest.raises(ModelError):
            _backend_port()

    def test_out_of_range_env_raises(self, monkeypatch):
        monkeypatch.setenv(BACKEND_PORT_ENV, "80")
        with pytest.raises(ModelError):
            _backend_port()

    def test_blank_env_uses_default(self, monkeypatch):
        monkeypatch.setenv(BACKEND_PORT_ENV, "   ")
        assert _backend_port() == DEFAULT_SERVER_PORT
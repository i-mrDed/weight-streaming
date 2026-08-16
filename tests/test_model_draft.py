"""Tests for draft-model support + draft-only rejection (2026-08-16).

- LlamaServerBackend rejects a draft-only GGUF (few tensors) as a chat
  model with a clear ModelError.
- model_draft (arg or WS_MODEL_DRAFT env) adds --model-draft +
  --spec-type draft-mtp to the spawn command.
"""
import os
import subprocess

import pytest

from weight_stream.backends.llama_server import LlamaServerBackend
from weight_stream.core.exceptions import ModelError


from weight_stream.backends.llama_server import LlamaServerBackend
from weight_stream.core.exceptions import ModelError
from tests.gguf_helper import make_gguf


@pytest.fixture
def backend_factory():
    def make(model_path, **kw):
        return LlamaServerBackend(
            model_path=model_path,
            n_ctx=16,
            server_binary="fake-llama-server",
            **kw,
        )
    return make


class TestDraftOnlyRejection:
    def test_rejects_few_tensors(self, tmp_path, backend_factory):
        path = make_gguf(str(tmp_path / "m.gguf"), 18)  # MTP-ONLY has 18
        with pytest.raises(ModelError) as ei:
            backend_factory(path)
        assert "draft-only" in str(ei.value) or "not a full chat model" in str(ei.value)

    def test_accepts_full_model(self, tmp_path, backend_factory):
        path = make_gguf(str(tmp_path / "m.gguf"), 500)
        b = backend_factory(path)
        assert b._n_tensors == 500

    def test_zero_tensors_skips_guard(self, tmp_path, backend_factory):
        path = make_gguf(str(tmp_path / "m.gguf"), 0)
        b = backend_factory(path)
        assert b._n_tensors == 0


class TestModelDraftFlag:
    def _cmd(self, tmp_path, backend_factory, model_draft=None, env=None):
        path = make_gguf(str(tmp_path / "m.gguf"), 500)  # full model
        kw = {}
        if model_draft:
            kw["model_draft"] = model_draft
        old_env = None
        if env is not None:
            old_env = os.environ.get("WS_MODEL_DRAFT")
            os.environ["WS_MODEL_DRAFT"] = env
        try:
            b = backend_factory(path, **kw)
            # extract the spawn cmd via the private builder (monkeypatch Popen)
            cmd_holder = {}

            class FakeProc:
                stderr = None
                pid = 1

            def fake_popen(cmd, **kwargs):
                cmd_holder["cmd"] = cmd
                return FakeProc()

            monkeypatch = pytest.MonkeyPatch()
            monkeypatch.setattr(subprocess, "Popen", fake_popen)
            monkeypatch.setattr(b, "_sweep_stale_owner", lambda: None)
            monkeypatch.setattr(b, "_wait_ready", lambda timeout=300: None)
            monkeypatch.setattr(
                "weight_stream.backends.llama_server._assign_process_to_job",
                lambda *a: None)
            monkeypatch.setattr(
                "weight_stream.backends.llama_server._lower_child_priority",
                lambda *a: None)
            b.enable_routing()  # stub reasons: we only check cmd contents
            b._routing_enabled = False  # keep stderr=DEVNULL path simple
            b.start()
            return cmd_holder["cmd"]
        finally:
            if env is not None and old_env is not None:
                os.environ["WS_MODEL_DRAFT"] = old_env
            elif env is not None:
                os.environ.pop("WS_MODEL_DRAFT", None)

    def test_model_draft_arg_adds_flags(self, tmp_path, backend_factory):
        cmd = self._cmd(tmp_path, backend_factory,
                        model_draft="C:/draft.gguf")
        joined = " ".join(cmd)
        assert "--model-draft" in joined
        assert "C:/draft.gguf" in joined
        assert "--spec-type" in joined and "draft-mtp" in joined

    def test_env_fallback(self, tmp_path, backend_factory):
        cmd = self._cmd(tmp_path, backend_factory,
                        env="C:/draft-env.gguf")
        joined = " ".join(cmd)
        assert "--model-draft" in joined and "C:/draft-env.gguf" in joined

    def test_no_draft_no_flag(self, tmp_path, backend_factory):
        cmd = self._cmd(tmp_path, backend_factory)
        joined = " ".join(cmd)
        assert "--model-draft" not in joined
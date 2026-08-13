"""Tests for L1/A4 expert-routing capture (LlamaServerBackend).

Covers:
- _stderr_reader parsing of WS_EXPERT lines (fake pipe, no binary needed)
- routing() / routing_stats() contract
- reasoning-flag detection regex (new vs old llama.cpp builds)
- spawn wiring: stderr=PIPE + WS_EXPERT_LOG only when routing enabled
"""
import io
import threading

import pytest

from weight_stream.backends.llama_server import LlamaServerBackend


@pytest.fixture
def backend():
    b = LlamaServerBackend(
        model_path="nonexistent-model.gguf",
        n_ctx=16,
        server_binary=None,
    )
    yield b
    b.close()


class TestRoutingParser:
    def _feed(self, b, lines):
        """Simulate the reader thread consuming a stderr pipe."""
        b._routing_enabled = True
        stream = io.BytesIO("\n".join(lines).encode("utf-8"))
        b._proc = type("P", (), {"stderr": stream})()
        b._stderr_reader()

    def test_parses_expert_lines(self, backend):
        self._feed(backend, [
            "main: loading model",
            "WS_EXPERT row=0 experts=1,2,3,4",
            "WS_EXPERT row=0 experts=5,6",
            "something else",
        ])
        hist = backend.routing()
        assert hist == [[5, 6], [1, 2, 3, 4]]  # reversed: most recent first

    def test_ignores_garbage(self, backend):
        self._feed(backend, [
            "WS_EXPERT row=0 experts=",       # empty
            "WS_EXPERT experts=abc,def",      # non-int
            "not a ws line",
        ])
        assert backend.routing() == []

    def test_bounded_history(self, backend):
        # exceed the 4096 cap -> oldest dropped
        lines = [f"WS_EXPERT row=0 experts={i}" for i in range(4100)]
        self._feed(backend, lines)
        hist = backend.routing()
        assert len(hist) == 4096
        assert hist[0] == [4099]   # most recent kept
        assert hist[-1] == [4]     # oldest kept is #4 (0..3 dropped)

    def test_routing_stats_contract(self, backend):
        self._feed(backend, [
            "WS_EXPERT row=0 experts=1,2,3",
            "WS_EXPERT row=0 experts=1,2,4",
        ])
        stats = backend.routing_stats()
        assert stats["enabled"] is True
        assert stats["tokens"] == 2
        assert stats["experts_per_token"] == 3
        assert stats["unique_experts"] == 4      # {1,2,3,4}
        assert stats["last_token_experts"] == [1, 2, 4]

    def test_disabled_returns_empty(self, backend):
        assert backend.routing() == []
        assert backend.routing_stats()["enabled"] is False


class TestReasoningFlagDetect:
    def test_new_build_uses_reasoning_format(self, backend, monkeypatch):
        # build 8196 help: --reasoning-format / --reasoning-budget only
        import subprocess
        fake = type("R", (), {
            "stdout": (
                "--reasoning-format FORMAT  controls thought tags\n"
                "--reasoning-budget N       thinking budget\n"
            ),
        })()
        monkeypatch.setattr(subprocess, "run", lambda *a, **k: fake)
        assert backend._supports_reasoning_flag() is False

    def test_old_build_uses_reasoning(self, backend, monkeypatch):
        import subprocess
        fake = type("R", (), {
            "stdout": (
                "--reasoning [on|off|auto]  Use reasoning\n"
                "--reasoning-budget N       thinking budget\n"
            ),
        })()
        monkeypatch.setattr(subprocess, "run", lambda *a, **k: fake)
        assert backend._supports_reasoning_flag() is True

    def test_probe_failure_defaults_old(self, backend, monkeypatch):
        import subprocess
        def boom(*a, **k):
            raise OSError("no binary")
        monkeypatch.setattr(subprocess, "run", boom)
        assert backend._supports_reasoning_flag() is True


class TestSpawnWiring:
    def test_router_reader_thread_started(self, backend, monkeypatch):
        """enable_routing + start -> stderr pipe + reader thread."""
        import subprocess

        import weight_stream.backends.llama_server as mod

        class FakeProc:
            # a pipe that stays open briefly so the reader thread stays alive
            stderr = io.BytesIO(b"main: loading\n")
            pid = 4242

        captured = {}
        def fake_popen(cmd, **kw):
            captured["env"] = kw.get("env")
            captured["stderr"] = kw.get("stderr")
            return FakeProc()

        monkeypatch.setattr(subprocess, "Popen", fake_popen)
        monkeypatch.setattr(backend, "_sweep_stale_owner", lambda: None)
        monkeypatch.setattr(backend, "_wait_ready", lambda timeout=60: None)
        monkeypatch.setattr(mod, "_assign_process_to_job", lambda *a: None)
        monkeypatch.setattr(mod, "_lower_child_priority", lambda *a: None)

        backend.enable_routing()
        backend.start()

        assert captured["stderr"] is subprocess.PIPE
        assert captured["env"] is not None
        assert captured["env"].get("WS_EXPERT_LOG") == "1"
        assert backend._stderr_thread is not None
        assert backend._stderr_thread.name == "llama-server-stderr"
        assert backend._stderr_thread.daemon is True

    def test_no_routing_keeps_devnull(self, backend, monkeypatch):
        import subprocess

        import weight_stream.backends.llama_server as mod

        class FakeProc:
            stderr = None
            pid = 4243

        captured = {}
        def fake_popen(cmd, **kw):
            captured["env"] = kw.get("env")
            captured["stderr"] = kw.get("stderr")
            return FakeProc()

        monkeypatch.setattr(subprocess, "Popen", fake_popen)
        monkeypatch.setattr(backend, "_sweep_stale_owner", lambda: None)
        monkeypatch.setattr(backend, "_wait_ready", lambda timeout=60: None)
        monkeypatch.setattr(mod, "_assign_process_to_job", lambda *a: None)
        monkeypatch.setattr(mod, "_lower_child_priority", lambda *a: None)

        backend.start()  # routing NOT enabled

        assert captured["stderr"] is subprocess.DEVNULL
        assert captured["env"] is None       # no env override
        assert backend._stderr_thread is None
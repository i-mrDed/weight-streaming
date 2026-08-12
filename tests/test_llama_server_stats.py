"""Offline tests for LlamaServerBackend.get_stats() telemetry contract.

No llama-server binary or model file needed: the constructor tolerates a
missing GGUF (metadata falls back to {}), and get_stats() must report the
GPU-backend honesty contract — explicit nulls for buffer / prefetcher /
page_cache (never accidentally missing, never fabricated zeros), the model
fields the frontend needs (incl. n_experts for the MoE heatmap), and no
network calls while the subprocess is not running (gpu block is None).
"""
import json
import os

import pytest

from weight_stream.backends.llama_server import LlamaServerBackend


@pytest.fixture
def gpu_backend():
    b = LlamaServerBackend(
        model_path="nonexistent-model.gguf",
        n_ctx=16,
        server_binary=None,  # no binary needed — we never start()
    )
    yield b
    b.close()


class TestLlamaServerStatsContract:
    def test_get_stats_shape(self, gpu_backend):
        stats = gpu_backend.get_stats()
        # GPU backend honesty: EXPLICIT nulls (self-documenting "no such
        # telemetry here"), not accidentally-missing keys — every consumer
        # must render honest "n/a", never a fabricated zero.
        assert stats["buffer"] is None
        assert stats["prefetcher"] is None
        assert stats["page_cache"] is None
        # No llama-server subprocess running → gpu block honestly None
        # (never a network call or fabricated VRAM).
        assert stats["gpu"] is None

    def test_model_fields(self, gpu_backend):
        stats = gpu_backend.get_stats()
        model = stats["model"]
        assert model["backend"] == "llama-server"
        assert "path" in model
        assert "arch" in model
        # n_experts must exist (0 when metadata unreadable) so the frontend
        # heatmap does not mislabel a MoE model as "not MoE".
        assert "n_experts" in model
        assert isinstance(model["n_experts"], int)

    def test_generation_starts_empty(self, gpu_backend):
        # Same contract as the CPU binding: {} until the first generation.
        assert gpu_backend.get_stats()["generation"] == {}


class TestStreamChatPaging:
    def test_subprocess_paging_attached_to_last_gen_stats(self, monkeypatch):
        """stream_chat's finally block must attach REAL paging demand (from
        the sampled subprocess counters) — never a fabricated block."""
        import weight_stream.backends.llama_server as ls_mod

        b = LlamaServerBackend(model_path="x.gguf", n_ctx=16, server_binary=None)
        try:
            # Pretend the subprocess is running so stream_chat skips start().
            monkeypatch.setattr(
                ls_mod.LlamaServerBackend,
                "is_loaded",
                property(lambda self: True),
            )
            calls = {"n": 0}

            def fake_faults(pid=None):
                calls["n"] += 1
                # 100 faults before generation, 150 after → delta 50.
                return 100 if calls["n"] == 1 else 150

            monkeypatch.setattr(ls_mod, "page_fault_count", fake_faults)

            def fake_request(path, payload, timeout=300.0):
                yield {"choices": [{"delta": {"content": "Hello"}}]}

            monkeypatch.setattr(b, "_request", fake_request)

            out = "".join(b.stream_chat([{"role": "user", "content": "hi"}], max_tokens=5))
            assert out == "Hello"
            paging = b._last_gen_stats.get("paging")
            assert paging is not None
            assert paging["faults"] == 50
            assert paging["faults_per_token"] == 50.0
        finally:
            b.close()

    def test_chat_template_kwargs_forwarded_to_payload(self, monkeypatch):
        """Agent tool turns pass chat_template_kwargs (e.g.
        {"enable_thinking": false}) through to llama-server. Qwen3-family
        templates default thinking ON, which makes tool-calling degenerate;
        the agent loop relies on this flag reaching the payload."""
        import weight_stream.backends.llama_server as ls_mod

        b = LlamaServerBackend(model_path="x.gguf", n_ctx=16, server_binary=None)
        try:
            monkeypatch.setattr(
                ls_mod.LlamaServerBackend,
                "is_loaded",
                property(lambda self: True),
            )
            captured = {}

            def fake_request(path, payload, timeout=300.0):
                captured["payload"] = payload
                yield {"choices": [{"delta": {"content": "Hi"}}]}

            monkeypatch.setattr(b, "_request", fake_request)
            list(b.stream_chat(
                [{"role": "user", "content": "hi"}],
                max_tokens=5,
                chat_template_kwargs={"enable_thinking": False},
            ))
            assert captured["payload"]["chat_template_kwargs"] == {"enable_thinking": False}
        finally:
            b.close()

    def test_paging_absent_when_counters_unavailable(self, monkeypatch):
        """POSIX-style None counters → the paging key is simply absent
        (honest), never zeroed or fabricated."""
        import weight_stream.backends.llama_server as ls_mod

        b = LlamaServerBackend(model_path="x.gguf", n_ctx=16, server_binary=None)
        try:
            monkeypatch.setattr(
                ls_mod.LlamaServerBackend,
                "is_loaded",
                property(lambda self: True),
            )
            monkeypatch.setattr(ls_mod, "page_fault_count", lambda pid=None: None)

            def fake_request(path, payload, timeout=300.0):
                yield {"choices": [{"delta": {"content": "Hi"}}]}

            monkeypatch.setattr(b, "_request", fake_request)
            list(b.stream_chat([{"role": "user", "content": "hi"}], max_tokens=5))
            assert "paging" not in b._last_gen_stats
        finally:
            b.close()


class TestGpuLoadFlags:
    """P7.5: gpu_layers → -ngl and kv_cache_type → -ctk/-ctv in the
    llama-server command line; invalid kv types are refused up front."""

    def _cmd_with(self, monkeypatch, lower_calls=None, **ctor):
        import subprocess
        import weight_stream.backends.llama_server as ls_mod

        captured = {}

        class FakeProc:
            pid = 777

            def poll(self):
                return None

            def terminate(self):
                pass

            def wait(self, timeout=None):
                return 0

            def kill(self):
                pass

        def fake_popen(cmd, **kwargs):
            captured["cmd"] = list(cmd)
            return FakeProc()

        b = LlamaServerBackend(
            model_path="x.gguf",
            n_ctx=16,
            server_binary="C:/fake/llama-server.exe",
            **ctor,
        )
        try:
            monkeypatch.setattr(ls_mod.subprocess, "Popen", fake_popen)
            # Child priority lowering must never touch a real process in
            # tests — record the pid when the test asks for it.
            monkeypatch.setattr(
                ls_mod, "_lower_child_priority",
                lambda pid: (lower_calls.append(pid) if lower_calls is not None
                             else None) or True,
            )
            # EXP-009: start() sweeps stale port owners via /props first —
            # keep it fully offline (never probe/kill a real 8805 owner).
            monkeypatch.setattr(b, "_read_props", lambda: None)
            monkeypatch.setattr(
                ls_mod.LlamaServerBackend,
                "_wait_ready",
                lambda self, timeout=60: setattr(self, "_ready", True),
            )
            b.start()
            return captured["cmd"]
        finally:
            b.close()

    def test_gpu_layers_auto_omits_flag(self, monkeypatch):
        cmd = self._cmd_with(monkeypatch)  # gpu_layers defaults to -1 (auto)
        assert "-ngl" not in cmd

    def test_gpu_layers_explicit_adds_ngl(self, monkeypatch):
        cmd = self._cmd_with(monkeypatch, gpu_layers=32)
        assert "-ngl" in cmd
        assert cmd[cmd.index("-ngl") + 1] == "32"

    def test_gpu_layers_zero_forces_cpu(self, monkeypatch):
        cmd = self._cmd_with(monkeypatch, gpu_layers=0)
        assert cmd[cmd.index("-ngl") + 1] == "0"

    def test_kv_cache_type_adds_ctk_ctv(self, monkeypatch):
        cmd = self._cmd_with(monkeypatch, kv_cache_type="q8_0")
        assert "-ctk" in cmd
        assert cmd[cmd.index("-ctk") + 1] == "q8_0"
        assert cmd[cmd.index("-ctv") + 1] == "q8_0"

    def test_kv_cache_type_case_normalized(self, monkeypatch):
        cmd = self._cmd_with(monkeypatch, kv_cache_type="Q8_0")
        assert cmd[cmd.index("-ctk") + 1] == "q8_0"

    def test_spawn_lowers_child_priority_by_default(self, monkeypatch):
        calls = []
        self._cmd_with(monkeypatch, lower_calls=calls)
        # WS_LOWER_PRIORITY defaults to enabled → the spawned child (pid 777)
        # is dropped below-normal so the desktop stays responsive during
        # inference, not just the API server process.
        assert calls == [777]

    def test_spawn_skips_child_lowering_when_disabled(self, monkeypatch):
        monkeypatch.setenv("WS_LOWER_PRIORITY", "0")
        calls = []
        self._cmd_with(monkeypatch, lower_calls=calls)
        assert calls == []

    def test_invalid_kv_cache_type_refused(self):
        from weight_stream.core.exceptions import ModelError
        with pytest.raises(ModelError, match="Unsupported KV cache type"):
            LlamaServerBackend(
                model_path="x.gguf",
                n_ctx=16,
                server_binary="C:/fake/llama-server.exe",
                kv_cache_type="banana",
            )


class TestWaitReadyPortCollisionGuard:
    """EXP-007 regression: _wait_ready() must NOT trust a /health 200 on our
    fixed port — a stale llama-server squatting there answers /health too.
    It must verify /props model_path matches the model we loaded."""

    # Two models for the collision scenario: ours (35B) vs stale (Qwythos).
    # Deliberately NON-EXISTENT paths: these tests exercise the /props
    # path-comparison guard, not GGUF parsing — a real 10 GB model file
    # here made every _make_backend() take ~9.5 s (GGUF header parse).
    OUR = ("D:/models/Qwen3.6-35B-A3B-GGUF/"
           "Qwen3.6-35B-A3B-UD-IQ2_M.missing.gguf")
    STALE = ("C:/Users/x/AppData/Roaming/Jan/data/llamacpp/models/"
             "Qwythos-9B-Claude-Mythos-5-1M-Q4_K_M/model.gguf")

    class _FakeProc:
        """Minimal stand-in for subprocess.Popen — _wait_ready() polls it."""
        returncode = None

        def poll(self):
            return None

        def terminate(self):
            pass

        def wait(self, timeout=None):
            return 0

        def kill(self):
            pass

    class _FakeResp:
        def __init__(self, status=200, body=None):
            self.status = status
            self._body = body or b"{}"

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return self._body

    def _make_backend(self, model_path=OUR):
        return LlamaServerBackend(
            model_path=model_path,
            n_ctx=16,
            server_binary=None,
            port=8805,
        )

    def _install_http(self, monkeypatch, props_model_path=None, health_status=200):
        """Serve /health 200 + /props with the given model_path (or fail
        /props entirely when props_model_path is a sentinel)."""
        import weight_stream.backends.llama_server as ls_mod

        def fake_urlopen(url, timeout=2):
            url = str(url)
            if url.endswith("/health"):
                return self._FakeResp(status=health_status)
            if url.endswith("/props"):
                if props_model_path is None:
                    raise OSError("connection refused")
                body = json.dumps({"model_path": props_model_path}).encode()
                return self._FakeResp(status=200, body=body)
            raise AssertionError(f"unexpected url: {url}")

        monkeypatch.setattr(ls_mod.urllib.request, "urlopen", fake_urlopen)

    def test_ready_when_props_match(self, monkeypatch):
        """Normal case: /health 200 AND /props model_path == our model →
        backend considers itself ready."""
        import weight_stream.backends.llama_server as ls_mod
        b = self._make_backend()
        try:
            # Exercise the real _wait_ready (not the start() wrapper which
            # needs a binary); patch only the network layer.
            self._install_http(monkeypatch, props_model_path=self.OUR)
            monkeypatch.setattr(b, "_proc", self._FakeProc())
            b._wait_ready(timeout=2)
            assert b._ready is True
        finally:
            b.close()

    def test_port_collision_raises(self, monkeypatch):
        """Stale server on our port: /health 200 (it answers!) but /props
        shows a DIFFERENT model → ModelError, never silently serving it."""
        from weight_stream.core.exceptions import ModelError
        import weight_stream.backends.llama_server as ls_mod
        b = self._make_backend()
        try:
            self._install_http(monkeypatch, props_model_path=self.STALE)
            monkeypatch.setattr(b, "_proc", self._FakeProc())
            with pytest.raises(ModelError, match="DIFFERENT model"):
                b._wait_ready(timeout=2)
            # Must NOT mark itself ready after a collision.
            assert b._ready is False
        finally:
            b.close()

    def test_path_normalization_tolerates_case_and_separators(self, monkeypatch):
        """Windows path from /props may differ in case/separators from the
        load request — equality must be normalized (EXP-007 guard must not
        false-positive on its own server)."""
        import weight_stream.backends.llama_server as ls_mod
        # Backslash variant of OUR path, different drive-letter case.
        props_win = ("d:/Models/Qwen3.6-35B-A3B-GGUF/"
                     "Qwen3.6-35B-A3B-UD-IQ2_M.missing.gguf")
        assert ls_mod.LlamaServerBackend._same_model_path(props_win, self.OUR)

    def test_relative_vs_absolute_match(self, monkeypatch):
        """A relative request path must still match llama-server's absolute
        /props path (abspath normalization) — no false-positive collision
        on our own server."""
        import weight_stream.backends.llama_server as ls_mod
        assert ls_mod.LlamaServerBackend._same_model_path(
            self.OUR, os.path.relpath(self.OUR))

    def test_truly_different_paths_do_not_match(self, monkeypatch):
        """The guard must still catch a genuinely different model."""
        import weight_stream.backends.llama_server as ls_mod
        assert not ls_mod.LlamaServerBackend._same_model_path(self.OUR, self.STALE)

    def test_props_unavailable_is_backward_compatible(self, monkeypatch):
        """Older llama-server builds expose no /props → cannot verify →
        accept with a warning (never break load on old binaries)."""
        import weight_stream.backends.llama_server as ls_mod
        b = self._make_backend()
        try:
            self._install_http(monkeypatch, props_model_path=None)  # /props fails
            monkeypatch.setattr(b, "_proc", self._FakeProc())
            b._wait_ready(timeout=2)
            assert b._ready is True
        finally:
            b.close()

    def test_health_timeout_raises(self, monkeypatch):
        """No server at all on the port → ModelError (unchanged behavior)."""
        from weight_stream.core.exceptions import ModelError
        import weight_stream.backends.llama_server as ls_mod
        b = self._make_backend()
        try:
            self._install_http(monkeypatch, health_status=503)
            monkeypatch.setattr(b, "_proc", self._FakeProc())
            with pytest.raises(ModelError, match="not ready"):
                b._wait_ready(timeout=1)
            assert b._ready is False
        finally:
            b.close()


class TestPageFaultPidContract:
    def test_nonexistent_pid_is_honest_none(self):
        """page_fault_count(pid=...) must never raise or fabricate."""
        from weight_stream.io.page_faults import page_fault_count
        # PID 999999999 does not exist on any real system — OpenProcess
        # (Windows) returns NULL → None; POSIX returns None by contract.
        assert page_fault_count(pid=999_999_999) is None

class TestExtraArgsInjection:
    """WS_LLAMA_EXTRA_ARGS must be appended to the llama-server command line
    (shlex-split), letting us experiment with --cpu-moe / -fa / -ctk without
    code changes — while unparsable input is ignored, never fatal."""

    def _capture_start_cmd(self, monkeypatch, extra_env):
        import subprocess
        import weight_stream.backends.llama_server as ls_mod

        captured = {}

        class FakeProc:
            pid = 4242

            def poll(self):
                return None

            def terminate(self):
                pass

            def wait(self, timeout=None):
                return 0

            def kill(self):
                pass

        def fake_popen(cmd, **kwargs):
            captured["cmd"] = list(cmd)
            return FakeProc()

        b = LlamaServerBackend(
            model_path="x.gguf",
            n_ctx=16,
            server_binary="C:/fake/llama-server.exe",
        )
        try:
            monkeypatch.setattr(ls_mod.subprocess, "Popen", fake_popen)
            # EXP-009: keep start()'s stale-owner sweep offline.
            monkeypatch.setattr(b, "_read_props", lambda: None)
            monkeypatch.setattr(
                ls_mod.LlamaServerBackend,
                "_wait_ready",
                lambda self, timeout=60: setattr(self, "_ready", True),
            )
            if extra_env is not None:
                monkeypatch.setenv("WS_LLAMA_EXTRA_ARGS", extra_env)
            else:
                monkeypatch.delenv("WS_LLAMA_EXTRA_ARGS", raising=False)
            b.start()
            return captured["cmd"]
        finally:
            b.close()

    def test_extra_args_appended(self, monkeypatch):
        cmd = self._capture_start_cmd(
            monkeypatch, "--cpu-moe -fa on -ctk q8_0 -ctv q8_0"
        )
        assert "--cpu-moe" in cmd
        assert "-fa" in cmd and "on" in cmd
        assert "-ctk" in cmd and "q8_0" in cmd
        # Ordered after the backend's own flags.
        assert cmd.index("--cpu-moe") > cmd.index("-m")

    def test_no_extra_env_no_crash(self, monkeypatch):
        cmd = self._capture_start_cmd(monkeypatch, None)
        assert "--cpu-moe" not in cmd
        assert cmd[0] == "C:/fake/llama-server.exe"

    def test_quoted_extra_args_split(self, monkeypatch):
        cmd = self._capture_start_cmd(
            monkeypatch, '-ot "*.mlp.experts=CPU" -ngl 99'
        )
        # shlex: quoted value stays one token.
        assert '"*.mlp.experts=CPU"' in cmd or '*.mlp.experts=CPU' in cmd
        assert "-ngl" in cmd and "99" in cmd

    def test_unparsable_extra_ignored(self, monkeypatch):
        # Unterminated quote → shlex raises → backend must not crash.
        cmd = self._capture_start_cmd(monkeypatch, '--cpu-moe "unterminated')
        assert "--cpu-moe" not in cmd

    def test_current_process_still_counts(self):
        """pid=None (the CPU-binding path) keeps working unchanged."""
        from weight_stream.io.page_faults import page_fault_count, is_supported
        if not is_supported():
            pytest.skip("platform has no page-fault counter")
        val = page_fault_count()
        assert isinstance(val, int)
        assert val >= 0


class TestOrphanGuard:
    """EXP-009: a force-killed parent must not orphan its llama-server.

    Two mechanisms: (1) a Windows KILL_ON_JOB_CLOSE Job Object makes the OS
    kill the child when the parent dies by ANY means (taskkill /F, crash,
    console close); (2) a stale-owner sweep at start() clears a leftover
    llama-server on our fixed port that serves a different model, so loads
    recover instead of failing the collision guard. All tests stay fully
    offline — no real subprocess or network ever runs.
    """

    def _backend_with_fake_spawn(self, monkeypatch):
        import subprocess
        import weight_stream.backends.llama_server as ls_mod

        events = {"assign": [], "close_job": [], "terminates": 0, "sweeps": 0}

        class FakeProc:
            pid = 4242
            _handle = 42

            def poll(self):
                return None

            def terminate(self):
                events["terminates"] += 1

            def wait(self, timeout=None):
                return 0

            def kill(self):
                pass

        b = LlamaServerBackend(
            model_path="x.gguf",
            n_ctx=16,
            server_binary="C:/fake/llama-server.exe",
        )

        def bump_sweep():
            events["sweeps"] += 1

        monkeypatch.setattr(ls_mod.subprocess, "Popen", lambda cmd, **kw: FakeProc())
        monkeypatch.setattr(ls_mod, "_create_win32_kill_on_close_job", lambda: 12345)
        monkeypatch.setattr(
            ls_mod, "_assign_process_to_job",
            lambda job, proc: events["assign"].append((job, proc.pid)) or True,
        )
        monkeypatch.setattr(
            ls_mod, "_close_win32_job",
            lambda job: events["close_job"].append(job) or None,
        )
        monkeypatch.setattr(b, "_sweep_stale_owner", bump_sweep)
        monkeypatch.setattr(
            ls_mod.LlamaServerBackend, "_wait_ready",
            lambda self, timeout=60: setattr(self, "_ready", True),
        )
        return b, events

    def test_child_assigned_to_kill_on_close_job(self, monkeypatch):
        """start() puts the subprocess in the job; close() releases the job
        handle (which force-kills any child that survived terminate). The
        child's PID is registered as OURS while alive and unregistered on
        close — so a sibling backend's sweep can never kill it."""
        import weight_stream.backends.llama_server as ls_mod

        b, events = self._backend_with_fake_spawn(monkeypatch)
        try:
            b.start()
            assert events["sweeps"] == 1            # recovery ran before spawn
            assert events["assign"] == [(12345, 4242)]
            assert 4242 in ls_mod._OWNED_PIDS
        finally:
            b.close()
        assert events["close_job"] == [12345]
        assert events["terminates"] == 1
        assert 4242 not in ls_mod._OWNED_PIDS

    def test_close_is_idempotent(self, monkeypatch):
        """Double close() must not double-terminate or double-close the job."""
        b, events = self._backend_with_fake_spawn(monkeypatch)
        b.start()
        b.close()
        b.close()
        assert events["terminates"] == 1
        assert events["close_job"] == [12345]

    def test_sweep_never_kills_owned_sibling(self, monkeypatch):
        """With max_loaded_models > 1, a sibling backend's llama-server
        (one WE spawned — in _OWNED_PIDS) must never be killed by our
        sweep; the load fails via the collision guard instead of destroying
        the sibling's session (which would silently reroute its traffic)."""
        import weight_stream.backends.llama_server as ls_mod

        b = LlamaServerBackend(model_path="x.gguf", n_ctx=16, server_binary=None)
        try:
            monkeypatch.setattr(
                b, "_read_props",
                lambda: {"model_path": "D:/models/Qwythos-9B/model.gguf"},
            )
            monkeypatch.setattr(ls_mod, "_find_port_pid", lambda port: 777)
            monkeypatch.setattr(ls_mod, "_OWNED_PIDS", {777})
            kills = []
            monkeypatch.setattr(
                ls_mod, "_kill_pid", lambda pid: kills.append(pid) or True)
            b._sweep_stale_owner()
            assert kills == []            # own child → refused
        finally:
            b.close()

    def test_failed_wait_ready_terminates_spawned_child(self, monkeypatch):
        """If the port guard raises (a collision the sweep could not clear,
        a timeout, an early exit), the just-spawned subprocess must be
        terminated — never leaked as a fresh orphan when the caller drops
        this backend and falls back to the CPU binding."""
        from weight_stream.core.exceptions import ModelError
        import weight_stream.backends.llama_server as ls_mod

        b, events = self._backend_with_fake_spawn(monkeypatch)

        def collision(self, timeout=60):
            raise ModelError("llama-server on our port serves a DIFFERENT model")

        monkeypatch.setattr(ls_mod.LlamaServerBackend, "_wait_ready", collision)
        with pytest.raises(ModelError):
            b.start()
        assert events["terminates"] == 1
        assert events["close_job"] == [12345]
        assert b._proc is None
        assert b._started is False

    def test_kill_on_close_job_helper(self):
        """The job helper must produce a real handle on Windows and be a
        no-op on POSIX (no orphans there — init reaps children)."""
        import weight_stream.backends.llama_server as ls_mod

        job = ls_mod._create_win32_kill_on_close_job()
        if os.name == "nt":
            assert job is not None, "KILL_ON_JOB_CLOSE job must exist on Windows"
            ls_mod._close_win32_job(job)
        else:
            assert job is None

    def test_sweep_kills_stale_different_model(self, monkeypatch):
        """A leftover llama-server serving a DIFFERENT model on our port is
        killed by PID before the fresh spawn (self-healing recovery)."""
        import weight_stream.backends.llama_server as ls_mod

        b = LlamaServerBackend(model_path="x.gguf", n_ctx=16, server_binary=None)
        try:
            monkeypatch.setattr(
                b, "_read_props",
                lambda: {"model_path": "D:/models/Qwythos-9B/model.gguf"},
            )
            monkeypatch.setattr(ls_mod, "_find_port_pid", lambda port: 777)
            kills = []
            monkeypatch.setattr(
                ls_mod, "_kill_pid", lambda pid: kills.append(pid) or True)
            b._sweep_stale_owner()
            assert kills == [777]
        finally:
            b.close()

    def test_sweep_keeps_our_own_model(self, monkeypatch):
        """Our own model already on the port (idempotent start) is never
        touched — the sweep must not kill our own server."""
        import weight_stream.backends.llama_server as ls_mod

        b = LlamaServerBackend(
            model_path="D:/Models/x.gguf", n_ctx=16, server_binary=None)
        try:
            monkeypatch.setattr(
                b, "_read_props",
                lambda: {"model_path": "d:/models/x.gguf"},
            )
            kills = []
            monkeypatch.setattr(
                ls_mod, "_kill_pid", lambda pid: kills.append(pid) or True)
            b._sweep_stale_owner()
            assert kills == []
        finally:
            b.close()

    def test_sweep_skips_empty_port(self, monkeypatch):
        """Nothing listening on the port → the sweep is a no-op."""
        import weight_stream.backends.llama_server as ls_mod

        b = LlamaServerBackend(model_path="x.gguf", n_ctx=16, server_binary=None)
        try:
            monkeypatch.setattr(b, "_read_props", lambda: None)
            kills = []
            monkeypatch.setattr(
                ls_mod, "_kill_pid", lambda pid: kills.append(pid) or True)
            b._sweep_stale_owner()
            assert kills == []
        finally:
            b.close()

    def test_parse_netstat_listener(self):
        """netstat -ano parsing: LISTENING PID extraction, IPv6 rows,
        non-TCP rows, unknown ports, and our own PID are all handled."""
        import weight_stream.backends.llama_server as ls_mod

        sample = (
            "  TCP    127.0.0.1:8805    0.0.0.0:0    LISTENING    48920\n"
            "  TCP    127.0.0.1:8765    0.0.0.0:0    LISTENING    30684\n"
            "  TCP    [::]:8805        [::]:0       LISTENING    48920\n"
            "  UDP    0.0.0.0:8805     *:*                     48920\n"
            f"  TCP    127.0.0.1:9999    0.0.0.0:0    LISTENING    {os.getpid()}\n"
        )
        assert ls_mod._parse_netstat_listener(sample, 8805) == 48920
        assert ls_mod._parse_netstat_listener(sample, 8765) == 30684
        assert ls_mod._parse_netstat_listener(sample, 9999) is None  # own PID
        assert ls_mod._parse_netstat_listener("", 8805) is None

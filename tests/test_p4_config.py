"""P4 contract + unit tests: /v1/config (GET + PATCH v1.1) and the shared
model-search-dir helper.

Offline-only; uses tmp paths for the usage/log stores so nothing is written
into the repo's data/ directory.
"""

import os

from fastapi.testclient import TestClient

from weight_stream.server.api_server import create_app
from weight_stream.server.config import (
    ServerConfig,
    get_model_search_dirs,
    describe_config,
    CONFIG_ENV_KEYS,
)


def _app(monkeypatch, tmp_path, **cfg):
    """Build an app whose usage/log stores point at tmp (no repo pollution)."""
    monkeypatch.setenv("WS_USAGE_HISTORY_FILE", str(tmp_path / "usage.jsonl"))
    monkeypatch.setenv("WS_LOG_FILE", str(tmp_path / "server.log"))
    return create_app(ServerConfig(**cfg))


# ── get_model_search_dirs helper ──────────────────────────────────────


def test_get_model_search_dirs_honors_ws_models_dir_first(monkeypatch):
    monkeypatch.setenv("WS_MODELS_DIR", "/some/models")
    dirs = get_model_search_dirs()
    assert dirs[0] == "/some/models"


def test_get_model_search_dirs_includes_common_locations(monkeypatch):
    monkeypatch.delenv("WS_MODELS_DIR", raising=False)
    dirs = get_model_search_dirs()
    cwd = os.getcwd()
    assert cwd in dirs
    assert os.path.join(cwd, "models") in dirs
    assert os.path.expanduser("~/models") in dirs


def test_scan_models_still_works_through_shared_helper(monkeypatch, tmp_path):
    """Regression: the refactored _scan_gguf_models must still list GGUFs."""
    (tmp_path / "tiny.gguf").write_bytes(b"")  # empty file; header parse is best-effort
    app, _ = _app(monkeypatch, tmp_path)
    with TestClient(app) as c:
        r = c.get("/v1/models/scan", params={"dir": str(tmp_path)})
        assert r.status_code == 200
        names = [m["name"] for m in r.json()["models"]]
        assert "tiny.gguf" in names


# ── GET /v1/config ────────────────────────────────────────────────────


def test_get_config_reports_every_key_with_source(monkeypatch, tmp_path):
    monkeypatch.delenv("WS_MAX_MODELS", raising=False)
    app, _ = _app(monkeypatch, tmp_path)
    with TestClient(app) as c:
        d = c.get("/v1/config").json()
    cfg = d["config"]
    for field_name in ServerConfig().__dataclass_fields__:  # noqa: SLF001
        assert field_name in cfg
        assert set(cfg[field_name]) == {"value", "source"}
        assert cfg[field_name]["source"] in ("env", "default", "runtime")


def test_get_config_source_env_when_var_set(monkeypatch, tmp_path):
    monkeypatch.setenv("WS_MAX_MODELS", "7")
    app, _ = _app(monkeypatch, tmp_path)
    with TestClient(app) as c:
        cfg = c.get("/v1/config").json()["config"]
    assert cfg["max_loaded_models"] == {"value": 7, "source": "env"}
    assert cfg["port"]["source"] == "default"  # WS_PORT not set


def test_get_config_includes_dirs_and_version(monkeypatch, tmp_path):
    from weight_stream import __version__
    app, _ = _app(monkeypatch, tmp_path)
    with TestClient(app) as c:
        d = c.get("/v1/config").json()
    assert d["version"] == __version__
    assert isinstance(d["models_dirs"], list) and d["models_dirs"]
    assert d["issues_dir"]  # real path from the issue store


# ── describe_config runtime source ────────────────────────────────────


def test_describe_config_marks_runtime_overrides(monkeypatch):
    monkeypatch.delenv("WS_N_CTX", raising=False)
    cfg = ServerConfig()
    cfg.default_n_ctx = 9999
    cfg._runtime_overrides = {"default_n_ctx"}  # noqa: SLF001
    assert describe_config(cfg)["default_n_ctx"]["source"] == "runtime"


# ── PATCH /v1/config ──────────────────────────────────────────────────


def test_patch_safe_keys_apply_and_mutate_live_config(monkeypatch, tmp_path):
    app, mgr = _app(monkeypatch, tmp_path)
    with TestClient(app) as c:
        r = c.patch("/v1/config", json={"idle_unload_timeout": 120, "max_loaded_models": 2})
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "applied"
        assert body["applied"]["idle_unload_timeout"] == {"value": 120.0, "source": "runtime"}
        assert mgr._cfg.idle_unload_timeout == 120.0  # noqa: SLF001
        assert mgr._cfg.max_loaded_models == 2  # noqa: SLF001


def test_patch_gated_key_returns_next_load_note(monkeypatch, tmp_path):
    app, mgr = _app(monkeypatch, tmp_path)
    with TestClient(app) as c:
        r = c.patch("/v1/config", json={"default_n_ctx": 4096})
        assert r.status_code == 200
        assert "default_n_ctx" in r.json()["notes"]
        assert mgr._cfg.default_n_ctx == 4096  # noqa: SLF001


def test_patch_runtime_source_is_reflected_in_get(monkeypatch, tmp_path):
    app, _ = _app(monkeypatch, tmp_path)
    with TestClient(app) as c:
        c.patch("/v1/config", json={"max_loaded_models": 3})
        cfg = c.get("/v1/config").json()["config"]
    assert cfg["max_loaded_models"] == {"value": 3, "source": "runtime"}


def test_patch_restart_key_409_with_snippet_and_no_mutation(monkeypatch, tmp_path):
    app, mgr = _app(monkeypatch, tmp_path)
    original_port = mgr._cfg.port  # noqa: SLF001
    with TestClient(app) as c:
        r = c.patch("/v1/config", json={"port": 9999})
        assert r.status_code == 409
        body = r.json()
        assert body["restart_required"] is True
        assert "WS_PORT=9999" in body["snippet"]
        assert "port" in body["rejected"]
    assert mgr._cfg.port == original_port  # noqa: SLF001  (not mutated)


def test_patch_unenforced_key_409_is_honest_noop(monkeypatch, tmp_path):
    app, _ = _app(monkeypatch, tmp_path)
    with TestClient(app) as c:
        r = c.patch("/v1/config", json={"max_concurrent_requests": 5})
        assert r.status_code == 409
        assert "not enforced" in r.json()["rejected"]["max_concurrent_requests"]


def test_patch_unknown_key_400(monkeypatch, tmp_path):
    app, _ = _app(monkeypatch, tmp_path)
    with TestClient(app) as c:
        assert c.patch("/v1/config", json={"bogus": 1}).status_code == 400


def test_patch_invalid_values_400(monkeypatch, tmp_path):
    app, _ = _app(monkeypatch, tmp_path)
    with TestClient(app) as c:
        assert c.patch("/v1/config", json={"max_loaded_models": "abc"}).status_code == 400
        assert c.patch("/v1/config", json={"max_loaded_models": 0}).status_code == 400
        assert c.patch("/v1/config", json={"idle_unload_timeout": -5}).status_code == 400
        assert c.patch("/v1/config", json={}).status_code == 400


def test_patch_mixed_safe_and_reject_is_atomic(monkeypatch, tmp_path):
    app, mgr = _app(monkeypatch, tmp_path)
    before = mgr._cfg.max_loaded_models  # noqa: SLF001
    with TestClient(app) as c:
        r = c.patch("/v1/config", json={"max_loaded_models": 9, "port": 1})
        assert r.status_code == 409
    assert mgr._cfg.max_loaded_models == before  # noqa: SLF001  (nothing applied)


def test_config_env_keys_cover_every_field():
    """The source map must stay in sync with ServerConfig fields."""
    for field_name in ServerConfig().__dataclass_fields__:  # noqa: SLF001
        assert field_name in CONFIG_ENV_KEYS


# ── GET /v1/hardware (quant-fit advisory data) ────────────────────────


def test_hardware_reports_nvidia_gpu_when_available(monkeypatch, tmp_path):
    """Parses nvidia-smi output into {gpu: {name, total_vram_mb}}."""
    import subprocess

    real_run = subprocess.run

    def fake_run(cmd, *args, **kwargs):
        assert cmd[0] == "nvidia-smi"
        assert "--query-gpu=name,memory.total" in cmd
        return type("R", (), {"stdout": "NVIDIA GeForce RTX 3060, 12288 MiB\n"})()

    monkeypatch.setattr(subprocess, "run", fake_run)
    app, _ = _app(monkeypatch, tmp_path)
    with TestClient(app) as c:
        d = c.get("/v1/hardware").json()
    assert d["source"] == "nvidia-smi"
    assert d["gpu"] == {"name": "NVIDIA GeForce RTX 3060", "total_vram_mb": 12288}


def test_hardware_honest_null_when_nvidia_smi_unavailable(monkeypatch, tmp_path):
    """No GPU tooling → gpu: null (never a fake number)."""
    import subprocess

    def boom(cmd, *args, **kwargs):
        raise FileNotFoundError("nvidia-smi not installed")

    monkeypatch.setattr(subprocess, "run", boom)
    app, _ = _app(monkeypatch, tmp_path)
    with TestClient(app) as c:
        d = c.get("/v1/hardware").json()
    assert d["source"] == "nvidia-smi"
    assert d["gpu"] is None

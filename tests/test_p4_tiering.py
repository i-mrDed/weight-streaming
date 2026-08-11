"""Offline tests for auto-tiering (server/tiering.py + /v1/tiering/*).

Covers the pure decision rule (prompt length + reasoning demand), config
validation + normalization (default Gemma pair, ~ expansion, on-disk
resolution), persistence fallback, and the three endpoints via TestClient
with a stub manager so no real model is loaded and no network is touched.
"""

import json

import pytest
from fastapi.testclient import TestClient

from weight_stream.server import tiering
from weight_stream.server.model_manager import ModelManager
from weight_stream.server.api_server import create_app
from weight_stream.server.config import ServerConfig


# ── pure decision rule ─────────────────────────────────────────────────


def _cfg(**over):
    c = tiering.default_config()
    c.update(over)
    return c


def test_decide_fast_for_short_prompt():
    tier, reason = tiering.decide_tier(
        _cfg(), [{"role": "user", "content": "hi"}])
    assert tier == "fast"
    assert "≤" in reason


def test_decide_quality_for_long_prompt():
    long = "x" * (tiering.DEFAULT_MAX_PROMPT_CHARS + 1)
    tier, reason = tiering.decide_tier(
        _cfg(), [{"role": "user", "content": long}])
    assert tier == "quality"
    assert ">" in reason


def test_decide_quality_for_high_reasoning_short_prompt():
    tier, reason = tiering.decide_tier(
        _cfg(), [{"role": "user", "content": "short"}],
        options={"reasoning_mode": "high"})
    assert tier == "quality"
    assert "reasoning" in reason


def test_decide_fast_for_low_reasoning():
    tier, _ = tiering.decide_tier(
        _cfg(), [{"role": "user", "content": "short"}],
        options={"reasoning_mode": "low"})
    assert tier == "fast"


def test_decide_disabled_returns_fast_with_honest_reason():
    tier, reason = tiering.decide_tier(_cfg(enabled=False), [])
    assert tier == "fast"
    assert "disabled" in reason


def test_decide_length_counts_all_messages():
    messages = [
        {"role": "system", "content": "s" * 100},
        {"role": "user", "content": "u" * 100},
    ]
    # Total 200 chars; raise threshold above it → fast, below → quality.
    tier_fast, _ = tiering.decide_tier(_cfg(max_prompt_chars=500), messages)
    tier_qual, _ = tiering.decide_tier(_cfg(max_prompt_chars=50), messages)
    assert tier_fast == "fast"
    assert tier_qual == "quality"


def test_prompt_text_concatenates_string_contents_only():
    assert tiering.prompt_text([
        {"role": "user", "content": "a"},
        {"role": "assistant", "content": "b"},
        {"role": "user", "content": ["array", "ignored"]},
        {"role": "user"},  # no content
    ]) == "a\nb"


# ── config validation + normalization ──────────────────────────────────


def test_default_config_has_two_tiers_and_gemma_ids():
    c = tiering.default_config()
    assert c["enabled"] is True
    assert c["fast"]["model_id"] == "gemma-4-12b-qat-mtp"
    assert c["quality"]["model_id"] == "gemma-4-26b-qat-mtp"
    assert c["max_prompt_chars"] > 0


def test_validate_config_accepts_defaults_if_files_exist():
    # Defaults point at the reference rig's Gemma pair. When the files are
    # actually there the config is valid; otherwise it reports them as
    # missing (honest, still deterministic).
    problems = tiering.validate_config(tiering.default_config())
    if tiering.default_config()["fast"]["model_path"] is None:
        pytest.skip("no default paths")
    missing = [p for p in problems if "file not found" in p]
    # Either everything valid, or only the on-disk reality is reported —
    # never a structural error (model_id/max_prompt_chars are fine).
    assert not [p for p in problems if "model_id" in p or "max_prompt_chars" in p]


def test_validate_config_rejects_missing_required_fields():
    with pytest.raises(ValueError):
        tiering.validate_config("nope")
    problems = tiering.validate_config({"fast": {}, "quality": {}})
    assert any("model_id is required" in p for p in problems)
    assert any("model_path is required" in p for p in problems)


def test_validate_config_rejects_bad_types():
    problems = tiering.validate_config({
        "enabled": "yes",
        "max_prompt_chars": -5,
        "reasoning_quality": "ultra",
        "fast": {"model_id": "a", "model_path": "x"},
        "quality": {"model_id": "b", "model_path": "y"},
    })
    assert any("enabled must be a boolean" in p for p in problems)
    assert any("max_prompt_chars must be a positive integer" in p for p in problems)
    assert any("reasoning_quality must be one of" in p for p in problems)


def test_normalize_config_fills_defaults_and_expands_tilde(monkeypatch):
    monkeypatch.setenv("WS_TIERING_FILE", "data/tiering.json")
    c = tiering.normalize_config({})
    assert c["enabled"] is True
    assert c["fast"]["model_path"]
    assert c["quality"]["extra_args"]
    # Custom entry survives; defaults fill the rest.
    c2 = tiering.normalize_config({
        "fast": {"model_id": "mine", "model_path": "C:/models/x.gguf"},
    })
    assert c2["fast"]["model_id"] == "mine"
    assert c2["quality"]["model_id"] == "gemma-4-26b-qat-mtp"


def test_resolve_state_reports_file_resolution(tmp_path, monkeypatch):
    monkeypatch.setenv("WS_TIERING_FILE", str(tmp_path / "t.json"))
    real = tmp_path / "real.gguf"
    real.write_bytes(b"GGUF")
    c = tiering.normalize_config({
        "fast": {"model_id": "f", "model_path": str(real)},
        "quality": {"model_id": "q", "model_path": str(tmp_path / "ghost.gguf")},
    })
    st = tiering.resolve_state(c)
    assert st["fast"]["file_resolved"] is True
    assert st["quality"]["file_resolved"] is False


def test_load_config_falls_back_to_defaults_on_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("WS_TIERING_FILE", str(tmp_path / "none.json"))
    assert tiering.load_config()["enabled"] is True


def test_save_config_persists_and_round_trips(tmp_path, monkeypatch):
    monkeypatch.setenv("WS_TIERING_FILE", str(tmp_path / "t.json"))
    real = tmp_path / "real.gguf"
    real.write_bytes(b"GGUF")
    cfg = tiering.default_config()
    cfg["fast"]["model_path"] = str(real)
    cfg["quality"]["model_path"] = str(real)
    saved = tiering.save_config(cfg)
    assert saved["enabled"] is True
    again = tiering.load_config()
    assert again["fast"]["model_path"] == str(real)


def test_save_config_raises_on_missing_file(tmp_path, monkeypatch):
    monkeypatch.setenv("WS_TIERING_FILE", str(tmp_path / "t.json"))
    cfg = tiering.default_config()
    cfg["fast"]["model_path"] = str(tmp_path / "nope.gguf")
    with pytest.raises(ValueError, match="file not found"):
        tiering.save_config(cfg)


# ── endpoints (stub manager — no real load) ────────────────────────────
class _StubManager:
    """Loads are recorded, never performed — the route endpoint must not
    spawn a real llama-server in tests."""

    def __init__(self):
        self.loaded = []
        # path → model_id the manager claims is ALREADY loaded (reuse tests)
        self.pretend_loaded = {}

    async def load_or_get(self, model_id, model_path, **kwargs):
        self.loaded.append({"id": model_id, "path": model_path, **kwargs})

    def find_loaded_path(self, path):
        return self.pretend_loaded.get(path)


@pytest.fixture
def real_gguf(tmp_path):
    f = tmp_path / "m.gguf"
    f.write_bytes(b"GGUF")
    return str(f)


@pytest.fixture
def isolated_history(tmp_path, monkeypatch):
    """Point the usage recorder's JSONL at a temp file so tier_route events
    written by endpoint tests never touch the real data/usage_history.jsonl."""
    monkeypatch.setenv("WS_USAGE_HISTORY_FILE", str(tmp_path / "usage.jsonl"))
    return str(tmp_path / "usage.jsonl")


def test_load_endpoint_forwards_extra_args(tmp_path, monkeypatch, real_gguf):
    """EXP-023: /v1/models/load must accept and forward extra_args (the
    schema field was missing until now — the endpoint silently dropped it,
    wasting a whole penalty matrix on flags that never reached llama-server)."""
    monkeypatch.setenv("WS_TIERING_FILE", str(tmp_path / "t.json"))
    monkeypatch.setenv("WS_USAGE_HISTORY_FILE", str(tmp_path / "usage.jsonl"))
    captured = {}

    async def fake_load(self, model_id, model_path, **kwargs):
        captured.update(kwargs)
        return {"status": "loaded", "model_id": model_id}

    monkeypatch.setattr(ModelManager, "load", fake_load)
    app, _ = create_app(ServerConfig())
    client = TestClient(app)
    r = client.post("/v1/models/load", json={
        "model_id": "m", "model_path": real_gguf,
        "extra_args": "--spec-type draft-mtp --spec-draft-model C:/x.gguf",
    })
    assert r.status_code == 200, r.text
    assert captured.get("extra_args") == (
        "--spec-type draft-mtp --spec-draft-model C:/x.gguf")


def test_get_tiering_config_returns_defaults(tmp_path, monkeypatch):
    monkeypatch.setenv("WS_TIERING_FILE", str(tmp_path / "t.json"))
    app, _ = create_app(ServerConfig())
    client = TestClient(app)
    r = client.get("/v1/tiering/config")
    assert r.status_code == 200
    body = r.json()
    assert body["config"]["fast"]["model_id"] == "gemma-4-12b-qat-mtp"
    assert "problems" in body


def test_put_tiering_config_validates_and_saves(tmp_path, monkeypatch, real_gguf):
    monkeypatch.setenv("WS_TIERING_FILE", str(tmp_path / "t.json"))
    app, _ = create_app(ServerConfig())
    client = TestClient(app)
    payload = {
        "enabled": True,
        "max_prompt_chars": 3000,
        "fast": {"model_id": "f", "model_path": real_gguf},
        "quality": {"model_id": "q", "model_path": real_gguf},
    }
    r = client.put("/v1/tiering/config", json=payload)
    assert r.status_code == 200, r.text
    saved = r.json()["config"]
    assert saved["max_prompt_chars"] == 3000
    assert saved["fast"]["file_resolved"] is True
    # Persisted on disk.
    on_disk = json.loads((tmp_path / "t.json").read_text(encoding="utf-8"))
    assert on_disk["fast"]["model_id"] == "f"


def test_put_tiering_config_rejects_missing_file(tmp_path, monkeypatch):
    monkeypatch.setenv("WS_TIERING_FILE", str(tmp_path / "t.json"))
    app, _ = create_app(ServerConfig())
    client = TestClient(app)
    payload = {
        "fast": {"model_id": "f", "model_path": "C:/nope/ghost.gguf"},
        "quality": {"model_id": "q", "model_path": "C:/nope/ghost2.gguf"},
    }
    r = client.put("/v1/tiering/config", json=payload)
    assert r.status_code == 400
    assert "file not found" in r.json()["detail"]


def _stub_app(tmp_path, monkeypatch, real_gguf, payload=None):
    monkeypatch.setenv("WS_TIERING_FILE", str(tmp_path / "t.json"))
    # Route tests record tier_route events — keep them OUT of the real
    # data/usage_history.jsonl (isolated per-test usage store).
    monkeypatch.setenv("WS_USAGE_HISTORY_FILE", str(tmp_path / "usage.jsonl"))
    app, _ = create_app(ServerConfig())
    stub = _StubManager()
    app.state.tiering_manager = stub
    client = TestClient(app)
    if payload is not None:
        assert client.put("/v1/tiering/config", json=payload).status_code == 200
    return client, stub


def test_route_short_prompt_uses_fast_tier(tmp_path, monkeypatch, real_gguf):
    payload = {
        "fast": {"model_id": "fast-m", "model_path": real_gguf},
        "quality": {"model_id": "qual-m", "model_path": real_gguf},
    }
    client, stub = _stub_app(tmp_path, monkeypatch, real_gguf, payload)
    r = client.post("/v1/tiering/route",
                    json={"messages": [{"role": "user", "content": "hi"}]})
    assert r.status_code == 200
    body = r.json()
    assert body["tier"] == "fast"
    assert body["model_id"] == "fast-m"
    assert body["model_path"] == real_gguf
    assert "reason" in body
    # The stub recorded the auto-load (no real llama-server spawned).
    assert stub.loaded and stub.loaded[0]["id"] == "fast-m"


def test_default_pair_carries_exp022_recipe():
    """EXP-023 regression: the shipped defaults must match the measured
    bench recipe (`-fa on` + draft flags) and load with a real n_ctx — the
    server-wide 2048 would truncate long answers mid-thought. The quality
    tier uses a smaller ctx: the 26B pays real decode speed for KV size
    (EXP-023: warm 34.1 @ 8192 vs 39.2 @ 2048), while the VRAM-resident
    12B does not."""
    for tier in ("fast", "quality"):
        entry = tiering.default_config()[tier]
        assert "-fa on" in entry["extra_args"], f"{tier} missing -fa on"
    assert tiering.default_config()["fast"]["n_ctx"] == 8192
    assert tiering.default_config()["quality"]["n_ctx"] == 4096
    # EXP-023: per-tier output budgets — the fast tier is for quick answers
    # and must not burn the full 8192 on a degenerate repetition loop.
    assert tiering.default_config()["fast"]["max_tokens"] == 2048
    assert tiering.default_config()["quality"]["max_tokens"] == 8192


def test_route_reports_tier_max_tokens(tmp_path, monkeypatch, real_gguf):
    """EXP-023: the route response carries the tier's max_tokens so the
    caller (⚡ Auto chat / gate) can clamp its request budget."""
    payload = {
        "fast": {"model_id": "fast-m", "model_path": real_gguf, "max_tokens": 2048},
        "quality": {"model_id": "qual-m", "model_path": real_gguf},
    }
    client, stub = _stub_app(tmp_path, monkeypatch, real_gguf, payload)
    r = client.post("/v1/tiering/route",
                    json={"messages": [{"role": "user", "content": "hi"}]})
    assert r.status_code == 200
    assert r.json()["max_tokens"] == 2048


def test_pin_sets_per_tier_max_tokens(tmp_path, monkeypatch, real_gguf):
    """Pinning a model from the Hub/scan must set the same per-tier
    max_tokens contract as the shipped defaults."""
    monkeypatch.setenv("WS_TIERING_FILE", str(tmp_path / "t.json"))
    main = tmp_path / "m.gguf"; main.write_bytes(b"GGUF")
    tiering.pin_tier("fast", ["m.gguf"], [str(tmp_path)])
    tiering.pin_tier("quality", ["m.gguf"], [str(tmp_path)])
    cfg = tiering.load_config()
    assert cfg["fast"]["max_tokens"] == 2048
    assert cfg["quality"]["max_tokens"] == 8192


def test_route_forwards_n_ctx_from_config(tmp_path, monkeypatch, real_gguf):
    """EXP-023 regression: the route must pass the tier's n_ctx to the load
    (not the server-wide 2048) so long generations are not truncated."""
    payload = {
        "fast": {"model_id": "fast-m", "model_path": real_gguf, "n_ctx": 8192},
        "quality": {"model_id": "qual-m", "model_path": real_gguf},
    }
    client, stub = _stub_app(tmp_path, monkeypatch, real_gguf, payload)
    r = client.post("/v1/tiering/route",
                    json={"messages": [{"role": "user", "content": "hi"}]})
    assert r.status_code == 200
    assert stub.loaded[0].get("n_ctx") == 8192


def test_route_with_null_n_ctx_skips_the_kwarg(tmp_path, monkeypatch, real_gguf):
    """An explicit null n_ctx (e.g. a hand-edited config) must not forward
    a literal None (load() pops n_ctx without coalescing) — the route
    omits the kwarg so the server default applies."""
    payload = {
        "fast": {"model_id": "fast-m", "model_path": real_gguf, "n_ctx": None},
        "quality": {"model_id": "qual-m", "model_path": real_gguf},
    }
    client, stub = _stub_app(tmp_path, monkeypatch, real_gguf, payload)
    r = client.post("/v1/tiering/route",
                    json={"messages": [{"role": "user", "content": "hi"}]})
    assert r.status_code == 200
    assert "n_ctx" not in stub.loaded[0]


def test_route_long_prompt_uses_quality_tier(tmp_path, monkeypatch, real_gguf):
    payload = {
        "max_prompt_chars": 100,
        "fast": {"model_id": "fast-m", "model_path": real_gguf},
        "quality": {"model_id": "qual-m", "model_path": real_gguf},
    }
    client, stub = _stub_app(tmp_path, monkeypatch, real_gguf, payload)
    r = client.post("/v1/tiering/route", json={
        "messages": [{"role": "user", "content": "x" * 200}],
    })
    assert r.status_code == 200
    assert r.json()["tier"] == "quality"
    assert r.json()["model_id"] == "qual-m"
    assert stub.loaded and stub.loaded[0]["id"] == "qual-m"


# ── pin endpoint (Hub recommended → disk) ─────────────────────────────


def test_pin_finds_files_and_wires_draft(tmp_path, monkeypatch):
    monkeypatch.setenv("WS_TIERING_FILE", str(tmp_path / "t.json"))
    # Model dir with main + MTP draft (the Gemma layout).
    model_dir = tmp_path / "models"
    (model_dir / "Gemma4-12B-QAT" / "MTP").mkdir(parents=True)
    main = model_dir / "Gemma4-12B-QAT" / "gemma-4-12B-it-qat-UD-Q4_K_XL.gguf"
    main.write_bytes(b"GGUF")
    draft = (model_dir / "Gemma4-12B-QAT" / "MTP" /
             "mtp-gemma-4-12B-it-Q8_0.gguf")
    draft.write_bytes(b"GGUF")
    monkeypatch.setenv("WS_MODELS_DIR", str(model_dir))
    app, _ = create_app(ServerConfig())
    client = TestClient(app)
    r = client.post("/v1/tiering/pin", json={
        "tier": "fast",
        "files": ["gemma-4-12B-it-qat-UD-Q4_K_XL.gguf",
                  "mtp-gemma-4-12B-it-Q8_0.gguf"],
    })
    assert r.status_code == 200, r.text
    cfg = r.json()["config"]
    assert cfg["fast"]["model_path"].endswith(
        "gemma-4-12B-it-qat-UD-Q4_K_XL.gguf")
    assert "draft-mtp" in cfg["fast"]["extra_args"]
    assert str(draft).replace("\\", "/") in cfg["fast"]["extra_args"]
    # Other tier untouched.
    assert cfg["quality"]["model_id"] == "gemma-4-26b-qat-mtp"


def test_pin_missing_file_returns_400(tmp_path, monkeypatch):
    monkeypatch.setenv("WS_TIERING_FILE", str(tmp_path / "t.json"))
    monkeypatch.setenv("WS_MODELS_DIR", str(tmp_path / "empty"))
    app, _ = create_app(ServerConfig())
    client = TestClient(app)
    r = client.post("/v1/tiering/pin", json={
        "tier": "fast",
        "files": ["ghost.gguf"],
    })
    assert r.status_code == 400
    assert "not found on disk" in r.json()["detail"]


def test_pin_invalid_tier_returns_400(tmp_path, monkeypatch):
    monkeypatch.setenv("WS_TIERING_FILE", str(tmp_path / "t.json"))
    app, _ = create_app(ServerConfig())
    client = TestClient(app)
    r = client.post("/v1/tiering/pin", json={"tier": "turbo", "files": []})
    assert r.status_code == 400
    assert "'fast' or 'quality'" in r.json()["detail"]


def test_route_disabled_returns_409(tmp_path, monkeypatch, real_gguf):
    payload = {
        "enabled": False,
        "fast": {"model_id": "f", "model_path": real_gguf},
        "quality": {"model_id": "q", "model_path": real_gguf},
    }
    client, _ = _stub_app(tmp_path, monkeypatch, real_gguf, payload)
    r = client.post("/v1/tiering/route", json={"messages": []})
    assert r.status_code == 409
    assert "disabled" in r.json()["detail"]


# ── unpin endpoint (Hub/Settings → restore shipped default) ───────────


def test_unpin_restores_default_tier(tmp_path, monkeypatch, real_gguf):
    monkeypatch.setenv("WS_TIERING_FILE", str(tmp_path / "t.json"))
    app, _ = create_app(ServerConfig())
    client = TestClient(app)
    # Pin a non-default model to fast first (a real file on disk).
    r = client.put("/v1/tiering/config", json={
        "fast": {"model_id": "my-model", "model_path": real_gguf},
        "quality": {"model_id": "gemma-4-26b-qat-mtp",
                    "model_path": real_gguf},
    })
    assert r.status_code == 200
    body = r.json()["config"]
    assert body["fast"]["model_id"] == "my-model"
    assert body["fast"]["is_default"] is False
    # Unpin only fast — quality must be untouched.
    r = client.post("/v1/tiering/unpin", json={"tier": "fast"})
    assert r.status_code == 200, r.text
    cfg = r.json()["config"]
    assert cfg["fast"]["model_id"] == "gemma-4-12b-qat-mtp"
    assert cfg["fast"]["is_default"] is True
    assert cfg["quality"]["model_id"] == "gemma-4-26b-qat-mtp"


def test_unpin_invalid_tier_returns_400(tmp_path, monkeypatch):
    monkeypatch.setenv("WS_TIERING_FILE", str(tmp_path / "t.json"))
    app, _ = create_app(ServerConfig())
    client = TestClient(app)
    r = client.post("/v1/tiering/unpin", json={"tier": "turbo"})
    assert r.status_code == 400
    assert "'fast' or 'quality'" in r.json()["detail"]


def test_unpin_persists_to_disk(tmp_path, monkeypatch, real_gguf):
    monkeypatch.setenv("WS_TIERING_FILE", str(tmp_path / "t.json"))
    app, _ = create_app(ServerConfig())
    client = TestClient(app)
    assert client.put("/v1/tiering/config", json={
        "fast": {"model_id": "mine", "model_path": real_gguf},
        "quality": {"model_id": "q", "model_path": real_gguf},
    }).status_code == 200
    assert client.post("/v1/tiering/unpin",
                       json={"tier": "fast"}).status_code == 200
    on_disk = json.loads((tmp_path / "t.json").read_text(encoding="utf-8"))
    assert on_disk["fast"]["model_id"] == "gemma-4-12b-qat-mtp"


# ── route reuse-by-path + tiering stats ───────────────────────────────


def test_route_reuses_already_loaded_model(tmp_path, monkeypatch, real_gguf):
    payload = {
        "fast": {"model_id": "fast-m", "model_path": real_gguf},
        "quality": {"model_id": "qual-m", "model_path": real_gguf},
    }
    client, stub = _stub_app(tmp_path, monkeypatch, real_gguf, payload)
    # The same file is already resident under a DIFFERENT model_id (the
    # user loaded it manually) — the route must reuse it, not reload.
    stub.pretend_loaded[real_gguf] = "manual-id"
    r = client.post("/v1/tiering/route",
                    json={"messages": [{"role": "user", "content": "hi"}]})
    assert r.status_code == 200
    body = r.json()
    assert body["tier"] == "fast"
    assert body["model_id"] == "manual-id"  # effective loaded id
    assert body["reused"] is True
    assert stub.loaded == []  # no evict+reload happened


def test_route_not_reused_when_not_loaded(tmp_path, monkeypatch, real_gguf):
    payload = {
        "fast": {"model_id": "fast-m", "model_path": real_gguf},
        "quality": {"model_id": "qual-m", "model_path": real_gguf},
    }
    client, stub = _stub_app(tmp_path, monkeypatch, real_gguf, payload)
    r = client.post("/v1/tiering/route",
                    json={"messages": [{"role": "user", "content": "hi"}]})
    assert r.status_code == 200
    assert r.json()["model_id"] == "fast-m"
    assert r.json()["reused"] is False
    assert stub.loaded and stub.loaded[0]["id"] == "fast-m"


def test_route_records_event_and_stats_aggregate(
    tmp_path, monkeypatch, real_gguf, isolated_history
):
    payload = {
        "max_prompt_chars": 100,
        "fast": {"model_id": "fast-m", "model_path": real_gguf},
        "quality": {"model_id": "qual-m", "model_path": real_gguf},
    }
    client, _ = _stub_app(tmp_path, monkeypatch, real_gguf, payload)
    # Two routes: one fast, one quality (long prompt).
    r1 = client.post("/v1/tiering/route",
                     json={"messages": [{"role": "user", "content": "hi"}]})
    r2 = client.post("/v1/tiering/route", json={
        "messages": [{"role": "user", "content": "x" * 200}],
    })
    assert r1.status_code == 200 and r2.status_code == 200
    st = client.get("/v1/tiering/stats").json()
    assert st["enabled"] is True
    assert st["total_routes"] == 2
    assert st["by_tier"] == {"fast": 1, "quality": 1}
    assert st["count"] == 2
    assert st["recent"][0]["tier"] == "fast"
    # Generation history must NOT contain the event records (no mixing).
    hist = client.get("/v1/usage/history").json()
    assert hist["count"] == 0


def test_tiering_stats_empty_on_fresh_install(tmp_path, monkeypatch):
    monkeypatch.setenv("WS_TIERING_FILE", str(tmp_path / "t.json"))
    monkeypatch.setenv("WS_USAGE_HISTORY_FILE", str(tmp_path / "usage.jsonl"))
    app, _ = create_app(ServerConfig())
    client = TestClient(app)
    st = client.get("/v1/tiering/stats").json()
    assert st["total_routes"] == 0
    assert st["by_tier"] == {}
    assert st["recent"] == []


# ── preview endpoint (decide WITHOUT loading) ─────────────────────────


def test_preview_returns_decision_without_loading(
    tmp_path, monkeypatch, real_gguf
):
    payload = {
        "fast": {"model_id": "fast-m", "model_path": real_gguf},
        "quality": {"model_id": "qual-m", "model_path": real_gguf},
    }
    client, stub = _stub_app(tmp_path, monkeypatch, real_gguf, payload)
    r = client.post("/v1/tiering/preview",
                    json={"messages": [{"role": "user", "content": "hi"}]})
    assert r.status_code == 200
    body = r.json()
    assert body["tier"] == "fast"
    assert "reason" in body
    assert body["model_id"] == "fast-m"
    assert body["model_path"] == real_gguf
    # The critical property: preview NEVER loads anything.
    assert stub.loaded == []


def test_preview_long_prompt_picks_quality(tmp_path, monkeypatch, real_gguf):
    payload = {
        "max_prompt_chars": 100,
        "fast": {"model_id": "fast-m", "model_path": real_gguf},
        "quality": {"model_id": "qual-m", "model_path": real_gguf},
    }
    client, _ = _stub_app(tmp_path, monkeypatch, real_gguf, payload)
    r = client.post("/v1/tiering/preview", json={
        "messages": [{"role": "user", "content": "x" * 200}],
    })
    assert r.status_code == 200
    assert r.json()["tier"] == "quality"


def test_preview_disabled_returns_409(tmp_path, monkeypatch, real_gguf):
    payload = {
        "enabled": False,
        "fast": {"model_id": "f", "model_path": real_gguf},
        "quality": {"model_id": "q", "model_path": real_gguf},
    }
    client, _ = _stub_app(tmp_path, monkeypatch, real_gguf, payload)
    r = client.post("/v1/tiering/preview", json={"messages": []})
    assert r.status_code == 409
    assert "disabled" in r.json()["detail"]


# ── debug context includes the tiering snapshot ───────────────────────


def test_debug_context_includes_tiering_summary(
    tmp_path, monkeypatch, real_gguf, isolated_history
):
    payload = {
        "max_prompt_chars": 100,
        "fast": {"model_id": "fast-m", "model_path": real_gguf},
        "quality": {"model_id": "qual-m", "model_path": real_gguf},
    }
    client, _ = _stub_app(tmp_path, monkeypatch, real_gguf, payload)
    # Two real route decisions → two tier_route events.
    assert client.post("/v1/tiering/route", json={
        "messages": [{"role": "user", "content": "hi"}],
    }).status_code == 200
    assert client.post("/v1/tiering/route", json={
        "messages": [{"role": "user", "content": "x" * 200}],
    }).status_code == 200
    ctx = client.get("/v1/debug/context").json()
    assert "tiering" in ctx
    assert ctx["tiering"]["enabled"] is True
    assert ctx["tiering"]["total_routes"] == 2
    assert ctx["tiering"]["by_tier"] == {"fast": 1, "quality": 1}


def test_collect_debug_context_tiering_optional():
    from weight_stream.issues.context import collect_debug_context
    base = collect_debug_context()
    assert "tiering" not in base
    with_t = collect_debug_context(tiering={"enabled": True, "total_routes": 0})
    assert with_t["tiering"] == {"enabled": True, "total_routes": 0}

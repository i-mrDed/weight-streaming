"""Tests for WebSocket /v1/stream security (fix/ws-security).

- Origin not in allowlist -> connection refused (4408) BEFORE accept
- WS_API_TOKEN set + missing/wrong Bearer -> 4401
- WS_API_TOKEN set + correct Bearer -> accepted (can send generate)
- non-browser (no Origin) still allowed when no token configured
"""
import os

import pytest
from starlette.testclient import TestClient

from weight_stream.server import api_server


def _make_client(token: str = "", extra_origins: str = ""):
    """Create app + TestClient with optional WS_API_TOKEN."""
    old_token = os.environ.get("WS_API_TOKEN")
    old_origins = os.environ.get("WS_CORS_ORIGINS")
    if token:
        os.environ["WS_API_TOKEN"] = token
    else:
        os.environ.pop("WS_API_TOKEN", None)
    if extra_origins:
        os.environ["WS_CORS_ORIGINS"] = extra_origins
    else:
        os.environ.pop("WS_CORS_ORIGINS", None)
    try:
        app, manager = api_server.create_app()
        return TestClient(app)
    finally:
        # restore env
        if old_token is None:
            os.environ.pop("WS_API_TOKEN", None)
        else:
            os.environ["WS_API_TOKEN"] = old_token
        if old_origins is None:
            os.environ.pop("WS_CORS_ORIGINS", None)
        else:
            os.environ["WS_CORS_ORIGINS"] = old_origins


class TestWsOriginGuard:
    def test_evil_origin_refused(self):
        client = _make_client()
        with pytest.raises(Exception):
            with client.websocket_connect(
                "/v1/stream",
                headers={"Origin": "https://evil.example.com"},
            ) as ws:
                ws.receive_json()

    def test_loopback_origin_allowed(self):
        client = _make_client()
        # must accept — send a bad first message to observe server response
        with client.websocket_connect(
            "/v1/stream",
            headers={"Origin": "http://127.0.0.1:8765"},
        ) as ws:
            ws.send_json({"type": "wrong"})
            msg = ws.receive_json()
            assert msg.get("type") == "error"

    def test_scheme_mismatch_refused(self):
        # allowlist is http-only; https origin must NOT pass (old code
        # ignored the scheme entirely)
        client = _make_client()
        with pytest.raises(Exception):
            with client.websocket_connect(
                "/v1/stream",
                headers={"Origin": "https://127.0.0.1:8765"},
            ) as ws:
                ws.receive_json()

    def test_non_allowlisted_port_refused(self):
        # "http://127.0.0.1" (no port) must NOT match every loopback port
        # (old code: a.port is None -> any port passed)
        client = _make_client()
        with pytest.raises(Exception):
            with client.websocket_connect(
                "/v1/stream",
                headers={"Origin": "http://127.0.0.1:9999"},
            ) as ws:
                ws.receive_json()

    def test_default_port_folds_to_no_port(self):
        # browsers omit the default port in Origin; explicit :80 must be
        # treated the same as no port (matches "http://127.0.0.1")
        client = _make_client()
        with client.websocket_connect(
            "/v1/stream",
            headers={"Origin": "http://127.0.0.1:80"},
        ) as ws:
            ws.send_json({"type": "wrong"})
            msg = ws.receive_json()
            assert msg.get("type") == "error"

    def test_custom_origin_via_env_allowed(self):
        client = _make_client(extra_origins="http://localhost:3000")
        with client.websocket_connect(
            "/v1/stream",
            headers={"Origin": "http://localhost:3000"},
        ) as ws:
            ws.send_json({"type": "wrong"})
            msg = ws.receive_json()
            assert msg.get("type") == "error"


class TestWsTokenGuard:
    def test_missing_token_refused(self):
        client = _make_client(token="s3cret")
        with pytest.raises(Exception):
            with client.websocket_connect(
                "/v1/stream",
                headers={"Origin": "http://127.0.0.1:8765"},
            ) as ws:
                ws.receive_json()

    def test_wrong_token_refused(self):
        client = _make_client(token="s3cret")
        with pytest.raises(Exception):
            with client.websocket_connect(
                "/v1/stream",
                headers={
                    "Origin": "http://127.0.0.1:8765",
                    "Authorization": "Bearer wrong",
                },
            ) as ws:
                ws.receive_json()

    def test_correct_token_allowed(self):
        client = _make_client(token="s3cret")
        with client.websocket_connect(
            "/v1/stream",
            headers={
                "Origin": "http://127.0.0.1:8765",
                "Authorization": "Bearer s3cret",
            },
        ) as ws:
            ws.send_json({"type": "wrong"})
            msg = ws.receive_json()
            assert msg.get("type") == "error"

    def test_no_token_no_origin_still_works(self):
        # non-browser client, no token configured -> allowed
        client = _make_client()
        with client.websocket_connect("/v1/stream") as ws:
            ws.send_json({"type": "wrong"})
            msg = ws.receive_json()
            assert msg.get("type") == "error"
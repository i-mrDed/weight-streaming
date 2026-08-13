"""Tests for MCPHost.close() robustness (2026-08-13 fix).

The mcp SDK >= 1.2 can raise GeneratorExit inside its internal TaskGroup
during stdio_client teardown; close() must not propagate it (previously
logged "Task exception was never retrieved" on model unload).
"""
import asyncio

import pytest

from weight_stream.server.mcp_host import MCPHost, MCPServerStore


def _host(tmp_path) -> MCPHost:
    store = MCPServerStore(file_path=str(tmp_path / "mcp.json"))
    return MCPHost(store=store)


class _FakeSession:
    """Session whose __aexit__ raises inside a task group style."""

    def __init__(self, name="s"):
        self.name = name
        self.exited = False

    async def __aexit__(self, *args):
        self.exited = True
        # simulate mcp SDK: raise GeneratorExit from within (like the
        # stdio_client TaskGroup does during teardown)
        raise GeneratorExit


class _FakeCtx:
    """Transport context manager whose __aexit__ also misbehaves."""

    def __init__(self, name="c"):
        self.name = name
        self.exited = False

    async def __aexit__(self, *args):
        self.exited = True
        raise RuntimeError("transport teardown failed")


def test_close_swallows_generator_exit(tmp_path):
    host = _host(tmp_path)
    host._sessions = {"s1": _FakeSession()}
    host._contexts = {"c1": _FakeCtx()}
    # must not raise despite GeneratorExit + RuntimeError in teardown
    asyncio.run(host.close())
    assert host._sessions == {}
    assert host._contexts == {}


def test_close_with_nothing(tmp_path):
    host = _host(tmp_path)
    asyncio.run(host.close())  # no-op, no crash
    assert host._sessions == {}


def test_close_waits_for_all(tmp_path):
    host = _host(tmp_path)
    s1, s2 = _FakeSession("a"), _FakeSession("b")
    host._sessions = {"a": s1, "b": s2}
    asyncio.run(host.close())
    assert s1.exited and s2.exited
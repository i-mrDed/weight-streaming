"""Tests for the built-in workspace tools (AGENT_TOOLS_PLAN.md).

Hermetic: state file + workspace root point into tmp_path via env vars
(WS_AGENT_FILE / WS_WORKSPACE_ROOT), exactly like WS_TIERING_FILE does for
tiering tests. No real model files, no network.
"""
import os

import pytest

from weight_stream.server import workspace_tools


@pytest.fixture
def root(tmp_path, monkeypatch):
    """A workspace with a couple of files + a symlink (for escape tests)."""
    ws = tmp_path / "ws"
    (ws / "src").mkdir(parents=True)
    (ws / "src" / "main.py").write_text("print('hello')", encoding="utf-8")
    (ws / "README.md").write_text("# Demo\n", encoding="utf-8")
    (ws / "big.bin").write_bytes(b"x" * (workspace_tools.MAX_READ_BYTES + 1000))
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    try:
        (ws / "evil_link").symlink_to(outside, target_is_directory=False)
    except OSError:
        pass  # no symlink permission → escape tests for symlink just won't apply
    monkeypatch.setenv("WS_AGENT_FILE", str(tmp_path / "agent.json"))
    monkeypatch.setenv("WS_WORKSPACE_ROOT", str(ws))
    # Fresh default config pointing at the workspace
    workspace_tools.save_config(workspace_tools.default_config())
    return ws


class TestPathGuard:
    def test_relative_path_inside(self, root):
        p = workspace_tools.resolve_within(str(root), "src/main.py")
        assert p == str((root / "src" / "main.py").resolve())

    def test_absolute_path_inside(self, root):
        p = workspace_tools.resolve_within(str(root), str(root / "README.md"))
        assert p == str((root / "README.md").resolve())

    def test_dotdot_escape_rejected(self, root, tmp_path):
        with pytest.raises(workspace_tools.ToolError) as ei:
            workspace_tools.resolve_within(str(root), "../outside.txt")
        assert ei.value.status == 403

    def test_absolute_outside_rejected(self, root, tmp_path):
        outside = tmp_path / "outside.txt"
        with pytest.raises(workspace_tools.ToolError) as ei:
            workspace_tools.resolve_within(str(root), str(outside))
        assert ei.value.status == 403

    def test_symlink_escape_rejected(self, root):
        link = root / "evil_link"
        if not link.is_symlink():
            pytest.skip("symlinks not permitted on this filesystem")
        with pytest.raises(workspace_tools.ToolError) as ei:
            workspace_tools.resolve_within(str(root), "evil_link")
        assert ei.value.status == 403

    def test_empty_path_rejected(self, root):
        with pytest.raises(workspace_tools.ToolError):
            workspace_tools.resolve_within(str(root), "")


class TestTools:
    def test_workspace_info(self, root):
        out = workspace_tools.call_tool("workspace_info", {})
        assert out["root"] == str(root)
        assert out["file_count"] == 4  # main.py, README.md, big.bin (+ symlink counted as file if present)
        assert out["total_bytes"] > 0

    def test_list_directory(self, root):
        out = workspace_tools.call_tool("list_directory", {"path": "."})
        names = {e["name"]: e for e in out["entries"]}
        assert "src" in names and names["src"]["type"] == "dir"
        assert "README.md" in names and names["README.md"]["type"] == "file"
        assert out["count"] == len(out["entries"])

    def test_read_file(self, root):
        out = workspace_tools.call_tool("read_file", {"path": "src/main.py"})
        assert out["content"] == "print('hello')"
        assert out["size"] == len("print('hello')")

    def test_read_file_absolute(self, root):
        out = workspace_tools.call_tool("read_file", {"path": str(root / "README.md")})
        assert out["content"] == "# Demo\n"

    def test_read_file_too_large_rejected(self, root):
        with pytest.raises(workspace_tools.ToolError) as ei:
            workspace_tools.call_tool("read_file", {"path": "big.bin"})
        assert "too large" in str(ei.value)

    def test_read_missing_file(self, root):
        with pytest.raises(workspace_tools.ToolError):
            workspace_tools.call_tool("read_file", {"path": "nope.txt"})

    def test_unknown_tool(self, root):
        with pytest.raises(workspace_tools.ToolError) as ei:
            workspace_tools.call_tool("rm_rf", {})
        assert ei.value.status == 404


class TestConfig:
    def test_round_trip(self, root, monkeypatch, tmp_path):
        cfg = workspace_tools.load_config()
        assert cfg["enabled"] is True
        assert cfg["workspace_root"] == str(root)
        # update via save → reload
        other = tmp_path / "ws2"
        other.mkdir()
        workspace_tools.save_config({"enabled": False, "workspace_root": str(other)})
        reloaded = workspace_tools.load_config()
        assert reloaded["enabled"] is False
        assert reloaded["workspace_root"] == str(other)
        # disabled → no tools
        assert workspace_tools.list_tools() == []

    def test_missing_root_disables_tools(self, monkeypatch, tmp_path):
        monkeypatch.setenv("WS_AGENT_FILE", str(tmp_path / "agent.json"))
        workspace_tools.save_config({"enabled": True, "workspace_root": str(tmp_path / "nope")})
        assert workspace_tools.list_tools() == []
        with pytest.raises(workspace_tools.ToolError) as ei:
            workspace_tools.call_tool("workspace_info", {})
        assert ei.value.status == 404

    def test_unreadable_file_falls_back_to_defaults(self, monkeypatch, tmp_path):
        monkeypatch.setenv("WS_AGENT_FILE", str(tmp_path / "agent.json"))
        (tmp_path / "agent.json").write_text("{not json", encoding="utf-8")
        cfg = workspace_tools.load_config()  # must not raise
        assert "workspace_root" in cfg

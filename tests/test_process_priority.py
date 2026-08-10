"""Tests for weight_stream.io.process_priority.

Covers both backends with injected fakes (no real priority changes in the
suite), plus one safe live round-trip on the host platform when supported.
"""

import os

import pytest

from weight_stream.io import process_priority as pp


class _FakeWin:
    """In-memory stand-in for the Win32 priority class of the process."""

    def __init__(self, initial=pp._NORMAL_PRIORITY_CLASS):
        self.current = initial
        self.set_calls = []
        self.fail_sets = False

    # patched in as pp._win_get_class / pp._win_set_class
    def get_class(self):
        return self.current

    def set_class(self, value):
        self.set_calls.append(value)
        if self.fail_sets:
            return False
        self.current = value
        return True


@pytest.fixture
def fake_win(monkeypatch):
    fake = _FakeWin()
    monkeypatch.setattr(pp, "_win_get_class", fake.get_class)
    monkeypatch.setattr(pp, "_win_set_class", fake.set_class)
    return fake


def test_windows_backend_lowers_and_restores(fake_win):
    mgr = pp.ProcessPriority(backend="windows")

    assert mgr.lower() is True
    assert fake_win.current == pp._BELOW_NORMAL_PRIORITY_CLASS
    assert mgr.is_lowered is True

    # Idempotent: a second lower must not overwrite the saved class.
    assert mgr.lower() is True
    assert fake_win.set_calls == [pp._BELOW_NORMAL_PRIORITY_CLASS]

    assert mgr.restore() is True
    assert fake_win.current == pp._NORMAL_PRIORITY_CLASS
    assert mgr.is_lowered is False


def test_windows_backend_restore_returns_to_original_class(fake_win):
    fake_win.current = pp._HIGH_PRIORITY_CLASS
    mgr = pp.ProcessPriority(backend="windows")

    assert mgr.lower() is True
    assert mgr.restore() is True
    assert fake_win.current == pp._HIGH_PRIORITY_CLASS


def test_windows_backend_reports_failure_honestly(fake_win):
    fake_win.fail_sets = True
    mgr = pp.ProcessPriority(backend="windows")

    assert mgr.lower() is False
    assert mgr.is_lowered is False


def test_posix_backend_lowers_and_restores(monkeypatch):
    calls = []

    def fake_nice(delta):
        calls.append(delta)
        return 0

    monkeypatch.setattr(pp, "_posix_nice", fake_nice)
    mgr = pp.ProcessPriority(backend="posix")

    assert mgr.lower() is True
    assert calls == [5]
    assert mgr.is_lowered is True

    assert mgr.restore() is True
    assert calls == [5, -5]
    assert mgr.is_lowered is False


def test_posix_backend_restore_failure_is_reported(monkeypatch):
    def fake_nice(delta):
        if delta < 0:
            raise PermissionError("requires privileges")
        return 0

    monkeypatch.setattr(pp, "_posix_nice", fake_nice)
    mgr = pp.ProcessPriority(backend="posix")

    assert mgr.lower() is True
    assert mgr.restore() is False
    assert mgr.is_lowered is True  # still lowered — honest state


def test_none_backend_is_unsupported_noop():
    mgr = pp.ProcessPriority(backend="none")
    assert mgr.lower() is False
    assert mgr.restore() is True  # nothing to restore
    info = mgr.describe()
    assert info["backend"] == "none"
    assert info["lowered"] is False


def test_describe_reflects_state(fake_win):
    mgr = pp.ProcessPriority(backend="windows")
    info = mgr.describe()
    assert info["priority_class"] == "normal"
    assert info["lowered"] is False

    mgr.lower()
    info = mgr.describe()
    assert info["priority_class"] == "below_normal"
    assert info["lowered"] is True
    assert "SetPriorityClass" in info["mechanism"]


def test_live_round_trip_on_host_platform():
    """Safe on any platform: lower then immediately restore."""
    mgr = pp.ProcessPriority()
    if mgr._backend == "none":
        pytest.skip("no priority backend on this platform")

    assert mgr.lower() is True
    assert mgr.is_lowered is True
    # Restore may fail on POSIX without privileges — that is honest
    # behavior, not a test failure; only Windows must round-trip.
    restored = mgr.restore()
    if mgr._backend == "windows":
        assert restored is True
        assert mgr.is_lowered is False
    else:
        assert isinstance(restored, bool)


class _FakeK32:
    """In-memory stand-in for kernel32 with OpenProcess/SetPriorityClass."""

    def __init__(self):
        self._next = 1
        self.handles = {}  # handle -> pid
        self.classes = {}  # handle -> priority class
        self.fail_open = False
        self.fail_set = False

    def GetCurrentProcess(self):
        return 0xDEAD

    def GetPriorityClass(self, handle):
        return self.classes.get(handle, pp._NORMAL_PRIORITY_CLASS)

    def SetPriorityClass(self, handle, value):
        if self.fail_set:
            return False
        self.classes[handle] = value
        return True

    def OpenProcess(self, access, inherit, pid):
        if self.fail_open:
            return None
        h = self._next
        self._next += 1
        self.handles[h] = pid
        self.classes[h] = pp._NORMAL_PRIORITY_CLASS
        return h

    def CloseHandle(self, handle):
        self.handles.pop(handle, None)
        return True


def test_lower_pid_lowers_child(monkeypatch):
    fake = _FakeK32()
    monkeypatch.setattr(pp, "_win_k32", lambda: fake)

    assert pp.lower_pid(1234) is True
    # The child was set below normal...
    assert list(fake.classes.values()) == [pp._BELOW_NORMAL_PRIORITY_CLASS]
    # ...and every opened handle was closed (no handle leak).
    assert fake.handles == {}


def test_lower_pid_open_failure_is_honest(monkeypatch):
    fake = _FakeK32()
    fake.fail_open = True
    monkeypatch.setattr(pp, "_win_k32", lambda: fake)

    assert pp.lower_pid(1234) is False


def test_lower_pid_set_failure_is_honest(monkeypatch):
    fake = _FakeK32()
    fake.fail_set = True
    monkeypatch.setattr(pp, "_win_k32", lambda: fake)

    assert pp.lower_pid(1234) is False


def test_lower_pid_noop_for_invalid_or_off_windows(monkeypatch):
    monkeypatch.setattr(pp, "_win_k32", lambda: None)
    assert pp.lower_pid(1234) is False  # off Windows → no-op

    fake = _FakeK32()
    monkeypatch.setattr(pp, "_win_k32", lambda: fake)
    assert pp.lower_pid(0) is False  # invalid pid short-circuits
    assert pp.lower_pid(None) is False
    assert fake.handles == {}


def test_module_level_singleton_api():
    # Module functions delegate to a shared instance and never raise.
    assert isinstance(pp.describe_process_priority(), dict)
    assert isinstance(pp.is_process_priority_lowered(), bool)

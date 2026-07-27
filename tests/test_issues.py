"""Tests for the issue tracking system."""
import os
import tempfile
from pathlib import Path

import pytest

from weight_stream.issues.models import (
    IssueCreate,
    IssueStatus,
    IssueUpdate,
    IssueVerify,
    Severity,
)
from weight_stream.issues.service import IssueService
from weight_stream.issues.store import IssueStore
from weight_stream.issues.context import collect_debug_context


@pytest.fixture
def svc(tmp_path):
    store = IssueStore(base_dir=tmp_path)
    return IssueService(store=store)


class TestIssueLifecycle:
    def test_create_and_get(self, svc):
        issue = svc.create(IssueCreate(
            title="Browse dialog closes early",
            description="Dialog disappears before I can select a file",
            severity=Severity.HIGH,
        ))
        assert issue.id.startswith("Report-ISSUE-")
        assert issue.status == IssueStatus.OPEN
        got = svc.get(issue.id)
        assert got is not None
        assert got.title == issue.title

    def test_list_filter_status(self, svc):
        svc.create(IssueCreate(title="Issue number one xx", description="Description long enough"))
        svc.create(IssueCreate(title="Issue number two xx", description="Description long enough"))
        all_i = svc.list()
        assert len(all_i) == 2
        open_i = svc.list(status="open")
        assert len(open_i) == 2

    def test_illegal_transition(self, svc):
        issue = svc.create(IssueCreate(
            title="Cannot jump to closed",
            description="Should not allow open -> closed directly",
        ))
        with pytest.raises(ValueError, match="Illegal transition"):
            svc.update(issue.id, IssueUpdate(status=IssueStatus.CLOSED))

    def test_fixed_requires_fields(self, svc):
        issue = svc.create(IssueCreate(
            title="Fixed needs root cause",
            description="Must provide analysis fields before fixed",
        ))
        svc.update(issue.id, IssueUpdate(status=IssueStatus.IN_PROGRESS))
        with pytest.raises(ValueError, match="root_cause"):
            svc.update(issue.id, IssueUpdate(status=IssueStatus.FIXED))

    def test_full_happy_path(self, svc):
        issue = svc.create(IssueCreate(
            title="Full lifecycle test case",
            description="Walk through open to closed with verify",
        ))
        issue = svc.update(issue.id, IssueUpdate(status=IssueStatus.IN_PROGRESS))
        assert issue.status == IssueStatus.IN_PROGRESS

        issue = svc.update(issue.id, IssueUpdate(
            status=IssueStatus.FIXED,
            root_cause="Missing import asyncio",
            fix_summary="Added import asyncio",
            verify_steps="1. Restart server\n2. Click Browse",
            commit="abc123",
        ))
        # auto-advances to verify_pending
        assert issue.status == IssueStatus.VERIFY_PENDING
        assert issue.root_cause is not None

        issue = svc.verify(issue.id, IssueVerify(verified=True, note="Works now"))
        assert issue.status == IssueStatus.CLOSED

    def test_verify_fail_reopens(self, svc):
        issue = svc.create(IssueCreate(
            title="Verify fail reopens issue",
            description="Should go back to in_progress when verify fails",
        ))
        svc.update(issue.id, IssueUpdate(status=IssueStatus.IN_PROGRESS))
        svc.update(issue.id, IssueUpdate(
            status=IssueStatus.FIXED,
            root_cause="bug",
            fix_summary="fix",
            verify_steps="try again",
        ))
        issue = svc.verify(issue.id, IssueVerify(verified=False, note="Still broken"))
        assert issue.status == IssueStatus.IN_PROGRESS

    def test_persist_across_service_instances(self, tmp_path):
        s1 = IssueService(store=IssueStore(base_dir=tmp_path))
        issue = s1.create(IssueCreate(
            title="Persistence check issue",
            description="Must survive new service instance",
        ))
        s2 = IssueService(store=IssueStore(base_dir=tmp_path))
        got = s2.get(issue.id)
        assert got is not None
        assert got.title == issue.title

    def test_export_markdown(self, svc):
        svc.create(IssueCreate(
            title="Export markdown test issue",
            description="Should appear in summary export",
        ))
        md = svc.export_markdown()
        assert "Issues Summary" in md
        assert "ISSUE-" in md


class TestDebugContext:
    def test_collect_basic(self):
        ctx = collect_debug_context(last_error="boom")
        assert "app_version" in ctx
        assert "python_version" in ctx
        assert "os" in ctx
        assert ctx["last_error"] == "boom"

    def test_redacts_secrets(self):
        os.environ["WS_SECRET_TOKEN"] = "super-secret-value"
        try:
            ctx = collect_debug_context()
            env = ctx.get("env", {})
            if "WS_SECRET_TOKEN" in env:
                assert env["WS_SECRET_TOKEN"] == "***REDACTED***"
        finally:
            del os.environ["WS_SECRET_TOKEN"]

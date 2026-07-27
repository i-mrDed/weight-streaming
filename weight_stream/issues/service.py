"""Issue service — create, update, verify, export."""
from __future__ import annotations

from typing import List, Optional

from .export_md import export_summary_markdown
from .models import (
    Issue,
    IssueCreate,
    IssueStatus,
    IssueUpdate,
    IssueVerify,
    Severity,
    TimelineEvent,
    _utcnow,
)
from .store import IssueStore


class IssueService:
    def __init__(self, store: IssueStore | None = None):
        self.store = store or IssueStore()

    def create(self, data: IssueCreate) -> Issue:
        now = _utcnow()
        issue_id = self.store.new_issue_id()
        issue = Issue(
            id=issue_id,
            title=data.title.strip(),
            description=data.description.strip(),
            steps_to_reproduce=data.steps_to_reproduce,
            expected=data.expected,
            actual=data.actual,
            severity=data.severity,
            status=IssueStatus.OPEN,
            created_at=now,
            updated_at=now,
            created_by=data.created_by,
            context=data.context or {},
            timeline=[
                TimelineEvent(at=now, event="created", by=data.created_by),
            ],
        )
        return self.store.create(issue)

    def get(self, issue_id: str) -> Optional[Issue]:
        return self.store.get(issue_id)

    def list(
        self,
        status: Optional[str] = None,
        severity: Optional[str] = None,
    ) -> List[Issue]:
        st = IssueStatus(status) if status else None
        return self.store.list(status=st, severity=severity)

    def update(self, issue_id: str, data: IssueUpdate) -> Issue:
        issue = self.store.get(issue_id)
        if not issue:
            raise ValueError(f"Issue {issue_id} not found")

        by = data.updated_by or "maintainer"
        now = _utcnow()

        if data.title is not None:
            issue.title = data.title.strip()
        if data.description is not None:
            issue.description = data.description.strip()
        if data.severity is not None:
            issue.severity = data.severity
        if data.root_cause is not None:
            issue.root_cause = data.root_cause
        if data.fix_summary is not None:
            issue.fix_summary = data.fix_summary
        if data.commit is not None:
            issue.commit = data.commit
        if data.test_notes is not None:
            issue.test_notes = data.test_notes
        if data.verify_steps is not None:
            issue.verify_steps = data.verify_steps

        if data.status is not None:
            new_status = data.status
            if new_status != issue.status:
                if not issue.can_transition_to(new_status):
                    raise ValueError(
                        f"Illegal transition: {issue.status.value} → {new_status.value}"
                    )
                # fixed requires fields
                if new_status == IssueStatus.FIXED:
                    # apply fields first then check
                    err = issue.require_fixed_fields()
                    if err:
                        raise ValueError(err)
                    # auto-move to verify_pending after fixed
                    issue.status = IssueStatus.FIXED
                    issue.timeline.append(TimelineEvent(
                        at=now, event="status:fixed", by=by, note=data.note,
                    ))
                    issue.status = IssueStatus.VERIFY_PENDING
                    issue.timeline.append(TimelineEvent(
                        at=now, event="status:verify_pending", by="system",
                        note="Auto-advanced after fixed",
                    ))
                elif new_status == IssueStatus.CLOSED:
                    if issue.status not in (
                        IssueStatus.VERIFIED,
                        IssueStatus.WONTFIX,
                        IssueStatus.DUPLICATE,
                    ):
                        raise ValueError(
                            "Can only close from verified, wontfix, or duplicate"
                        )
                    issue.status = new_status
                    issue.timeline.append(TimelineEvent(
                        at=now, event=f"status:{new_status.value}", by=by, note=data.note,
                    ))
                else:
                    issue.status = new_status
                    issue.timeline.append(TimelineEvent(
                        at=now, event=f"status:{new_status.value}", by=by, note=data.note,
                    ))
        elif data.note:
            issue.timeline.append(TimelineEvent(
                at=now, event="note", by=by, note=data.note,
            ))

        return self.store.update(issue)

    def verify(self, issue_id: str, data: IssueVerify) -> Issue:
        issue = self.store.get(issue_id)
        if not issue:
            raise ValueError(f"Issue {issue_id} not found")

        now = _utcnow()
        by = data.verified_by or "local-user"

        if issue.status not in (IssueStatus.FIXED, IssueStatus.VERIFY_PENDING):
            raise ValueError(
                f"Issue must be fixed/verify_pending to verify (current: {issue.status.value})"
            )

        if data.verified:
            issue.status = IssueStatus.VERIFIED
            issue.timeline.append(TimelineEvent(
                at=now, event="verified", by=by, note=data.note or "User confirmed fix",
            ))
            # auto-close after verified
            issue.status = IssueStatus.CLOSED
            issue.timeline.append(TimelineEvent(
                at=now, event="status:closed", by="system",
                note="Auto-closed after verification",
            ))
        else:
            issue.status = IssueStatus.IN_PROGRESS
            issue.timeline.append(TimelineEvent(
                at=now, event="verify_failed", by=by,
                note=data.note or "Still broken — reopened",
            ))

        return self.store.update(issue)

    def export_markdown(self) -> str:
        issues = self.store.list()
        md = export_summary_markdown(issues)
        out = self.store.base / "ISSUES_SUMMARY.md"
        out.write_text(md, encoding="utf-8")
        return md

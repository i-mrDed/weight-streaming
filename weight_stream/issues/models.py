"""Issue data models and status lifecycle."""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class IssueStatus(str, Enum):
    OPEN = "open"
    TRIAGED = "triaged"
    IN_PROGRESS = "in_progress"
    FIXED = "fixed"
    VERIFY_PENDING = "verify_pending"
    VERIFIED = "verified"
    WONTFIX = "wontfix"
    DUPLICATE = "duplicate"
    CLOSED = "closed"


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# Allowed transitions (from -> set of to)
TRANSITIONS: Dict[IssueStatus, set[IssueStatus]] = {
    IssueStatus.OPEN: {IssueStatus.TRIAGED, IssueStatus.IN_PROGRESS, IssueStatus.DUPLICATE, IssueStatus.WONTFIX},
    IssueStatus.TRIAGED: {IssueStatus.IN_PROGRESS, IssueStatus.DUPLICATE, IssueStatus.WONTFIX},
    IssueStatus.IN_PROGRESS: {IssueStatus.FIXED, IssueStatus.WONTFIX, IssueStatus.DUPLICATE},
    IssueStatus.FIXED: {IssueStatus.VERIFY_PENDING, IssueStatus.IN_PROGRESS},
    IssueStatus.VERIFY_PENDING: {IssueStatus.VERIFIED, IssueStatus.IN_PROGRESS},
    IssueStatus.VERIFIED: {IssueStatus.CLOSED},
    IssueStatus.WONTFIX: {IssueStatus.CLOSED},
    IssueStatus.DUPLICATE: {IssueStatus.CLOSED},
    IssueStatus.CLOSED: set(),  # terminal
}


class TimelineEvent(BaseModel):
    at: str
    event: str
    by: str = "system"
    note: Optional[str] = None


class IssueCreate(BaseModel):
    title: str = Field(..., min_length=5, max_length=200)
    description: str = Field(..., min_length=10, max_length=10000)
    steps_to_reproduce: List[str] = Field(default_factory=list)
    expected: str = ""
    actual: str = ""
    severity: Severity = Severity.MEDIUM
    created_by: str = "local-user"
    context: Dict[str, Any] = Field(default_factory=dict)


class IssueUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    severity: Optional[Severity] = None
    status: Optional[IssueStatus] = None
    root_cause: Optional[str] = None
    fix_summary: Optional[str] = None
    commit: Optional[str] = None
    test_notes: Optional[str] = None
    verify_steps: Optional[str] = None
    note: Optional[str] = None
    updated_by: str = "maintainer"


class IssueVerify(BaseModel):
    verified: bool = True
    note: str = ""
    verified_by: str = "local-user"


class Issue(BaseModel):
    id: str
    title: str
    description: str
    steps_to_reproduce: List[str] = Field(default_factory=list)
    expected: str = ""
    actual: str = ""
    severity: Severity = Severity.MEDIUM
    status: IssueStatus = IssueStatus.OPEN
    created_at: str
    updated_at: str
    created_by: str = "local-user"
    context: Dict[str, Any] = Field(default_factory=dict)
    root_cause: Optional[str] = None
    fix_summary: Optional[str] = None
    commit: Optional[str] = None
    test_notes: Optional[str] = None
    verify_steps: Optional[str] = None
    timeline: List[TimelineEvent] = Field(default_factory=list)

    def can_transition_to(self, new_status: IssueStatus) -> bool:
        return new_status in TRANSITIONS.get(self.status, set())

    def require_fixed_fields(self) -> Optional[str]:
        """Return error message if fixed status requirements not met."""
        if not self.root_cause:
            return "root_cause is required before marking fixed"
        if not self.fix_summary:
            return "fix_summary is required before marking fixed"
        if not self.verify_steps:
            return "verify_steps is required before marking fixed"
        return None

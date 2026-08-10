"""Persistent issue storage (JSON per issue + JSONL event log)."""
from __future__ import annotations

import json
import os
import re
import threading
from pathlib import Path
from typing import List, Optional

from .models import Issue, IssueStatus, TimelineEvent, _utcnow


class IssueStore:
    """Thread-safe file-backed issue store."""

    def __init__(self, base_dir: str | Path | None = None):
        if base_dir is None:
            base_dir = os.environ.get("WS_ISSUES_DIR", "data/issues")
        self.base = Path(base_dir)
        self.base.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._counter_file = self.base / "counter.txt"
        self._jsonl = self.base / "issues.jsonl"

    ID_PREFIX = "Report-ISSUE-"

    # Only safe filename characters. Blocks path traversal (W5): "..", path
    # separators (/ and Windows \\) and encoded variants never reach disk.
    _ID_RE = re.compile(r"^[A-Za-z0-9_.-]+$")

    @classmethod
    def _valid_id(cls, issue_id: str) -> bool:
        return bool(issue_id) and bool(cls._ID_RE.fullmatch(issue_id))

    def _next_id(self) -> str:
        with self._lock:
            n = 1
            if self._counter_file.exists():
                try:
                    n = int(self._counter_file.read_text(encoding="utf-8").strip() or "0") + 1
                except ValueError:
                    n = self._scan_max_id() + 1
            else:
                n = self._scan_max_id() + 1
            self._counter_file.write_text(str(n), encoding="utf-8")
            return f"{self.ID_PREFIX}{n:03d}"

    def _scan_max_id(self) -> int:
        max_n = 0
        for p in self.base.glob("Report-ISSUE-*.json"):
            m = re.match(r"Report-ISSUE-(\d+)\.json", p.name)
            if m:
                max_n = max(max_n, int(m.group(1)))
        return max_n

    def _path(self, issue_id: str) -> Path:
        if not self._valid_id(issue_id):
            raise ValueError(f"invalid issue id: {issue_id!r}")
        return self.base / f"{issue_id}.json"

    def _md_path(self, issue_id: str) -> Path:
        if not self._valid_id(issue_id):
            raise ValueError(f"invalid issue id: {issue_id!r}")
        return self.base / f"{issue_id}.md"

    def create(self, issue: Issue) -> Issue:
        with self._lock:
            path = self._path(issue.id)
            if path.exists():
                raise ValueError(f"Issue {issue.id} already exists")
            self._write(issue)
            self._append_event({"event": "created", "id": issue.id, "at": issue.created_at})
            return issue

    def get(self, issue_id: str) -> Optional[Issue]:
        if not self._valid_id(issue_id):
            return None
        path = self._path(issue_id)
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return Issue.model_validate(data)

    def list(
        self,
        status: Optional[IssueStatus] = None,
        severity: Optional[str] = None,
    ) -> List[Issue]:
        issues: List[Issue] = []
        with self._lock:
            for path in sorted(self.base.glob("Report-ISSUE-*.json")):
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    issue = Issue.model_validate(data)
                    if status and issue.status != status:
                        continue
                    if severity and issue.severity.value != severity:
                        continue
                    issues.append(issue)
                except Exception:
                    continue
        # newest first
        issues.sort(key=lambda i: i.created_at, reverse=True)
        return issues

    def update(self, issue: Issue) -> Issue:
        with self._lock:
            if not self._path(issue.id).exists():
                raise ValueError(f"Issue {issue.id} not found")
            issue.updated_at = _utcnow()
            self._write(issue)
            self._append_event({
                "event": "updated",
                "id": issue.id,
                "status": issue.status.value,
                "at": issue.updated_at,
            })
            return issue

    def _write(self, issue: Issue) -> None:
        path = self._path(issue.id)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(
            issue.model_dump_json(indent=2),
            encoding="utf-8",
        )
        tmp.replace(path)
        # human-readable mirror
        self._md_path(issue.id).write_text(self._to_markdown(issue), encoding="utf-8")

    def _append_event(self, event: dict) -> None:
        with open(self._jsonl, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")

    def new_issue_id(self) -> str:
        return self._next_id()

    @staticmethod
    def _to_markdown(issue: Issue) -> str:
        lines = [
            f"# {issue.id}: {issue.title}",
            "",
            f"- **Status:** {issue.status.value}",
            f"- **Severity:** {issue.severity.value}",
            f"- **Created:** {issue.created_at} by {issue.created_by}",
            f"- **Updated:** {issue.updated_at}",
            "",
            "## Description",
            issue.description,
            "",
        ]
        if issue.steps_to_reproduce:
            lines.append("## Steps to Reproduce")
            for i, s in enumerate(issue.steps_to_reproduce, 1):
                lines.append(f"{i}. {s}")
            lines.append("")
        if issue.expected:
            lines += ["## Expected", issue.expected, ""]
        if issue.actual:
            lines += ["## Actual", issue.actual, ""]
        if issue.context:
            lines += ["## Context", "```json", json.dumps(issue.context, indent=2, ensure_ascii=False), "```", ""]
        if issue.root_cause:
            lines += ["## Root Cause", issue.root_cause, ""]
        if issue.fix_summary:
            lines += ["## Fix", issue.fix_summary, ""]
        if issue.commit:
            lines += [f"**Commit:** `{issue.commit}`", ""]
        if issue.verify_steps:
            lines += ["## Verify Steps", issue.verify_steps, ""]
        if issue.timeline:
            lines.append("## Timeline")
            for ev in issue.timeline:
                note = f" — {ev.note}" if ev.note else ""
                lines.append(f"- `{ev.at}` **{ev.event}** by {ev.by}{note}")
            lines.append("")
        return "\n".join(lines)

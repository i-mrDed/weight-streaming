"""Export issues to markdown summary."""
from __future__ import annotations

from collections import defaultdict
from typing import List

from .models import Issue, IssueStatus


def export_summary_markdown(issues: List[Issue]) -> str:
    by_status = defaultdict(list)
    for issue in issues:
        by_status[issue.status.value].append(issue)

    lines = [
        "# Issues Summary",
        "",
        f"> Auto-generated - {len(issues)} total issues",
        "",
        "## By Status",
        "",
        "| Status | Count |",
        "|--------|------:|",
    ]
    for st in IssueStatus:
        n = len(by_status.get(st.value, []))
        if n:
            lines.append(f"| {st.value} | {n} |")
    lines += ["", "---", ""]

    # Active first
    active = [s for s in IssueStatus if s not in (IssueStatus.CLOSED, IssueStatus.VERIFIED)]
    lines.append("## Active")
    lines.append("")
    any_active = False
    for st in active:
        for issue in by_status.get(st.value, []):
            any_active = True
            lines.append(
                f"- **{issue.id}** [{issue.severity.value}] `{issue.status.value}` - {issue.title}"
            )
    if not any_active:
        lines.append("_No active issues._")
    lines += ["", "## Closed / Verified", ""]
    closed = by_status.get("closed", []) + by_status.get("verified", [])
    if not closed:
        lines.append("_None yet._")
    else:
        for issue in closed:
            lines.append(f"- **{issue.id}** `{issue.status.value}` - {issue.title}")
    lines.append("")
    return "\n".join(lines)

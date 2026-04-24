"""
api/issue_extractor.py - Extract structured issues from review text.

The review pipeline returns free-form text. This module parses it into
structured Issue dicts that the frontend can render with severity badges,
file references, and line numbers.

Strategy:
  1. Regex patterns to find CRITICAL/MAJOR/MINOR markers in the review text
  2. Infer a file hint from files_changed when the review omits a file path
  3. Always return a valid list (never crash the pipeline)
"""
from __future__ import annotations

import re
from typing import TypedDict


class Issue(TypedDict):
    severity: str      # "critical" | "warning" | "info"
    file: str
    line: int
    message: str


_SEVERITY_MAP = {
    "critical": "critical",
    "high": "critical",
    "major": "warning",
    "medium": "warning",
    "minor": "info",
    "low": "info",
    "info": "info",
    "note": "info",
}

_ISSUE_RE = re.compile(
    r"[-*]\s*\[?(?P<sev>critical|high|major|medium|minor|low|info|note)\]?"
    r"[:\s]+"
    r"(?:(?P<file>[^\s:]+\.(?:py|ts|tsx|js|jsx|go|rs|java|cs|rb|php|swift|sh|c|cpp|h))"
    r":(?P<line>\d+)\s+)?"
    r"(?P<msg>.+)",
    re.IGNORECASE,
)

_SIMPLE_RE = re.compile(
    r"[-*]\s*\[?(?P<sev>critical|high|major|medium|minor|low|info|note)\]?[:\s]+(?P<msg>[^\n]+)",
    re.IGNORECASE,
)


def extract_issues(review_text: str, files_changed: list[str] | None = None) -> list[Issue]:
    """
    Parse a free-form review text and return a list of structured Issue dicts.
    Returns an empty list if no issues are found.
    """
    issues: list[Issue] = []
    seen: set[str] = set()

    for raw_line in review_text.split("\n"):
        line = raw_line.strip()
        if not line:
            continue

        match = _ISSUE_RE.search(line) or _SIMPLE_RE.search(line)
        if not match:
            continue

        severity = _SEVERITY_MAP.get(match.group("sev").lower(), "info")
        file_ref = match.groupdict().get("file") or ""

        try:
            line_num = int(match.groupdict().get("line") or 0)
        except (TypeError, ValueError):
            line_num = 0

        if not file_ref and files_changed:
            file_ref = files_changed[0]

        message = re.sub(r"[)\]]+$", "", match.group("msg").strip()).strip()
        dedupe_key = f"{severity}:{file_ref}:{line_num}:{message[:60]}"
        if dedupe_key in seen or not message:
            continue
        seen.add(dedupe_key)

        issues.append(
            Issue(
                severity=severity,
                file=file_ref,
                line=line_num,
                message=message,
            )
        )

    return issues

"""
Parse free-form review text into structured issues.

The extractor prefers explicit issue structure from the review text, then falls
back to file and type inference without fabricating file ownership.
"""
from __future__ import annotations

import re
from typing import TypedDict

from backend.utils.issues import classify_issue_type, resolve_issue_file


class Issue(TypedDict):
    severity: str      # "critical" | "warning" | "info"
    issue_type: str
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
    r"(?:\s*\[(?P<issue_type>[a-z0-9_ -]+)\])?"
    r"[:\s]+"
    r"(?:(?:\[)?(?P<file>[^\s:\]]+\.(?:py|ts|tsx|js|jsx|go|rs|java|cs|rb|php|swift|sh|c|cpp|h))"
    r":(?P<line>\d+)(?:\])?\s+)?"
    r"(?P<msg>.+)",
    re.IGNORECASE,
)

_SIMPLE_RE = re.compile(
    r"[-*]\s*\[?(?P<sev>critical|high|major|medium|minor|low|info|note)\]?[:\s]+(?P<msg>[^\n]+)",
    re.IGNORECASE,
)
_LINE_HINT_RE = re.compile(r"\b(?:line\s+|lines\s+|L)(?P<line>\d{1,6})\b")


def _extract_line_number(match: re.Match[str], message: str) -> int:
    try:
        explicit_line = int(match.groupdict().get("line") or 0)
    except (TypeError, ValueError):
        explicit_line = 0
    if explicit_line > 0:
        return explicit_line

    line_match = _LINE_HINT_RE.search(message)
    if line_match is None:
        return 0
    try:
        return int(line_match.group("line"))
    except (TypeError, ValueError):
        return 0


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
        explicit_type = match.groupdict().get("issue_type")
        file_ref = match.groupdict().get("file") or ""

        message = re.sub(r"[)\]]+$", "", match.group("msg").strip()).strip()
        line_num = _extract_line_number(match, message)
        issue_type = classify_issue_type(message, explicit_type)
        resolved_file = resolve_issue_file(
            explicit_file=file_ref,
            message=message,
            files_changed=files_changed,
        )
        dedupe_key = f"{severity}:{issue_type}:{resolved_file}:{line_num}:{message[:60]}"
        if dedupe_key in seen or not message:
            continue
        seen.add(dedupe_key)

        issues.append(
            Issue(
                severity=severity,
                issue_type=issue_type,
                file=resolved_file,
                line=line_num,
                message=message,
            )
        )

    return issues

"""
api/issue_extractor.py — Extract structured issues from review text.

The LLM produces free-form review text.  This module parses it into
structured Issue dicts that the frontend can render with severity badges,
file references, and line numbers.

Strategy:
  1. Regex patterns to find CRITICAL/MAJOR/MINOR markers in the review text
  2. Fall back to a lightweight LLM call if structured extraction fails
  3. Always return a valid list (never crash the pipeline)
"""
import re
from typing import TypedDict


class Issue(TypedDict):
    severity: str      # "critical" | "warning" | "info"
    file: str
    line: int
    message: str


# Map review severity words to frontend severity values
_SEVERITY_MAP = {
    "critical": "critical",
    "high":     "critical",
    "major":    "warning",
    "medium":   "warning",
    "minor":    "info",
    "low":      "info",
    "info":     "info",
    "note":     "info",
}

# Pattern: - [CRITICAL] src/auth.py:42 Some message
# or:      - CRITICAL: src/auth.py:42 Some message
_ISSUE_RE = re.compile(
    r"[-*]\s*\[?(?P<sev>critical|high|major|medium|minor|low|info|note)\]?"
    r"[:\s]+"
    r"(?:(?P<file>[^\s:]+\.(?:py|ts|tsx|js|jsx|go|rs|java|cs|rb|php|swift|sh|c|cpp|h))"
    r":(?P<line>\d+)\s+)?"
    r"(?P<msg>.+)",
    re.IGNORECASE,
)

# Simpler fallback: just [SEVERITY] message
_SIMPLE_RE = re.compile(
    r"[-*]\s*\[?(?P<sev>critical|high|major|medium|minor|low|info|note)\]?[:\s]+(?P<msg>[^\n]+)",
    re.IGNORECASE,
)


def extract_issues(review_text: str, files_changed: list[str] | None = None) -> list[Issue]:
    """
    Parse a free-form review text and return a list of structured Issue dicts.
    Returns an empty list if no issues are found (not an error condition).
    """
    issues: list[Issue] = []
    seen: set[str] = set()

    for line in review_text.split("\n"):
        line = line.strip()
        if not line:
            continue

        m = _ISSUE_RE.search(line) or _SIMPLE_RE.search(line)
        if not m:
            continue

        sev_raw = m.group("sev").lower()
        severity = _SEVERITY_MAP.get(sev_raw, "info")

        # Extract file and line from match (may be None)
        file_ref = m.groupdict().get("file") or ""
        try:
            line_num = int(m.groupdict().get("line") or 0)
        except (ValueError, TypeError):
            line_num = 0

        # If no file ref found, try to infer from files_changed
        if not file_ref and files_changed:
            # Use the first changed file as a hint
            file_ref = files_changed[0] if files_changed else ""

        msg = m.group("msg").strip()
        # Clean up trailing punctuation/brackets
        msg = re.sub(r"[)\]]+$", "", msg).strip()

        # Deduplicate
        dedup_key = f"{severity}:{file_ref}:{line_num}:{msg[:60]}"
        if dedup_key in seen or not msg:
            continue
        seen.add(dedup_key)

        issues.append(Issue(
            severity=severity,
            file=file_ref,
            line=line_num,
            message=msg,
        ))

    return issues
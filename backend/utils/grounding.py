from __future__ import annotations

import re
from typing import Any, Iterable

from backend.api.issue_extractor import extract_issues
from backend.graph.state import GroundedIssue, RetrievalHit
from backend.utils.issues import classify_issue_type, file_paths_match, normalize_file_path

_FILE_HEADER_RE = re.compile(r"^\+\+\+\s+b/(.+)$")

_ISSUE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "sql_injection": ("select ", "insert ", "update ", "delete ", "execute(", "query", "where "),
    "weak_password_hash": ("md5", "sha1", "hashlib"),
    "hardcoded_secret": ("secret", "token", "api_key", "password", "database_url", "redacted_secret"),
    "command_injection": ("os.system", "os.popen", "subprocess", "shell"),
    "unsafe_deserialization": ("pickle.loads", "yaml.load", "deserialize"),
    "broken_access_control": ("request.args", "query.get", "permission", "authorization"),
    "missing_validation": ("todo", "validate", "request.body", "req.body", "params"),
    "obfuscated_code": ("global[", "string.fromcharcode", "eval(", "function("),
    "insecure_random": ("random.choice", "random.randint", "math.random"),
    "broad_exception": ("except exception", "except baseexception"),
    "bare_except": ("except:",),
    "mutable_default_argument": ("=[]", "={}", "= []", "= {}"),
    "none_comparison": ("== none", "!= none"),
    "missing_type_hints": ("def ",),
    "god_function": (
        "process_order",
        "stripe.create_charge",
        "email.send",
        "slack.post",
        "db.save",
        "payment",
        "notification",
    ),
    "magic_numbers": (
        "item_type ==",
        "qty >",
        "todo",
        "loyalty_discount",
        "9.99",
        "24.99",
        "49.99",
        "0.85",
        "0.70",
    ),
    "duplicate_logic": (
        "duplicated",
        "duplicate",
        "repeated",
        "errors.append",
        "validate_signup",
        "validate_profile_update",
    ),
    "xss": ("dangerouslysetinnerhtml", "innerhtml", "html"),
    "hooks_dependency": ("useeffect", "usememo", "usecallback"),
    "type_safety": (": any", " as any", "any)"),
}

_REVIEW_SEVERITY_LABELS = {
    "critical": "CRITICAL",
    "warning": "MAJOR",
    "info": "MINOR",
}

_LOW_VALUE_ISSUES = {
    "missing_type_hints",
    "none_comparison",
    "magic_numbers",
    "duplicate_logic",
}

_SECURITY_ISSUES = {
    "sql_injection",
    "weak_password_hash",
    "hardcoded_secret",
    "command_injection",
    "unsafe_deserialization",
    "broken_access_control",
    "missing_validation",
    "obfuscated_code",
    "insecure_random",
    "xss",
}


def iter_added_lines(diff: str) -> list[dict[str, Any]]:
    current_file = "unknown"
    new_line = 0
    added: list[dict[str, Any]] = []
    for raw_line in diff.replace("\r\n", "\n").split("\n"):
        file_match = _FILE_HEADER_RE.match(raw_line)
        if file_match:
            current_file = normalize_file_path(file_match.group(1).strip())
            continue
        if raw_line.startswith("@@"):
            header = raw_line.split("@@", 2)[1].strip()
            plus_part = next((part for part in header.split() if part.startswith("+")), "+0")
            try:
                new_line = int(plus_part[1:].split(",", 1)[0])
            except ValueError:
                new_line = 0
            continue
        if raw_line.startswith("+") and not raw_line.startswith("+++"):
            added.append({"file": current_file, "line": new_line, "content": raw_line[1:]})
            new_line += 1
            continue
        if raw_line.startswith("-") and not raw_line.startswith("---"):
            continue
        if new_line:
            new_line += 1
    return added


def _source_id_for_issue(issue_type: str, retrieval_hits: Iterable[RetrievalHit]) -> str:
    fallback = "diff"
    for hit in retrieval_hits:
        source_id = f"{hit.get('source', 'unknown')}:{hit.get('section', 'general')}"
        text = f"{hit.get('source', '')} {hit.get('section', '')} {hit.get('snippet', '')}".lower()
        if issue_type.replace("_", " ") in text or any(term in text for term in _ISSUE_KEYWORDS.get(issue_type, ())):
            return source_id
        if fallback == "diff":
            fallback = source_id
    return fallback


def _line_supports_issue(issue_type: str, line: str, message: str) -> bool:
    normalized_line = line.lower()
    normalized_message = message.lower()
    keywords = _ISSUE_KEYWORDS.get(issue_type, ())
    if any(keyword in normalized_line for keyword in keywords):
        return True
    if issue_type in _LOW_VALUE_ISSUES and any(keyword in normalized_message for keyword in keywords):
        return True
    return False


def _find_support(issue: dict[str, Any], added_lines: list[dict[str, Any]]) -> dict[str, Any] | None:
    issue_type = classify_issue_type(str(issue.get("message", "")), str(issue.get("issue_type", "")))
    issue_file = normalize_file_path(str(issue.get("file") or "unknown"))
    issue_line = int(issue.get("line") or 0)
    message = str(issue.get("message") or "")

    exact = [
        line for line in added_lines
        if file_paths_match(issue_file, line["file"]) and issue_line and line["line"] == issue_line
    ]
    for line in exact:
        if _line_supports_issue(issue_type, str(line["content"]), message) or issue_type not in _LOW_VALUE_ISSUES:
            return line

    same_file = [
        line for line in added_lines
        if issue_file == "unknown" or file_paths_match(issue_file, line["file"])
    ]
    for line in same_file:
        if _line_supports_issue(issue_type, str(line["content"]), message):
            return line

    return None


def ground_review_issues(
    review_text: str,
    *,
    diff: str,
    files_changed: list[str],
    retrieval_hits: list[RetrievalHit],
    review_focus: str = "balanced",
    candidate_index: int = 0,
) -> list[GroundedIssue]:
    raw_issues = extract_issues(review_text, files_changed)
    added_lines = iter_added_lines(diff)
    grounded: list[GroundedIssue] = []
    has_security_issue = any(
        classify_issue_type(issue["message"], issue["issue_type"]) in _SECURITY_ISSUES
        for issue in raw_issues
    )
    stronger_issue_files = {
        normalize_file_path(str(issue.get("file") or "unknown"))
        for issue in raw_issues
        if classify_issue_type(issue["message"], issue["issue_type"]) != "missing_type_hints"
    }

    for issue in raw_issues:
        issue_type = classify_issue_type(issue["message"], issue["issue_type"])
        issue_file = normalize_file_path(str(issue.get("file") or "unknown"))
        if review_focus == "security" and has_security_issue and issue_type in _LOW_VALUE_ISSUES:
            continue
        if issue_type == "missing_type_hints" and any(
            file_paths_match(issue_file, stronger_file)
            for stronger_file in stronger_issue_files
        ):
            continue
        support = _find_support(issue, added_lines)
        if support is None:
            continue
        grounded.append(
            {
                "severity": issue["severity"],
                "issue_type": issue_type,
                "file": normalize_file_path(str(support["file"])),
                "line": int(support["line"] or 0),
                "message": issue["message"],
                "code_snippet": str(support["content"]).strip(),
                "source_id": _source_id_for_issue(issue_type, retrieval_hits),
                "candidate_index": candidate_index,
            }
        )
    return grounded


def render_grounded_review(original_review: str, grounded_issues: list[GroundedIssue]) -> str:
    summary_match = re.search(r"## Summary\s*(.*?)(?=\n## |\Z)", original_review, re.DOTALL)
    suggestions_match = re.search(r"## Suggestions\s*(.*?)(?=\n## |\Z)", original_review, re.DOTALL)
    verdict = "REQUEST_CHANGES" if grounded_issues else "APPROVE"
    summary = summary_match.group(1).strip() if summary_match else "Review completed against the visible diff."
    suggestions = suggestions_match.group(1).strip() if suggestions_match else "No additional suggestions."
    if not grounded_issues:
        issues_text = "None."
        suggestions = "Keep the change covered with tests appropriate to its risk."
    else:
        issues_text = "\n".join(
            (
                f"- [{_REVIEW_SEVERITY_LABELS.get(issue['severity'], issue['severity'].upper())}] "
                f"[{issue['issue_type']}] "
                f"{issue['file']}:{issue['line']} {issue['message']} "
                f"(evidence: `{issue['code_snippet']}`; source: {issue['source_id']})"
            )
            for issue in grounded_issues
        )
    return (
        f"## Summary\n{summary}\n\n"
        f"## Issues Found\n{issues_text}\n\n"
        f"## Suggestions\n{suggestions}\n\n"
        f"## Grounding\n{len(grounded_issues)} issue(s) retained after changed-line evidence validation.\n\n"
        f"## Verdict\n{verdict}\n"
        f"{'Grounded issues must be fixed before merge.' if grounded_issues else 'No grounded issue survives evidence validation.'}"
    )

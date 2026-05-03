from __future__ import annotations

import time

from backend.graph.state import PRCriticState
from backend.observability.logger import log_end, log_start


def _plan(diff: str, files: list[str], language: str) -> dict:
    text = f"{diff}\n{' '.join(files)}".lower()
    risk_terms: list[str] = []
    expected_issue_types: list[str] = []
    focus = "balanced"

    security_markers = {
        "sql_injection": ("select ", "query", "execute(", "where ", "db."),
        "weak_password_hash": ("md5", "sha1", "hashlib"),
        "hardcoded_secret": ("secret", "token", "api_key", "password"),
        "xss": ("dangerouslysetinnerhtml", "innerhtml"),
        "command_injection": ("os.system", "os.popen", "subprocess"),
        "missing_validation": ("todo", "validation", "request.body", "req.body"),
    }
    for issue_type, markers in security_markers.items():
        if any(marker in text for marker in markers):
            expected_issue_types.append(issue_type)
            risk_terms.extend(marker.strip() for marker in markers[:2])

    if expected_issue_types:
        focus = "security"
    elif language in {"TypeScript", "JavaScript"} or any(file.endswith((".ts", ".tsx", ".js", ".jsx")) for file in files):
        focus = "frontend" if any(file.endswith((".tsx", ".jsx")) for file in files) else "correctness"
    elif language == "Python":
        focus = "correctness"
    if any(segment in text for segment in ("service", "controller", "processor", "manager")) and not expected_issue_types:
        focus = "maintainability"

    return {
        "focus": focus,
        "rationale": (
            "Security-sensitive patterns were detected in the changed lines."
            if focus == "security"
            else f"Primary review focus selected from language={language} and changed paths."
        ),
        "risk_terms": sorted(set(risk_terms))[:8],
        "expected_issue_types": sorted(set(expected_issue_types)),
    }


def planner_agent(state: PRCriticState) -> dict:
    started_at = time.perf_counter()
    trace = list(state.get("trace", []))
    metadata = state.get("pr_metadata", {})
    files = list(metadata.get("files_changed", []))
    language = str(metadata.get("language", "Unknown"))
    start_event = log_start(
        "planner_agent",
        {
            "language": language,
            "files_changed": files,
            "safety_flags": state.get("safety_flags", {}),
        },
    )
    plan = _plan(state.get("pr_diff", ""), files, language)
    end_event = log_end(
        "planner_agent",
        {
            "focus": plan["focus"],
            "expected_issue_types": plan["expected_issue_types"],
            "risk_terms": plan["risk_terms"],
        },
        (time.perf_counter() - started_at) * 1000,
    )
    return {
        "review_plan": plan,
        "rate_limited": bool(state.get("rate_limited", False)),
        "large_pr_mode": bool(state.get("large_pr_mode", False)),
        "repo_signals": state.get("repo_signals"),
        "request_cache_key": str(state.get("request_cache_key", "")),
        "branch_skipped_reason": str(state.get("branch_skipped_reason", "")),
        "safety_flags": state.get("safety_flags", {}),
        "agent_messages": list(state.get("agent_messages", [])) + [
            {
                "agent": "planner_agent",
                "artifact_type": "ReviewPlan",
                "summary": plan,
            }
        ],
        "trace": trace + [start_event, end_event],
    }

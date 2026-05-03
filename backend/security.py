from __future__ import annotations

import re
from typing import Any

from backend.config import settings

_GITHUB_PR_RE = re.compile(r"^https://github\.com/[^/\s]+/[^/\s]+/pull/\d+/?$")
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_OPAQUE_SECRET_RE = re.compile(
    r"(?i)\b("
    r"sk-[A-Za-z0-9_-]{8,}|"
    r"ghp_[A-Za-z0-9_]{8,}|"
    r"github_pat_[A-Za-z0-9_]+"
    r")"
)
_NAMED_SECRET_RE = re.compile(
    r"(?i)\b(?P<key>"
    r"(?:[A-Za-z0-9_]*api[_-]?key|[A-Za-z0-9_]*secret|[A-Za-z0-9_]*token|password|database_url)"
    r"\s*[:=]\s*)"
    r"(?P<quote>['\"])[^'\"]{4,}(?P=quote)"
)
_PROMPT_INJECTION_PATTERNS = (
    "ignore previous instructions",
    "ignore all previous",
    "you are now",
    "do not review",
    "always approve",
    "return approve",
    "jailbreak",
)


def mask_pii(text: str) -> str:
    masked = _EMAIL_RE.sub("[REDACTED_EMAIL]", str(text or ""))
    masked = _NAMED_SECRET_RE.sub(
        lambda m: f"{m.group('key')}{m.group('quote')}[REDACTED_SECRET]{m.group('quote')}",
        masked,
    )
    return _OPAQUE_SECRET_RE.sub("[REDACTED_SECRET]", masked)


def detect_prompt_injection(text: str) -> dict[str, Any]:
    normalized = str(text or "").lower()
    matches = [pattern for pattern in _PROMPT_INJECTION_PATTERNS if pattern in normalized]
    return {
        "prompt_injection_detected": bool(matches),
        "prompt_injection_patterns": matches[:8],
    }


def validate_review_source(value: str) -> str:
    source = str(value or "").strip()
    if not source:
        raise ValueError("Review source is required.")
    if len(source) > settings.max_review_input_chars:
        raise ValueError(f"Review source exceeds {settings.max_review_input_chars} characters.")
    if source.startswith(("mock://", "eval://")):
        return source
    if source.startswith("https://github.com/"):
        if not _GITHUB_PR_RE.match(source):
            raise ValueError("Only GitHub pull request URLs are allowed.")
        return source
    if source.startswith(("http://", "https://")):
        raise ValueError("Only github.com pull request URLs are allowed.")
    if "diff --git " in source or source.startswith("--- ") or source.startswith("+++ "):
        return source
    raise ValueError("Provide a GitHub PR URL, mock/eval URL, or unified diff text.")


def require_api_key(headers: dict[str, str]) -> bool:
    expected = settings.api_key
    if not expected:
        return True
    supplied = headers.get("x-api-key", "")
    auth = headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        supplied = auth.split(" ", 1)[1].strip()
    return supplied == expected

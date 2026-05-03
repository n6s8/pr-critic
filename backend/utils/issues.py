from __future__ import annotations

import os
import re
from typing import Iterable


_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "be",
    "before",
    "by",
    "for",
    "from",
    "if",
    "in",
    "into",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "this",
    "to",
    "use",
    "with",
}

_ISSUE_TYPE_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("sql_injection", ("sql injection", "parameterized quer", "parameterised quer", "interpolated sql")),
    ("weak_password_hash", ("md5", "password hash", "bcrypt", "argon2", "pbkdf2")),
    ("hardcoded_secret", ("hardcoded secret", "hardcoded credential", "hardcoded api key", "secret", "token")),
    ("command_injection", ("command injection", "os.system", "os.popen", "shell execution", "subprocess")),
    ("unsafe_deserialization", ("pickle", "deserialization", "deserialisation", "untrusted object")),
    ("broken_access_control", ("access control", "authorization", "authorisation", "permission", "current user")),
    ("missing_validation", ("missing validation", "proper validation", "input validation", "unvalidated", "validate input")),
    ("obfuscated_code", ("obfuscated", "encoded payload", "dynamic require", "global require", "mutates globals")),
    ("insecure_random", ("insecure random", "predictable", "secrets module", "cryptographically secure")),
    ("broad_exception", ("broad exception", "baseexception", "except exception", "silently passes", "swallows exceptions")),
    ("bare_except", ("bare except", "catch specific exception", "swallows unexpected exceptions")),
    ("mutable_default_argument", ("mutable default", "default argument", "shared across calls")),
    ("none_comparison", ("is none", "is not none", "compare against none", "none comparison")),
    ("missing_type_hints", ("type annotation", "type hint", "annotate", "public function is missing type")),
    ("god_function", ("single responsibility", "too many things", "too many responsibilities", "split the flow")),
    ("magic_numbers", ("magic number", "named constant", "dead code", "sentinel values")),
    ("duplicate_logic", ("duplicate logic", "duplicated", "repeated checks", "dry")),
    ("xss", ("xss", "dangerouslysetinnerhtml", "unsanitized html", "unsanitised html")),
    ("hooks_dependency", ("useeffect dependency", "hooks dependency", "stale closure")),
    ("type_safety", ("type safety", "any type", "broad type", "null safety")),
]


def normalize_text(text: str) -> str:
    return _NON_ALNUM_RE.sub(" ", str(text or "").lower()).strip()


def tokenize_text(text: str) -> set[str]:
    return {
        token
        for token in normalize_text(text).split()
        if len(token) > 2 and token not in _STOPWORDS
    }


def description_similarity(left: str, right: str) -> float:
    left_tokens = tokenize_text(left)
    right_tokens = tokenize_text(right)
    if not left_tokens or not right_tokens:
        return 0.0
    overlap = len(left_tokens & right_tokens)
    return overlap / max(len(left_tokens), len(right_tokens))


def normalize_file_path(path: str | None) -> str:
    if not path:
        return "unknown"
    normalized = str(path).replace("\\", "/").strip().strip("\"'")
    if normalized.startswith(("a/", "b/")):
        normalized = normalized[2:]
    return normalized or "unknown"


def file_paths_match(left: str | None, right: str | None) -> bool:
    normalized_left = normalize_file_path(left)
    normalized_right = normalize_file_path(right)
    if "unknown" in {normalized_left, normalized_right}:
        return False
    if normalized_left == normalized_right:
        return True
    return normalized_left.endswith(f"/{normalized_right}") or normalized_right.endswith(f"/{normalized_left}")


def classify_issue_type(text: str, explicit_type: str | None = None) -> str:
    if explicit_type:
        normalized = normalize_text(explicit_type).replace(" ", "_")
        if normalized:
            return normalized

    normalized_text = normalize_text(text)
    if not normalized_text:
        return "unknown"

    for issue_type, patterns in _ISSUE_TYPE_RULES:
        if any(pattern in normalized_text for pattern in patterns):
            return issue_type
    return "unknown"


def _candidate_file_mentions(message: str, files_changed: Iterable[str]) -> list[str]:
    normalized_message = normalize_text(message)
    matches: list[str] = []
    for file_path in files_changed:
        normalized_file = normalize_file_path(file_path)
        if normalized_file == "unknown":
            continue
        basename = os.path.basename(normalized_file)
        candidates = {
            normalize_text(normalized_file),
            normalize_text(basename),
            normalize_text(basename.rsplit(".", 1)[0]),
        }
        if any(candidate and candidate in normalized_message for candidate in candidates):
            matches.append(normalized_file)
    return matches


def resolve_issue_file(
    *,
    explicit_file: str | None,
    message: str,
    files_changed: Iterable[str] | None = None,
) -> str:
    normalized_explicit = normalize_file_path(explicit_file)
    if normalized_explicit != "unknown":
        return normalized_explicit

    if not files_changed:
        return "unknown"

    matches = _candidate_file_mentions(message, files_changed)
    if len(matches) == 1:
        return matches[0]

    return "unknown"

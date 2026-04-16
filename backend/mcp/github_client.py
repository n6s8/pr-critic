"""Real GitHub PR data fetcher with retry, timeout, and cache support."""
from __future__ import annotations

import re
import time
from dataclasses import dataclass

import httpx

from backend.config import settings
from backend.observability.logger import record, log_structured
from backend.utils.cache import TTLCache, build_cache_key
from backend.utils.resilience import is_retryable_github_error, retry_call


_GITHUB_URL_RE = re.compile(
    r"https?://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/pull/(?P<number>\d+)/?"
)


@dataclass
class GHPRRef:
    owner: str
    repo: str
    number: int


def parse_github_url(url: str) -> "GHPRRef | None":
    match = _GITHUB_URL_RE.match(url.strip())
    if not match:
        return None
    return GHPRRef(
        owner=match.group("owner"),
        repo=match.group("repo"),
        number=int(match.group("number")),
    )


def is_github_url(url: str) -> bool:
    return parse_github_url(url) is not None


_EXT_TO_LANGUAGE: dict[str, str] = {
    ".py": "Python", ".pyi": "Python",
    ".ts": "TypeScript", ".tsx": "TypeScript",
    ".js": "JavaScript", ".jsx": "JavaScript", ".mjs": "JavaScript", ".cjs": "JavaScript",
    ".go": "Go",
    ".rs": "Rust",
    ".java": "Java",
    ".kt": "Kotlin",
    ".c": "C", ".cpp": "C++", ".cc": "C++", ".h": "C/C++", ".hpp": "C++",
    ".cs": "C#",
    ".rb": "Ruby",
    ".php": "PHP",
    ".swift": "Swift",
    ".sh": "Shell", ".bash": "Shell",
}

LANGUAGE_RAG_TERMS: dict[str, str] = {
    "Python": "Python code review PEP8 style security OWASP exception handling",
    "TypeScript": "TypeScript JavaScript ESLint type safety React hooks security best practices",
    "JavaScript": "JavaScript ESLint code review security async promises best practices",
    "Go": "Go Golang error handling interfaces concurrency best practices",
    "Rust": "Rust memory safety ownership borrowing error handling",
    "Java": "Java code review SOLID principles security OWASP best practices",
    "Kotlin": "Kotlin Android coroutines null safety best practices",
    "C#": "C# .NET LINQ async await security best practices",
    "Ruby": "Ruby Rails code review security best practices",
    "PHP": "PHP security OWASP injection XSS best practices",
}


def detect_language(filenames: list[str]) -> str:
    """Detect primary language from changed file extensions."""
    from collections import Counter

    counts: Counter[str] = Counter()
    for filename in filenames:
        if "." not in filename:
            continue
        ext = "." + filename.rsplit(".", 1)[-1].lower()
        language = _EXT_TO_LANGUAGE.get(ext)
        if language:
            counts[language] += 1
    return counts.most_common(1)[0][0] if counts else "Unknown"


_API_BASE = "https://api.github.com"
_TIMEOUT = httpx.Timeout(settings.github_timeout_seconds)
_PR_CACHE: TTLCache["PRData"] = TTLCache("pr_fetch", settings.caches.pr_ttl_seconds, max_size=64)


def _headers(token: str | None = None) -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "pr-critic/1.0",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    else:
        log_structured(
            "WARNING",
            "github_api_no_token",
            message="GitHub API request without token - unauthenticated requests have lower rate limits",
        )
    return headers


def _request_json(url: str, headers: dict[str, str], params: dict | None = None) -> dict | list[dict]:
    def _operation():
        with httpx.Client(timeout=_TIMEOUT) as client:
            response = client.get(url, headers=headers, params=params)
            response.raise_for_status()
            return response.json()

    return retry_call(
        _operation,
        service="github",
        operation_name="json_get",
        should_retry=is_retryable_github_error,
        context={"url": url},
    )


def _request_text(url: str, headers: dict[str, str], *, follow_redirects: bool = False) -> str:
    def _operation():
        with httpx.Client(timeout=_TIMEOUT, follow_redirects=follow_redirects) as client:
            response = client.get(url, headers=headers)
            response.raise_for_status()
            return response.text

    return retry_call(
        _operation,
        service="github",
        operation_name="text_get",
        should_retry=is_retryable_github_error,
        context={"url": url},
    )


def _fetch_pr_meta(ref: GHPRRef, token: str | None) -> dict:
    url = f"{_API_BASE}/repos/{ref.owner}/{ref.repo}/pulls/{ref.number}"
    data = _request_json(url, _headers(token))
    return data if isinstance(data, dict) else {}


def _fetch_diff(ref: GHPRRef, token: str | None) -> str:
    """Fetch raw unified diff via API first, then .diff fallback."""
    url = f"{_API_BASE}/repos/{ref.owner}/{ref.repo}/pulls/{ref.number}"
    headers = _headers(token)
    headers["Accept"] = "application/vnd.github.v3.diff"
    diff = _request_text(url, headers)
    if diff.strip().startswith("diff --git"):
        return diff

    fallback = f"https://github.com/{ref.owner}/{ref.repo}/pull/{ref.number}.diff"
    fallback_headers = {"User-Agent": "pr-critic/1.0"}
    if token:
        fallback_headers["Authorization"] = f"Bearer {token}"
    return _request_text(fallback, fallback_headers, follow_redirects=True)


def _fetch_files(ref: GHPRRef, token: str | None) -> list[dict]:
    files: list[dict] = []
    for page in range(1, 4):
        url = f"{_API_BASE}/repos/{ref.owner}/{ref.repo}/pulls/{ref.number}/files"
        batch = _request_json(url, _headers(token), params={"per_page": 100, "page": page})
        if not isinstance(batch, list) or not batch:
            break
        files.extend(batch)
        if len(batch) < 100:
            break
    return files


from backend.mcp.github_mock import PRData  # noqa: E402

MAX_DIFF_CHARS = 8_000


def get_real_pr_data(pr_url: str, token: str | None = None) -> PRData:
    """
    Full fetch pipeline: URL -> meta -> files -> language -> diff.

    Raises:
        ValueError: URL is not a valid GitHub PR URL.
        httpx.HTTPStatusError: GitHub API returned an error (including 403 rate limit).
    """
    ref = parse_github_url(pr_url)
    if ref is None:
        raise ValueError(f"Not a GitHub PR URL: {pr_url!r}")

    token_key = build_cache_key(token or "anonymous")
    cache_key = build_cache_key(pr_url, token_key)

    def _load() -> PRData:
        started_at = time.perf_counter()
        
        try:
            meta = _fetch_pr_meta(ref, token)
            files = _fetch_files(ref, token)
            file_names = [item["filename"] for item in files if "filename" in item]
            language = detect_language(file_names)
            diff = _fetch_diff(ref, token)
        except httpx.HTTPStatusError as exc:
            # Handle GitHub rate limit (403) with clear error message
            if exc.response and exc.response.status_code == 403:
                remaining = exc.response.headers.get("x-ratelimit-remaining", "0")
                reset_time = exc.response.headers.get("x-ratelimit-reset", "unknown")
                log_structured(
                    "ERROR",
                    "github_rate_limit_exceeded",
                    status_code=403,
                    url=str(exc.request.url) if exc.request else "unknown",
                    remaining=remaining,
                    reset_time=reset_time,
                    has_token=bool(token),
                )
                raise ValueError(
                    f"GitHub API rate limit exceeded (403). "
                    f"Remaining requests: {remaining}. "
                    f"Please ensure GITHUB_TOKEN is set for higher rate limits."
                ) from exc
            # Re-raise other HTTP errors
            raise

        if len(diff) > MAX_DIFF_CHARS:
            omitted = len(diff) - MAX_DIFF_CHARS
            diff = (
                diff[:MAX_DIFF_CHARS]
                + f"\n\n... [diff truncated - {omitted} chars omitted to fit context window] ..."
            )

        elapsed_ms = (time.perf_counter() - started_at) * 1000
        record(
            "github_client",
            "fetch_complete",
            {
                "owner": ref.owner,
                "repo": ref.repo,
                "pr_number": ref.number,
                "files_changed": len(file_names),
                "language": language,
                "diff_length": len(diff),
                "elapsed_ms": round(elapsed_ms, 1),
            },
        )

        return PRData(
            url=pr_url,
            title=meta.get("title", ""),
            author=meta.get("user", {}).get("login", "unknown"),
            base_branch=meta.get("base", {}).get("ref", "main"),
            head_branch=meta.get("head", {}).get("ref", "feature"),
            files_changed=file_names,
            language=language,
            diff=diff,
        )

    pr_data, _ = _PR_CACHE.get_or_compute(cache_key, _load)
    return pr_data

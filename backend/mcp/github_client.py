"""
mcp/github_client.py — Real GitHub PR data fetcher.

Parses GitHub PR URLs and fetches real diff + metadata via the
GitHub REST API.  Falls back gracefully when no token is set
(public repos only, lower rate limit).

Set GITHUB_TOKEN in .env to enable private repos and higher rate limits.
"""
import re
import time
from dataclasses import dataclass

import httpx

from backend.observability.logger import record


# ── URL parsing ───────────────────────────────────────────────────────────────

_GITHUB_URL_RE = re.compile(
    r"https?://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/pull/(?P<number>\d+)"
)


@dataclass
class GHPRRef:
    owner: str
    repo: str
    number: int


def parse_github_url(url: str) -> "GHPRRef | None":
    m = _GITHUB_URL_RE.match(url.strip())
    if not m:
        return None
    return GHPRRef(owner=m.group("owner"), repo=m.group("repo"), number=int(m.group("number")))


def is_github_url(url: str) -> bool:
    return parse_github_url(url) is not None


# ── Language detection ────────────────────────────────────────────────────────

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

# Per-language RAG query terms that retrieve the most relevant corpus chunks
LANGUAGE_RAG_TERMS: dict[str, str] = {
    "Python":     "Python code review PEP8 style security OWASP exception handling",
    "TypeScript": "TypeScript JavaScript ESLint type safety React hooks security best practices",
    "JavaScript": "JavaScript ESLint code review security async promises best practices",
    "Go":         "Go Golang error handling interfaces concurrency best practices",
    "Rust":       "Rust memory safety ownership borrowing error handling",
    "Java":       "Java code review SOLID principles security OWASP best practices",
    "Kotlin":     "Kotlin Android coroutines null safety best practices",
    "C#":         "C# .NET LINQ async await security best practices",
    "Ruby":       "Ruby Rails code review security best practices",
    "PHP":        "PHP security OWASP injection XSS best practices",
}


def detect_language(filenames: list[str]) -> str:
    """Detect primary language from changed file extensions (frequency vote)."""
    from collections import Counter
    counts: Counter[str] = Counter()
    for fname in filenames:
        if "." in fname:
            ext = "." + fname.rsplit(".", 1)[-1].lower()
            lang = _EXT_TO_LANGUAGE.get(ext)
            if lang:
                counts[lang] += 1
    return counts.most_common(1)[0][0] if counts else "Unknown"


# ── GitHub REST API helpers ───────────────────────────────────────────────────

_API_BASE = "https://api.github.com"
_TIMEOUT  = httpx.Timeout(30.0)


def _headers(token: "str | None" = None) -> dict[str, str]:
    h = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "pr-critic/1.0",
    }
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def _fetch_pr_meta(ref: GHPRRef, token: "str | None") -> dict:
    url = f"{_API_BASE}/repos/{ref.owner}/{ref.repo}/pulls/{ref.number}"
    with httpx.Client(timeout=_TIMEOUT) as c:
        r = c.get(url, headers=_headers(token))
        r.raise_for_status()
        return r.json()


def _fetch_diff(ref: GHPRRef, token: "str | None") -> str:
    """Fetch raw unified diff via the diff media type, with .diff URL fallback."""
    url = f"{_API_BASE}/repos/{ref.owner}/{ref.repo}/pulls/{ref.number}"
    h = _headers(token)
    h["Accept"] = "application/vnd.github.v3.diff"
    with httpx.Client(timeout=_TIMEOUT) as c:
        r = c.get(url, headers=h)
        r.raise_for_status()
        diff = r.text
    if diff.strip().startswith("diff --git"):
        return diff
    # Fallback: public .diff URL
    fallback = f"https://github.com/{ref.owner}/{ref.repo}/pull/{ref.number}.diff"
    fh: dict[str, str] = {"User-Agent": "pr-critic/1.0"}
    if token:
        fh["Authorization"] = f"Bearer {token}"
    with httpx.Client(timeout=_TIMEOUT, follow_redirects=True) as c:
        r2 = c.get(fallback, headers=fh)
        r2.raise_for_status()
        return r2.text


def _fetch_files(ref: GHPRRef, token: "str | None") -> list[dict]:
    """Paginate through changed files (up to 300)."""
    files: list[dict] = []
    for page in range(1, 4):
        url = f"{_API_BASE}/repos/{ref.owner}/{ref.repo}/pulls/{ref.number}/files"
        with httpx.Client(timeout=_TIMEOUT) as c:
            r = c.get(url, headers=_headers(token), params={"per_page": 100, "page": page})
            r.raise_for_status()
            batch = r.json()
        if not batch:
            break
        files.extend(batch)
        if len(batch) < 100:
            break
    return files


# ── Public entry point ────────────────────────────────────────────────────────

# Import here to avoid circular — PRData is defined in github_mock.py
from backend.mcp.github_mock import PRData  # noqa: E402

MAX_DIFF_CHARS = 8_000   # ~2k tokens — enough for most PRs without hitting limits


def get_real_pr_data(pr_url: str, token: "str | None" = None) -> PRData:
    """
    Full fetch pipeline: URL → meta → files → language → diff.
    Returns PRData with the same interface as mock data so no other
    agent needs to change.

    Raises:
        ValueError: URL is not a valid GitHub PR URL.
        httpx.HTTPStatusError: GitHub API returned an error (404, 403, etc.).
    """
    ref = parse_github_url(pr_url)
    if ref is None:
        raise ValueError(f"Not a GitHub PR URL: {pr_url!r}")

    t0 = time.perf_counter()

    meta   = _fetch_pr_meta(ref, token)
    files  = _fetch_files(ref, token)
    names  = [f["filename"] for f in files]
    lang   = detect_language(names)
    diff   = _fetch_diff(ref, token)

    # Truncate to avoid LLM token overflow
    if len(diff) > MAX_DIFF_CHARS:
        omitted = len(diff) - MAX_DIFF_CHARS
        diff = (
            diff[:MAX_DIFF_CHARS]
            + f"\n\n... [diff truncated — {omitted} chars omitted to fit context window] ..."
        )

    elapsed = (time.perf_counter() - t0) * 1000
    record("github_client", "fetch_complete", {
        "owner": ref.owner, "repo": ref.repo, "pr_number": ref.number,
        "files_changed": len(names), "language": lang,
        "diff_length": len(diff), "elapsed_ms": round(elapsed, 1),
    })

    return PRData(
        url=pr_url,
        title=meta.get("title", ""),
        author=meta.get("user", {}).get("login", "unknown"),
        base_branch=meta.get("base", {}).get("ref", "main"),
        head_branch=meta.get("head", {}).get("ref", "feature"),
        files_changed=names,
        language=lang,
        diff=diff,
    )
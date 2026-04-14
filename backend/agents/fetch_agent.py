"""
agents/fetch_agent.py — Fetch Agent.

Routes:
  mock://  → built-in mock data
  github.com PR URL → real GitHub API via github_client
  anything else → raw diff fallback

Sets pr_metadata.language via detect_language() when language is Unknown.
"""
import time
from backend.graph.state import PRCriticState
from backend.mcp.github_mock import get_pr_data
from backend.observability.logger import log_start, log_end, log_error


def fetch_agent(state: PRCriticState) -> dict:
    t0 = time.perf_counter()
    pr_url = state["pr_url"]
    log_start("fetch_agent", {"pr_url": pr_url})
    trace = list(state.get("trace", []))

    try:
        pr = get_pr_data(pr_url)

        language = pr.language
        if language == "Unknown" and pr.files_changed:
            try:
                from backend.mcp.github_client import detect_language
                language = detect_language(pr.files_changed)
            except ImportError:
                pass

        metadata = {
            "title": pr.title,
            "author": pr.author,
            "base_branch": pr.base_branch,
            "head_branch": pr.head_branch,
            "files_changed": pr.files_changed,
            "language": language,
            "pr_url": pr_url,
        }

        if pr.diff.strip().startswith("# ERROR:"):
            trace.append(log_error("fetch_agent", f"Failed to fetch PR data for {pr_url}"))

        ev = log_end("fetch_agent", {
            "title": pr.title,
            "files_changed": pr.files_changed,
            "language": language,
            "diff_length": len(pr.diff),
            "source": "github" if "github.com" in pr_url else "mock",
        }, (time.perf_counter() - t0) * 1000)

        return {
            "pr_diff": pr.diff,
            "pr_metadata": metadata,
            "trace": trace + [ev],
        }

    except Exception as exc:
        ev = log_error("fetch_agent", str(exc))
        return {
            "pr_diff": "",
            "pr_metadata": {"language": "Unknown", "title": "Fetch failed", "error": str(exc)},
            "trace": trace + [ev],
        }

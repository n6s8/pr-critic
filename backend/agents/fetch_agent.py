"""
Fetch Agent — retrieves PR diff and metadata.
Currently uses mock data; swap get_pr_data() for real GitHub MCP calls.
"""
import time
from backend.graph.state import PRCriticState
from backend.mcp.github_mock import get_pr_data
from backend.observability.logger import log_start, log_end, log_error


def fetch_agent(state: PRCriticState) -> dict:
    t0 = time.perf_counter()
    pr_url = state["pr_url"]
    log_start("fetch_agent", {"pr_url": pr_url})

    try:
        pr = get_pr_data(pr_url)
        metadata = {
            "title": pr.title,
            "author": pr.author,
            "base_branch": pr.base_branch,
            "head_branch": pr.head_branch,
            "files_changed": pr.files_changed,
            "language": pr.language,
        }
        ev = log_end("fetch_agent", {
            "files_changed": pr.files_changed,
            "diff_length": len(pr.diff),
        }, (time.perf_counter() - t0) * 1000)

        return {
            "pr_diff": pr.diff,
            "pr_metadata": metadata,
            "trace": state.get("trace", []) + [ev],
        }

    except Exception as exc:
        ev = log_error("fetch_agent", str(exc))
        return {
            "pr_diff": "",
            "pr_metadata": {},
            "trace": state.get("trace", []) + [ev],
        }
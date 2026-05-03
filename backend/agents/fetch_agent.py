"""
Fetch PR metadata and diffs through the MCP client boundary.

Routes behind MCP:
  mock:// and eval:// sources -> built-in local data
  github.com PR URL -> GitHub provider behind the MCP server
  unified diff text -> raw diff provider

Sets pr_metadata.language via file detection when the provider reports Unknown.
"""
import time

from backend.graph.state import FetchAgentInput, FetchAgentOutput
from backend.mcp.client import github_mcp_client
from backend.mcp.github_client import parse_github_url
from backend.observability.logger import log_start, log_end, log_error, log_structured
from backend.security import detect_prompt_injection, mask_pii
from backend.services.repo_signals import collect_repo_signals
from backend.utils.cache import build_cache_key

_LARGE_PR_THRESHOLD = 50_000


def _build_request_cache_key(pr_url: str, diff: str) -> str:
    ref = parse_github_url(pr_url)
    if ref is not None:
        return build_cache_key(diff, f"{ref.owner}/{ref.repo}", ref.number)
    return build_cache_key(diff, pr_url, "n/a")


def fetch_agent(state: FetchAgentInput) -> FetchAgentOutput:
    t0 = time.perf_counter()
    pr_url = state["pr_url"]
    trace = list(state.get("trace", []))
    safe_source_preview = mask_pii(pr_url)
    if len(safe_source_preview) > 240:
        safe_source_preview = f"{safe_source_preview[:237]}..."
    start_event = log_start("fetch_agent", {"pr_url": safe_source_preview})

    try:
        pr, mcp_records = github_mcp_client.get_pr_data_sync(pr_url)
        diff = mask_pii(pr.diff)
        safety_flags = detect_prompt_injection(diff)

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
        diff_length = len(diff)
        large_pr_mode = diff_length > _LARGE_PR_THRESHOLD
        request_cache_key = _build_request_cache_key(pr_url, diff)
        repo_signals = collect_repo_signals(
            pr_url,
            pr.files_changed,
            request_cache_key=request_cache_key,
        )

        if large_pr_mode:
            log_structured(
                "INFO",
                "large_pr_mode_enabled",
                agent="fetch_agent",
                pr_url=pr_url,
                diff_length=diff_length,
                large_pr_mode=True,
            )

        ev = log_end("fetch_agent", {
            "title": pr.title,
            "files_changed": pr.files_changed,
            "language": language,
            "diff_length": diff_length,
            "large_pr_mode": large_pr_mode,
            "repo_signal_checkout": repo_signals["checkout_status"],
            "repo_signal_lint": repo_signals["lint_status"],
            "repo_signal_issue_count": repo_signals["lint_issue_count"],
            "mcp_tools_used": [record.tool for record in mcp_records],
            "mcp_transport": mcp_records[0].transport if mcp_records else "unknown",
            "prompt_injection_detected": safety_flags["prompt_injection_detected"],
            "source": "github" if "github.com" in pr_url else ("evaluation" if pr_url.startswith("eval://") else "mock"),
        }, (time.perf_counter() - t0) * 1000)

        return {
            "pr_diff": diff,
            "pr_metadata": metadata,
            "rate_limited": bool(state.get("rate_limited", False)),
            "large_pr_mode": large_pr_mode,
            "repo_signals": repo_signals,
            "request_cache_key": request_cache_key,
            "branch_skipped_reason": "large_pr_mode" if large_pr_mode else str(state.get("branch_skipped_reason", "")),
            "safety_flags": safety_flags,
            "agent_messages": list(state.get("agent_messages", [])) + [
                {
                    "agent": "fetch_agent",
                    "artifact_type": "FetchArtifact",
                    "summary": {
                        "files_changed": pr.files_changed,
                        "language": language,
                        "diff_length": diff_length,
                        "mcp_tools_used": [record.tool for record in mcp_records],
                    },
                }
            ],
            "trace": trace + [start_event, ev],
        }

    except Exception as exc:
        log_error("fetch_agent", str(exc))
        raise

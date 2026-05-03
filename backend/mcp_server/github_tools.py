"""MCP server exposing GitHub pull-request tools for PR Critic.

The concrete GitHub REST calls live behind this server boundary. Agents call
the MCP client wrapper instead of importing REST helpers directly.
"""
from __future__ import annotations

import json
from typing import Any

from backend.mcp.github_mock import get_pr_data
from backend.mcp.models import PullRequestDiff, PullRequestMetadata

try:  # The dependency is declared in pyproject; tests can still run without it.
    from mcp.server.fastmcp import FastMCP
except Exception:  # pragma: no cover - exercised only when SDK is absent.
    FastMCP = None  # type: ignore[assignment]


mcp = FastMCP("pr-critic-github") if FastMCP is not None else None


def get_pull_request_impl(pr_url: str) -> dict[str, Any]:
    pr = get_pr_data(pr_url)
    return PullRequestMetadata(
        url=pr.url,
        title=pr.title,
        author=pr.author,
        base_branch=pr.base_branch,
        head_branch=pr.head_branch,
        files_changed=pr.files_changed,
        language=pr.language,
    ).to_dict()


def get_pull_request_diff_impl(pr_url: str) -> dict[str, Any]:
    pr = get_pr_data(pr_url)
    return PullRequestDiff(url=pr.url, diff=pr.diff).to_dict()


if mcp is not None:

    @mcp.tool()
    def get_pull_request(pr_url: str) -> dict[str, Any]:
        """Return normalized pull-request metadata for a GitHub/mock/eval source."""
        return get_pull_request_impl(pr_url)

    @mcp.tool()
    def get_pull_request_diff(pr_url: str) -> dict[str, Any]:
        """Return a raw unified diff for a GitHub/mock/eval source."""
        return get_pull_request_diff_impl(pr_url)

else:

    def get_pull_request(pr_url: str) -> dict[str, Any]:
        return get_pull_request_impl(pr_url)

    def get_pull_request_diff(pr_url: str) -> dict[str, Any]:
        return get_pull_request_diff_impl(pr_url)


def main() -> None:
    if mcp is None:
        raise RuntimeError("The 'mcp' package is required to run the GitHub MCP server.")
    mcp.run()


if __name__ == "__main__":
    main()

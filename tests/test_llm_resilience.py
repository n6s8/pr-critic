from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

import httpx
import pytest

ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, ROOT)
os.environ.setdefault("GROQ_API_KEY", "test_key")

from backend.agents.critic_agent import critic_agent
from backend.agents.review_agent import review_agent
from backend.api.main import app
from backend.errors import LLMRateLimitError
from backend.graph.state import build_initial_state
from backend.utils.diff import chunk_diff_for_review
from backend.utils.resilience import invoke_llm


def _http_429(retry_after: str | None = None) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    headers = {"Retry-After": retry_after} if retry_after is not None else {}
    response = httpx.Response(429, headers=headers, request=request)
    return httpx.HTTPStatusError("rate limit exceeded", request=request, response=response)


def test_invoke_llm_retries_429_and_respects_retry_after():
    llm = SimpleNamespace(invoke=Mock(side_effect=[_http_429("3"), _http_429("3"), _http_429("3")]))

    with patch("backend.utils.resilience.time.sleep") as mock_sleep:
        with pytest.raises(LLMRateLimitError) as exc_info:
            invoke_llm(llm, ["hello"], agent="review_agent")

    assert exc_info.value.retry_after_seconds == 3.0
    assert mock_sleep.call_args_list == [call(3.0), call(3.0)]


def test_review_agent_returns_rate_limit_fallback_candidate():
    state = build_initial_state("mock://pr/security-issue")
    state.update(
        {
            "pr_diff": "diff --git a/auth.py b/auth.py\n@@ -0,0 +1 @@\n+query = f'SELECT * FROM users WHERE id={user_id}'",
            "pr_metadata": {
                "title": "Security PR",
                "author": "bot",
                "files_changed": ["auth.py"],
                "language": "Python",
                "head_branch": "feat/security",
                "base_branch": "main",
            },
            "retrieved_context": "Use parameterized queries.",
            "retrieval_sources": ["owasp"],
            "retrieval_hits": [],
        }
    )

    with patch(
        "backend.agents.review_agent.invoke_llm",
        side_effect=LLMRateLimitError(retry_after_seconds=7),
    ):
        result = review_agent(state)

    assert result["candidates"][0]["strategy"] == "fallback_rate_limited"
    assert result["candidates"][0]["review"] == "LLM unavailable due to rate limit"
    assert result["rate_limited"] is True
    assert result["branch_skipped_reason"] == "rate_limited"
    assert result["trace"][-1]["data"]["fallback_used"] is True
    assert result["trace"][-1]["data"]["retry_after_seconds"] == 7


def test_critic_skips_branch_for_rate_limit_fallback_candidate():
    state = build_initial_state("mock://pr/security-issue")
    state.update(
        {
            "pr_diff": "diff --git a/auth.py b/auth.py\n@@ -0,0 +1 @@\n+dangerous_change()",
            "candidates": [
                {
                    "id": "fallback-rate-limit-0",
                    "strategy": "fallback_rate_limited",
                    "review": "LLM unavailable due to rate limit",
                }
            ],
        }
    )

    with patch("backend.agents.critic_agent.invoke_llm") as mock_invoke:
        result = critic_agent(state)

    mock_invoke.assert_not_called()
    assert result["scores"][0]["score"] == 0.0
    assert result["branch_taken"] is False


def test_chunk_diff_for_review_prioritizes_important_files_under_budget():
    diff = (
        "diff --git a/README.md b/README.md\n--- a/README.md\n+++ b/README.md\n@@ -1 +1 @@\n-docs\n+docs update\n\n"
        "diff --git a/src/auth.py b/src/auth.py\n--- a/src/auth.py\n+++ b/src/auth.py\n@@ -1 +1 @@\n-query = build_query(user_id)\n+query = f\"SELECT * FROM users WHERE id={user_id}\"\n"
    )

    chunks = chunk_diff_for_review(diff, max_chars=200, max_chunks=1)

    assert len(chunks) == 1
    assert "src/auth.py" in chunks[0].included_files
    assert "README.md" not in chunks[0].included_files
    assert len(chunks[0].content.splitlines()) <= 200


def test_review_agent_uses_cache_for_repeat_request():
    state = build_initial_state("mock://pr/security-issue")
    state.update(
        {
            "pr_diff": "diff --git a/auth.py b/auth.py\n@@ -0,0 +1 @@\n+query = f'SELECT * FROM users WHERE id={user_id}'",
            "pr_metadata": {
                "title": "Security PR",
                "author": "bot",
                "files_changed": ["auth.py"],
                "language": "Python",
                "head_branch": "feat/security",
                "base_branch": "main",
            },
            "retrieved_context": "Use parameterized queries.",
            "retrieval_sources": ["owasp"],
            "retrieval_hits": [],
            "request_cache_key": "request-cache-key",
        }
    )

    with patch(
        "backend.agents.review_agent.invoke_llm",
        return_value=SimpleNamespace(
            content=(
                "## Summary\nRisky auth change.\n\n"
                "## Issues Found\n- [CRITICAL] [sql_injection] auth.py:1 SQL injection.\n\n"
                "## Suggestions\n- Parameterize.\n\n"
                "## Verdict\nREQUEST_CHANGES\nUnsafe."
            )
        ),
    ) as mock_invoke:
        first = review_agent(state)
        second = review_agent(state)

    assert mock_invoke.call_count == 1
    assert first["candidates"][0]["review"] == second["candidates"][0]["review"]
    assert second["trace"][-1]["data"]["cache_hit"] is True


def test_review_agent_uses_single_llm_call_for_filtered_packet():
    state = build_initial_state("mock://pr/security-issue")
    state.update(
        {
            "pr_diff": (
                "diff --git a/backend/auth.py b/backend/auth.py\n--- a/backend/auth.py\n+++ b/backend/auth.py\n@@ -0,0 +1,80 @@\n"
                + "\n".join(f"+auth_line_{index}" for index in range(80))
                + "\n\ndiff --git a/backend/db.py b/backend/db.py\n--- a/backend/db.py\n+++ b/backend/db.py\n@@ -0,0 +1,80 @@\n"
                + "\n".join(f"+db_line_{index}" for index in range(80))
            ),
            "pr_metadata": {
                "title": "Security PR",
                "author": "bot",
                "files_changed": ["backend/auth.py", "backend/db.py"],
                "language": "Python",
                "head_branch": "feat/security",
                "base_branch": "main",
            },
            "retrieved_context": "Use parameterized queries.\nValidate auth flows.",
            "retrieval_sources": ["owasp"],
            "retrieval_hits": [],
            "request_cache_key": "single-pass-cache-key",
        }
    )

    with patch(
        "backend.agents.review_agent.invoke_llm",
        return_value=SimpleNamespace(
            content=(
                "## Summary\nRisky backend change.\n\n"
                "## Issues Found\n- [CRITICAL] [sql_injection] backend/db.py:1 SQL injection.\n\n"
                "## Suggestions\n- Parameterize.\n\n"
                "## Verdict\nREQUEST_CHANGES\nUnsafe."
            )
        ),
    ) as mock_invoke:
        result = review_agent(state)

    assert mock_invoke.call_count == 1
    assert result["trace"][-1]["data"]["selected_chunks"] <= 3
    assert result["llm_input_tokens"] < 2000


def test_review_agent_uses_deterministic_large_pr_candidate_without_llm():
    state = build_initial_state("mock://pr/security-issue")
    state.update(
        {
            "pr_diff": (
                "diff --git a/backend/api.py b/backend/api.py\n"
                "--- a/backend/api.py\n+++ b/backend/api.py\n@@ -0,0 +1,120 @@\n"
                + "\n".join(f"+line_{index} = request.args.get('x')" for index in range(120))
            ),
            "pr_metadata": {
                "title": "Large change",
                "author": "bot",
                "files_changed": ["backend/api.py"],
                "language": "Python",
                "head_branch": "feat/large",
                "base_branch": "main",
            },
            "retrieved_context": "Validate request input.",
            "retrieval_sources": ["owasp"],
            "retrieval_hits": [],
            "large_pr_mode": True,
            "request_cache_key": "large-pr-cache-key",
        }
    )

    with patch("backend.agents.review_agent.invoke_llm") as mock_invoke:
        result = review_agent(state)

    mock_invoke.assert_not_called()
    assert result["candidates"][0]["strategy"] == "large_pr_partial"
    assert "Partial analysis only" in result["candidates"][0]["review"]
    assert result["branch_skipped_reason"] == "large_pr_mode"
    assert result["branch_budget_available"] is False


def test_review_endpoint_returns_503_with_rate_limit_message_when_no_candidates():
    async def fake_run(initial_state):
        return {
            **initial_state,
            "pr_diff": "diff --git a/app.py b/app.py\n@@ -0,0 +1 @@\n+print('x')",
            "pr_metadata": {
                "title": "Demo",
                "author": "bot",
                "base_branch": "main",
                "head_branch": "feat",
                "language": "Python",
                "files_changed": ["app.py"],
                "pr_url": initial_state["pr_url"],
            },
            "retrieval_hits": [],
            "candidates": [],
            "scores": [],
            "selected_index": None,
            "selector_reason": "No candidates were produced by the pipeline.",
            "branch_taken": False,
            "branch_improvement": None,
            "trace": [
                {
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "agent": "review_agent",
                    "event": "end",
                    "data": {"reason": "llm_rate_limited", "retry_after_seconds": 9},
                }
            ],
        }

    async def exercise():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.post("/review", json={"pr_url": "mock://pr/security-issue"})

    with patch("backend.api.main.run_review_pipeline_async", side_effect=fake_run):
        response = asyncio.run(exercise())

    assert response.status_code == 503
    assert response.headers["Retry-After"] == "9"
    payload = response.json()
    assert "rate limit" in payload["error"]["message"].lower()

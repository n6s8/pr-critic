"""
GitHub routing, language detection, retrieval, and API contract tests.
"""
from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime, timezone
from unittest.mock import patch

import httpx

ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, ROOT)
os.environ.setdefault("GROQ_API_KEY", "test_key")

from backend.graph.state import build_initial_state


class TestURLParsing:
    def test_valid_github_pr_url(self):
        from backend.mcp.github_client import parse_github_url

        ref = parse_github_url("https://github.com/torvalds/linux/pull/1234")
        assert ref is not None
        assert ref.owner == "torvalds"
        assert ref.repo == "linux"
        assert ref.number == 1234

    def test_is_github_url(self):
        from backend.mcp.github_client import is_github_url

        assert is_github_url("https://github.com/owner/repo/pull/1") is True
        assert is_github_url("mock://pr/test") is False


class TestLanguageDetection:
    def test_python_files(self):
        from backend.mcp.github_client import detect_language

        assert detect_language(["api/views.py", "models.py"]) == "Python"

    def test_typescript_files(self):
        from backend.mcp.github_client import detect_language

        assert detect_language(["src/auth.ts", "src/hooks/useAuth.tsx"]) == "TypeScript"

    def test_unknown_extensions(self):
        from backend.mcp.github_client import detect_language

        assert detect_language(["README.md", "LICENSE"]) == "Unknown"


class TestMockRouting:
    def test_known_mock_urls_return_mock_data(self):
        from backend.mcp.github_mock import MOCK_PRS, get_pr_data

        for url in MOCK_PRS:
            assert get_pr_data(url).url == url

    def test_evaluation_urls_return_real_scenario_diff(self):
        from backend.mcp.github_mock import get_pr_data

        pr = get_pr_data("eval://sec/sql-injection")
        assert "SELECT * FROM orders" in pr.diff
        assert pr.language == "Python"

    def test_github_fetch_error_returns_error_pr(self):
        from backend.mcp.github_mock import get_pr_data

        with patch("backend.mcp.github_client.get_real_pr_data", side_effect=Exception("404 Not Found")):
            pr = get_pr_data("https://github.com/owner/repo/pull/99999")
            assert pr.diff.startswith("# ERROR:")
            assert "404 Not Found" in pr.diff


class TestLanguageAwareRAG:
    def test_typescript_pr_gets_non_empty_sources(self):
        from backend.agents.rag_agent import _retrieve

        context, sources, hits, mode = _retrieve(
            "const [user, setUser] = useState(null)\nuseEffect(() => { fetch(url) }, [])",
            "TypeScript",
        )
        assert context.strip() != ""
        assert sources
        assert hits
        assert mode == "tfidf"

    def test_python_pr_mentions_security_guidance(self):
        from backend.agents.rag_agent import _retrieve

        context, sources, hits, mode = _retrieve(
            "hashlib.md5(password.encode()).hexdigest()",
            "Python",
        )
        assert context.strip() != ""
        assert sources
        assert hits
        assert "OWASP" in context or "password" in context.lower()


class TestBranchStrategies:
    def test_python_gets_python_idioms_strategy(self):
        from backend.agents.branch_agent import _strategies_for_language

        names = [strategy["name"] for strategy in _strategies_for_language("Python")]
        assert "python_idioms" in names
        assert "security_focus" in names

    def test_typescript_gets_typescript_strategy(self):
        from backend.agents.branch_agent import _strategies_for_language

        names = [strategy["name"] for strategy in _strategies_for_language("TypeScript")]
        assert "typescript_idioms" in names


class TestIssueExtractor:
    def test_extracts_structured_issues(self):
        from backend.api.issue_extractor import extract_issues

        review = """
## Issues Found
- [CRITICAL] src/auth.py:42 SQL injection via f-string
- [MAJOR] src/auth.py:43 Hardcoded secret
"""
        issues = extract_issues(review)
        assert len(issues) == 2
        assert issues[0]["severity"] == "critical"
        assert issues[1]["severity"] == "warning"

    def test_uses_file_hint_when_missing_file(self):
        from backend.api.issue_extractor import extract_issues

        issues = extract_issues("- [MINOR] Fix naming", files_changed=["utils.py"])
        assert issues[0]["file"] == "utils.py"


class TestReviewEndpointContract:
    def test_review_endpoint_returns_new_contract(self):
        from backend.api.main import app

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
                "retrieval_hits": [
                    {
                        "source": "pep8",
                        "section": "Type Annotations",
                        "snippet": "Annotate public function parameters and return types.",
                        "relevance": 0.8,
                    }
                ],
                "candidates": [
                    {
                        "id": "candidate-0",
                        "strategy": "initial",
                        "review": "## Issues Found\n- [MINOR] app.py:1 Missing type hints",
                    }
                ],
                "scores": [
                    {
                        "candidate_index": 0,
                        "strategy": "initial",
                        "score": 7.0,
                        "rationale": "Adequate",
                        "issues_identified": ["Missing type hints"],
                    }
                ],
                "selected_index": 0,
                "selector_reason": "Selected the only candidate returned by the pipeline.",
                "branch_taken": False,
                "branch_improvement": None,
                "trace": [
                    {
                        "ts": datetime.now(timezone.utc).isoformat(),
                        "agent": "fetch_agent",
                        "event": "end",
                        "data": {"language": "Python"},
                    }
                ],
            }

        async def exercise():
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                return await client.post("/review", json={"pr_url": "mock://pr/security-issue"})

        with patch("backend.api.main.run_review_pipeline_async", side_effect=fake_run):
            response = asyncio.run(exercise())

        payload = response.json()
        assert response.status_code == 200
        assert payload["pr_metadata"]["language"] == "Python"
        assert payload["selected_review"]["strategy"] == "initial"
        assert payload["retrieval"][0]["source"] == "pep8"
        assert payload["trace"][0]["status"] == "completed"


class TestErrorHandling:
    def test_fetch_agent_handles_error_diff_gracefully(self):
        from backend.agents.fetch_agent import fetch_agent

        state = {
            **build_initial_state("https://github.com/owner/repo/pull/1"),
        }
        with patch("backend.mcp.github_client.get_real_pr_data", side_effect=Exception("rate limit exceeded")):
            result = fetch_agent(state)
        assert "pr_diff" in result
        assert "pr_metadata" in result

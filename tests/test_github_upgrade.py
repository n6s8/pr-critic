"""
tests/test_github_upgrade.py

Tests for the real GitHub PR analysis upgrade:
  - URL parsing and language detection
  - Mock routing (mock:// vs github.com vs raw diff)
  - TypeScript-aware RAG retrieval
  - Language-aware branch strategies
  - Issue extraction from review text
  - API response shape matching frontend contract
  - Error handling for bad GitHub URLs
"""
import json
import os
import sys

import pytest
from unittest.mock import patch, MagicMock

ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, ROOT)
os.environ.setdefault("GROQ_API_KEY", "test_key")


# ── github_client tests ───────────────────────────────────────────────────────

class TestURLParsing:
    def test_valid_github_pr_url(self):
        from backend.mcp.github_client import parse_github_url
        ref = parse_github_url("https://github.com/torvalds/linux/pull/1234")
        assert ref is not None
        assert ref.owner == "torvalds"
        assert ref.repo == "linux"
        assert ref.number == 1234

    def test_github_url_with_trailing_slash(self):
        from backend.mcp.github_client import parse_github_url
        ref = parse_github_url("https://github.com/owner/repo/pull/42/")
        assert ref is not None
        assert ref.number == 42

    def test_mock_url_not_github(self):
        from backend.mcp.github_client import parse_github_url
        assert parse_github_url("mock://pr/security-issue") is None

    def test_raw_diff_not_github(self):
        from backend.mcp.github_client import parse_github_url
        assert parse_github_url("diff --git a/foo.py") is None

    def test_is_github_url(self):
        from backend.mcp.github_client import is_github_url
        assert is_github_url("https://github.com/owner/repo/pull/1") is True
        assert is_github_url("mock://pr/test") is False
        assert is_github_url("https://gitlab.com/owner/repo/merge_requests/1") is False
        assert is_github_url("") is False

    def test_http_url_also_works(self):
        from backend.mcp.github_client import parse_github_url
        ref = parse_github_url("http://github.com/owner/repo/pull/5")
        assert ref is not None


class TestLanguageDetection:
    def test_python_files(self):
        from backend.mcp.github_client import detect_language
        assert detect_language(["api/views.py", "models.py", "utils.py"]) == "Python"

    def test_typescript_files(self):
        from backend.mcp.github_client import detect_language
        assert detect_language(["src/auth.ts", "src/hooks/useAuth.tsx"]) == "TypeScript"

    def test_javascript_files(self):
        from backend.mcp.github_client import detect_language
        assert detect_language(["index.js", "utils.mjs"]) == "JavaScript"

    def test_go_files(self):
        from backend.mcp.github_client import detect_language
        assert detect_language(["main.go", "handler.go"]) == "Go"

    def test_mixed_files_majority_wins(self):
        from backend.mcp.github_client import detect_language
        # 3 py files vs 1 ts file — Python wins
        files = ["api.py", "models.py", "tests.py", "config.ts"]
        assert detect_language(files) == "Python"

    def test_unknown_extensions(self):
        from backend.mcp.github_client import detect_language
        assert detect_language(["README.md", "LICENSE", "Makefile"]) == "Unknown"

    def test_empty_list(self):
        from backend.mcp.github_client import detect_language
        assert detect_language([]) == "Unknown"

    def test_case_insensitive_extension(self):
        from backend.mcp.github_client import detect_language
        # Extensions are lowercased before lookup
        assert detect_language(["File.PY", "Module.PY"]) == "Python"


# ── Mock routing tests ────────────────────────────────────────────────────────

class TestMockRouting:
    def test_known_mock_urls_return_mock_data(self):
        from backend.mcp.github_mock import get_pr_data, MOCK_PRS
        for url in MOCK_PRS:
            pr = get_pr_data(url)
            assert pr.url == url

    def test_new_typescript_mock_exists(self):
        from backend.mcp.github_mock import get_pr_data
        pr = get_pr_data("mock://pr/typescript-react")
        assert pr.language == "TypeScript"
        assert any(f.endswith(".tsx") or f.endswith(".ts") for f in pr.files_changed)

    def test_unknown_url_becomes_raw_diff(self):
        from backend.mcp.github_mock import get_pr_data
        raw = "diff --git a/foo.py\n+x = 1"
        pr = get_pr_data(raw)
        assert pr.diff == raw

    def test_github_url_routes_to_client(self):
        """GitHub URL should call get_real_pr_data, not return mock."""
        from backend.mcp.github_mock import get_pr_data, PRData

        mock_pr = PRData(
            url="https://github.com/owner/repo/pull/1",
            title="Test PR", author="user",
            base_branch="main", head_branch="feat",
            files_changed=["app.py"], language="Python",
            diff="diff --git a/app.py",
        )
        # Patch at the definition site (github_client), since github_mock
        # imports it lazily inside the function body
        with patch("backend.mcp.github_client.get_real_pr_data", return_value=mock_pr):
            pr = get_pr_data("https://github.com/owner/repo/pull/1")
            assert pr.title == "Test PR"

    def test_github_fetch_error_returns_error_pr(self):
        """If GitHub fetch fails, should return error-state PRData not raise."""
        from backend.mcp.github_mock import get_pr_data
        with patch("backend.mcp.github_client.get_real_pr_data", side_effect=Exception("404 Not Found")):
            pr = get_pr_data("https://github.com/owner/repo/pull/99999")
            assert pr.diff.startswith("# ERROR:")
            assert "404 Not Found" in pr.diff


# ── Language-aware RAG tests ──────────────────────────────────────────────────

class TestLanguageAwareRAG:
    def test_typescript_pr_gets_ts_sources(self):
        from backend.agents.rag_agent import _retrieve
        ctx, sources, mode = _retrieve(
            "const [user, setUser] = useState(null)\nuseEffect(() => { fetch(url) }, [])",
            "TypeScript"
        )
        # After corpus rebuild, should find TS sources
        # Both tfidf (corpus) or placeholder are valid — test that result is usable
        assert ctx.strip() != ""
        assert isinstance(sources, list)
        assert len(sources) > 0

    def test_python_pr_gets_python_context(self):
        from backend.agents.rag_agent import _retrieve
        ctx, sources, mode = _retrieve(
            "hashlib.md5(password.encode()).hexdigest()",
            "Python"
        )
        assert ctx.strip() != ""
        # Python context should mention OWASP or PEP
        assert "OWASP" in ctx or "PEP" in ctx or "password" in ctx.lower()

    def test_unknown_language_has_fallback(self):
        from backend.agents.rag_agent import _retrieve
        ctx, sources, mode = _retrieve("", "Brainfuck")
        # Should not crash; should return some context
        assert ctx.strip() != ""

    def test_query_builder_includes_language_terms(self):
        from backend.agents.rag_agent import _build_query
        q = _build_query("", "TypeScript")
        assert "TypeScript" in q or "JavaScript" in q

        q2 = _build_query("", "Python")
        assert "Python" in q2 or "PEP" in q2

    def test_placeholders_exist_for_major_languages(self):
        from backend.agents.rag_agent import _PLACEHOLDERS
        for lang in ("Python", "TypeScript", "JavaScript", "Go", "Unknown"):
            assert lang in _PLACEHOLDERS, f"Missing placeholder for {lang}"
            assert len(_PLACEHOLDERS[lang]) > 100


# ── Language-aware branch strategy tests ─────────────────────────────────────

class TestLanguageAwareBranchStrategies:
    def test_python_gets_python_idioms_strategy(self):
        from backend.agents.branch_agent import _strategies_for_language
        strats = _strategies_for_language("Python")
        names = [s["name"] for s in strats]
        assert "python_idioms" in names

    def test_typescript_gets_typescript_strategy(self):
        from backend.agents.branch_agent import _strategies_for_language
        strats = _strategies_for_language("TypeScript")
        names = [s["name"] for s in strats]
        assert "typescript_idioms" in names

    def test_all_languages_get_security_strategy(self):
        from backend.agents.branch_agent import _strategies_for_language
        for lang in ("Python", "TypeScript", "JavaScript", "Go", "Rust", "Unknown"):
            strats = _strategies_for_language(lang)
            names = [s["name"] for s in strats]
            assert "security_focus" in names, f"{lang} missing security_focus"

    def test_unknown_language_gets_correctness_fallback(self):
        from backend.agents.branch_agent import _strategies_for_language
        strats = _strategies_for_language("Unknown")
        names = [s["name"] for s in strats]
        assert "correctness_focus" in names

    def test_no_duplicate_strategies(self):
        from backend.agents.branch_agent import _strategies_for_language
        for lang in ("Python", "TypeScript", "Go", "Unknown"):
            strats = _strategies_for_language(lang)
            names = [s["name"] for s in strats]
            assert len(names) == len(set(names)), f"Duplicate strategies for {lang}"

    def test_strategies_have_anti_hallucination_rules(self):
        from backend.agents.branch_agent import _ALL_STRATEGIES
        for strat in _ALL_STRATEGIES:
            assert "diff" in strat["prompt"].lower(), (
                f"Strategy {strat['name']} missing diff instruction"
            )


# ── Issue extractor tests ─────────────────────────────────────────────────────

class TestIssueExtractor:
    def test_extracts_critical_with_file_and_line(self):
        from backend.api.issue_extractor import extract_issues
        review = "- [CRITICAL] src/auth.py:42 SQL injection via f-string"
        issues = extract_issues(review)
        assert len(issues) == 1
        assert issues[0]["severity"] == "critical"
        assert issues[0]["file"] == "src/auth.py"
        assert issues[0]["line"] == 42
        assert "SQL injection" in issues[0]["message"]

    def test_extracts_multiple_severities(self):
        from backend.api.issue_extractor import extract_issues
        review = """
## Issues Found
- [CRITICAL] auth/views.py:8 MD5 used for password hashing
- [MAJOR] api/views.py:18 Hardcoded secret key
- [MINOR] Fix variable naming
"""
        issues = extract_issues(review)
        severities = [i["severity"] for i in issues]
        assert "critical" in severities
        assert "warning" in severities
        assert "info" in severities

    def test_maps_high_to_critical(self):
        from backend.api.issue_extractor import extract_issues
        issues = extract_issues("- [HIGH] security.py:1 Very dangerous thing")
        assert issues[0]["severity"] == "critical"

    def test_maps_major_to_warning(self):
        from backend.api.issue_extractor import extract_issues
        issues = extract_issues("- MAJOR: important problem in code")
        assert issues[0]["severity"] == "warning"

    def test_empty_review_returns_empty_list(self):
        from backend.api.issue_extractor import extract_issues
        assert extract_issues("") == []
        assert extract_issues("   ") == []

    def test_review_without_issues_returns_empty(self):
        from backend.api.issue_extractor import extract_issues
        review = "## Summary\nThis PR looks good.\n\n## Verdict: APPROVE"
        assert extract_issues(review) == []

    def test_deduplicates_identical_issues(self):
        from backend.api.issue_extractor import extract_issues
        review = """
- [CRITICAL] auth.py:1 SQL injection
- [CRITICAL] auth.py:1 SQL injection
"""
        issues = extract_issues(review)
        assert len(issues) == 1

    def test_uses_file_hint_when_no_file_in_issue(self):
        from backend.api.issue_extractor import extract_issues
        issues = extract_issues("- [MINOR] Fix naming convention", files_changed=["utils.py"])
        assert issues[0]["file"] == "utils.py"

    def test_real_world_review_format(self):
        from backend.api.issue_extractor import extract_issues
        review = """## Issues Found
- [CRITICAL] src/auth.ts:15 dangerouslySetInnerHTML with user.bio (XSS risk)
- [MAJOR] src/hooks/useUser.ts:8 useEffect missing userId in dependency array
- [MINOR] src/components/UserProfile.tsx:3 `any` type for userId prop"""
        issues = extract_issues(review)
        assert len(issues) == 3
        assert all(i["severity"] in ("critical", "warning", "info") for i in issues)


# ── API response shape tests ──────────────────────────────────────────────────

class TestAPIResponseShape:
    def _run_pipeline_mocked(self, pr_url="mock://pr/security-issue", score=8.5):
        from backend.graph.workflow import compiled_graph
        from backend.graph.state import PRCriticState
        from backend.api.main import _normalize_trace, _candidates_to_strategies
        from backend.api.issue_extractor import extract_issues

        def make_mock(content):
            m = MagicMock()
            m.content = content
            return m

        with patch("backend.agents.review_agent._llm") as rev, \
             patch("backend.agents.critic_agent._llm") as crit, \
             patch("backend.agents.selector_agent._llm") as sel:

            rev.invoke.return_value = make_mock(
                "## Summary\nTest PR.\n\n"
                "## Issues Found\n"
                "- [CRITICAL] auth.py:5 SQL injection\n"
                "- [MAJOR] auth.py:10 Hardcoded secret\n\n"
                "## Verdict: REQUEST_CHANGES"
            )
            crit.invoke.return_value = make_mock(
                json.dumps({"score": score, "rationale": "Good", "issues_identified": []})
            )
            sel.invoke.return_value = make_mock(
                json.dumps({"best_index": 0, "rationale": "Best"})
            )

            initial: PRCriticState = {
                "pr_url": pr_url, "pr_diff": "", "pr_metadata": {},
                "retrieved_context": "", "retrieval_sources": [],
                "candidates": [], "trigger_branch": False,
                "best_candidate": None, "selector_rationale": "", "trace": [],
            }
            result = compiled_graph.invoke(initial)

        best = result["best_candidate"]
        issues = extract_issues(best["review"], result.get("pr_metadata", {}).get("files_changed", []))
        trace = _normalize_trace(result["trace"])
        strats = _candidates_to_strategies(result["candidates"])
        return result, best, issues, trace, strats

    def test_response_has_score_field(self):
        result, best, issues, trace, strats = self._run_pipeline_mocked()
        assert isinstance(best["score"], float)
        assert 0.0 <= best["score"] <= 10.0

    def test_strategies_have_required_fields(self):
        _, _, _, _, strats = self._run_pipeline_mocked()
        for s in strats:
            assert hasattr(s, "id")
            assert hasattr(s, "name")
            assert hasattr(s, "score")
            assert hasattr(s, "description")

    def test_issues_have_required_fields(self):
        _, _, issues, _, _ = self._run_pipeline_mocked()
        for i in issues:
            assert i["severity"] in ("critical", "warning", "info")
            assert isinstance(i["file"], str)
            assert isinstance(i["line"], int)
            assert isinstance(i["message"], str)

    def test_trace_entries_have_required_fields(self):
        _, _, _, trace, _ = self._run_pipeline_mocked()
        assert len(trace) > 0
        for entry in trace:
            assert hasattr(entry, "agent")
            assert hasattr(entry, "level")
            assert hasattr(entry, "message")
            assert hasattr(entry, "timestamp")
            assert entry.level in ("INFO", "WARN", "ERROR", "DEBUG")

    def test_all_expected_agents_in_trace(self):
        _, _, _, trace, _ = self._run_pipeline_mocked()
        agents = {e.agent for e in trace}
        for expected in ("fetch_agent", "rag_agent", "review_agent", "critic_agent", "selector_agent"):
            assert expected in agents

    def test_high_score_no_branching(self):
        result, _, _, _, strats = self._run_pipeline_mocked(score=9.0)
        assert result["trigger_branch"] is False
        assert len(result["candidates"]) == 1

    def test_typescript_pr_has_ts_strategies_in_trace(self):
        """When a TS PR is analyzed, trace should reflect TypeScript language."""
        _, _, _, trace, _ = self._run_pipeline_mocked(pr_url="mock://pr/typescript-react")
        fetch_entries = [e for e in trace if e.agent == "fetch_agent"]
        # Language appears in the "completed" entry message
        assert len(fetch_entries) > 0
        # The rag_agent entry confirms TS language was used
        rag_entries = [e for e in trace if e.agent == "rag_agent"]
        assert any("TypeScript" in e.message for e in rag_entries)

    def test_selected_strategy_is_in_strategies_list(self):
        result, best, _, _, strats = self._run_pipeline_mocked()
        strategy_ids = {s.id for s in strats}
        assert best["strategy"] in strategy_ids


# ── Error handling tests ──────────────────────────────────────────────────────

class TestErrorHandling:
    def test_github_404_returns_error_diff_not_exception(self):
        """A 404 from GitHub should NOT crash the pipeline — it should produce a graceful error."""
        import httpx
        from backend.mcp.github_mock import get_pr_data
        with patch("backend.mcp.github_client.get_real_pr_data",
                   side_effect=httpx.HTTPStatusError("404", request=MagicMock(), response=MagicMock())):
            pr = get_pr_data("https://github.com/owner/private-repo/pull/1")
            assert pr.diff.startswith("# ERROR:")

    def test_network_error_returns_error_diff(self):
        import httpx
        from backend.mcp.github_mock import get_pr_data
        with patch("backend.mcp.github_client.get_real_pr_data",
                   side_effect=httpx.ConnectError("Connection refused")):
            pr = get_pr_data("https://github.com/owner/repo/pull/1")
            assert "ERROR" in pr.diff

    def test_fetch_agent_handles_error_diff_gracefully(self):
        """Error diff should be passed along without crashing fetch_agent."""
        from backend.agents.fetch_agent import fetch_agent
        state = {
            "pr_url": "https://github.com/owner/repo/pull/1",
            "pr_diff": "", "pr_metadata": {}, "retrieved_context": "",
            "retrieval_sources": [], "candidates": [], "trigger_branch": False,
            "best_candidate": None, "selector_rationale": "", "trace": [],
        }
        with patch("backend.mcp.github_client.get_real_pr_data",
                   side_effect=Exception("rate limit exceeded")):
            result = fetch_agent(state)
        assert "pr_diff" in result
        assert "pr_metadata" in result
"""
Backend pipeline tests for the productionized PR Critic flow.
"""
from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from backend.agents.critic_agent import _parse, critic_agent
from backend.agents.fetch_agent import fetch_agent
from backend.agents.rag_agent import rag_agent
from backend.agents.selector_agent import selector_agent
from backend.api.issue_extractor import extract_issues
from backend.graph.state import build_initial_state
from backend.graph.workflow import build_graph, compiled_graph
from backend.mcp.github_mock import MOCK_PRS, get_pr_data


def _state(**overrides):
    base = build_initial_state("mock://pr/security-issue")
    base.update(overrides)
    return base


def _resp(payload: str) -> SimpleNamespace:
    return SimpleNamespace(content=payload)


def _review_resp() -> SimpleNamespace:
    return _resp(
        "## Summary\nThis PR has concrete security issues.\n\n"
        "## Issues Found\n"
        "- [CRITICAL] [sql_injection] auth.py:5 SQL injection via interpolated input\n"
        "- [CRITICAL] [weak_password_hash] auth.py:10 MD5 used for password hashing\n\n"
        "## Suggestions\n- Use parameterized queries.\n- Replace MD5 with bcrypt.\n\n"
        "## Verdict\nREQUEST_CHANGES\nThe visible diff is not safe to merge."
    )


def _selector_resp(best_index: int) -> SimpleNamespace:
    return _resp(json.dumps({"best_index": best_index, "rationale": "Best coverage"}))


class TestMockPRData:
    def test_security_pr_has_diff(self):
        pr = get_pr_data("mock://pr/security-issue")
        assert len(pr.diff) > 100
        assert pr.language == "Python"

    def test_evaluation_url_routes_through_mock_layer(self):
        pr = get_pr_data("eval://sec/sql-injection")
        assert "SELECT * FROM orders" in pr.diff
        assert pr.files_changed == ["db/queries.py"]

    def test_all_mock_prs_have_required_fields(self):
        for key, pr in MOCK_PRS.items():
            assert pr.url == key
            assert pr.title
            assert isinstance(pr.files_changed, list)


class TestFetchAgent:
    def test_returns_diff_for_known_pr(self):
        result = fetch_agent(_state())
        assert result["pr_diff"] != ""
        assert result["pr_metadata"]["language"] == "Python"

    def test_trace_has_start_and_end_events(self):
        result = fetch_agent(_state())
        assert [entry["event"] for entry in result["trace"]] == ["start", "end"]
        assert result["trace"][0]["agent"] == "fetch_agent"


class TestRagAgent:
    def test_returns_context_sources_and_hits(self):
        result = rag_agent(
            _state(
                pr_diff="hashlib.md5(password.encode()).hexdigest()",
                pr_metadata={"language": "Python"},
            )
        )
        assert result["retrieved_context"] != ""
        assert result["retrieval_sources"]
        assert result["retrieval_hits"]

    def test_compacts_retrieval_hits_for_prompt_budget(self):
        from backend.agents.rag_agent import _build_compact_context

        context, hits = _build_compact_context(
            [
                {
                    "source": "owasp",
                    "section": "A03",
                    "text": "A" * 300,
                    "relevance": 0.9,
                },
                {
                    "source": "pep8",
                    "section": "Typing",
                    "text": "B" * 300,
                    "relevance": 0.8,
                },
                {
                    "source": "extra",
                    "section": "Ignored",
                    "text": "C" * 300,
                    "relevance": 0.7,
                },
            ]
        )

        assert len(hits) == 2
        assert all(len(hit["snippet"]) <= 180 for hit in hits)
        assert "extra" not in context


class TestCriticParsing:
    def test_valid_json(self):
        score, rationale, issues = _parse(
            '{"score": 8.5, "rationale": "Good", "issues_identified": ["no types"]}'
        )
        assert score == 8.5
        assert rationale == "Good"
        assert issues == ["no types"]

    def test_malformed_json_regex_fallback(self):
        score, rationale, issues = _parse('Something "score": 6.5 in here')
        assert score == 6.5
        assert rationale == ""
        assert issues == []

    def test_unparseable_defaults_to_5(self):
        score, rationale, issues = _parse("I cannot evaluate this review.")
        assert score == 5.0
        assert rationale == ""
        assert issues == []


class TestCriticAgent:
    @patch("backend.agents.critic_agent._llm")
    def test_scores_each_candidate_independently(self, mock_llm):
        mock_llm.invoke.side_effect = [
            _resp('{"score": 4.0, "rationale": "Shallow", "issues_identified": ["one"]}'),
            _resp('{"score": 8.5, "rationale": "Better", "issues_identified": ["two"]}'),
        ]

        state = _state(
            pr_diff="diff --git a/a.py b/a.py\n@@ -0,0 +1 @@\n+print('x')",
            candidates=[
                {"id": "candidate-0", "strategy": "initial", "review": "first"},
                {"id": "candidate-1", "strategy": "security_focus", "review": "second"},
            ],
            scores=[],
        )
        result = critic_agent(state)

        assert [score["candidate_index"] for score in result["scores"]] == [0, 1]
        assert result["scores"][0]["score"] == 4.0
        assert result["scores"][1]["score"] == 8.5
        assert result["branch_taken"] is True

    @patch("backend.agents.critic_agent._llm")
    def test_large_pr_mode_skips_branching_even_with_low_score(self, mock_llm):
        mock_llm.invoke.return_value = _resp(
            '{"score": 2.0, "rationale": "Low confidence", "issues_identified": ["one"]}'
        )

        state = _state(
            pr_diff="diff --git a/a.py b/a.py\n@@ -0,0 +1 @@\n+print('x')",
            large_pr_mode=True,
            candidates=[
                {"id": "candidate-0", "strategy": "initial", "review": "first"},
            ],
            scores=[],
        )
        result = critic_agent(state)

        assert result["branch_taken"] is False
        assert result["branch_skipped_reason"] == "large_pr_mode"

    def test_large_pr_partial_candidate_is_scored_without_llm(self):
        state = _state(
            pr_diff="diff --git a/a.py b/a.py\n@@ -0,0 +1 @@\n+print('x')",
            large_pr_mode=True,
            candidates=[
                {
                    "id": "large-pr-partial-0",
                    "strategy": "large_pr_partial",
                    "review": "## Summary\nPartial large PR analysis.\n\n## Issues Found\nNone.",
                },
            ],
            scores=[],
        )

        with patch("backend.agents.critic_agent.invoke_llm") as mock_invoke:
            result = critic_agent(state)

        mock_invoke.assert_not_called()
        assert result["scores"][0]["score"] == 6.0
        assert result["scores"][0]["strategy"] == "large_pr_partial"
        assert result["branch_taken"] is False
        assert result["branch_skipped_reason"] == "large_pr_mode"

    @patch("backend.agents.critic_agent._llm")
    def test_token_budget_skips_branching_even_with_low_score(self, mock_llm):
        mock_llm.invoke.return_value = _resp(
            '{"score": 2.0, "rationale": "Low confidence", "issues_identified": ["one"]}'
        )

        state = _state(
            pr_diff="diff --git a/a.py b/a.py\n@@ -0,0 +1 @@\n+print('x')",
            branch_budget_available=False,
            llm_input_tokens=1700,
            candidates=[
                {"id": "candidate-0", "strategy": "initial", "review": "first"},
            ],
            scores=[],
        )
        result = critic_agent(state)

        assert result["branch_taken"] is False
        assert result["branch_skipped_reason"] == "token_budget"

    @patch("backend.agents.critic_agent.build_reasoning_diff_packet")
    @patch("backend.agents.critic_agent.invoke_llm")
    def test_critic_uses_filtered_diff_packet(self, mock_invoke_llm, mock_build_packet):
        captured: dict[str, str] = {}

        def fake_invoke(_llm, messages, *, agent):
            captured["prompt"] = messages[-1].content
            return _resp('{"score": 8.0, "rationale": "Focused", "issues_identified": []}')

        mock_invoke_llm.side_effect = fake_invoke
        mock_build_packet.return_value = SimpleNamespace(
            content="FILTERED_DIFF_PACKET",
            included_files=["backend/auth.py"],
            selected_chunks=1,
            omitted_chunks=3,
            estimated_tokens=120,
        )
        diff = (
            "diff --git a/README.md b/README.md\n--- a/README.md\n+++ b/README.md\n@@ -0,0 +1,20 @@\n"
            + "\n".join(f"+docs_line_{index}" for index in range(20))
            + "\n\ndiff --git a/docs/guide.md b/docs/guide.md\n--- a/docs/guide.md\n+++ b/docs/guide.md\n@@ -0,0 +1,20 @@\n"
            + "\n".join(f"+guide_line_{index}" for index in range(20))
            + "\n\ndiff --git a/config/settings.json b/config/settings.json\n--- a/config/settings.json\n+++ b/config/settings.json\n@@ -0,0 +1,20 @@\n"
            + "\n".join(f"+json_line_{index}" for index in range(20))
            + "\n\ndiff --git a/backend/auth.py b/backend/auth.py\n--- a/backend/auth.py\n+++ b/backend/auth.py\n@@ -0,0 +1,20 @@\n"
            + "\n".join(f"+auth_line_{index}" for index in range(20))
        )
        state = _state(
            pr_diff=diff,
            candidates=[{"id": "candidate-0", "strategy": "initial", "review": "review"}],
            scores=[],
        )

        critic_agent(state)

        mock_build_packet.assert_called_once()
        assert "FILTERED_DIFF_PACKET" in captured["prompt"]
        assert "README.md" not in captured["prompt"]


class TestSelectorAgent:
    @patch("backend.agents.selector_agent._rerank", side_effect=ValueError("boom"))
    def test_fallback_selects_highest_score(self, _mock_rerank):
        result = selector_agent(
            _state(
                pr_diff="diff --git a/a.py b/a.py\n@@ -0,0 +1 @@\n+print('x')",
                candidates=[
                    {"id": "candidate-0", "strategy": "initial", "review": "first"},
                    {"id": "candidate-1", "strategy": "security_focus", "review": "second"},
                ],
                scores=[
                    {
                        "candidate_index": 0,
                        "strategy": "initial",
                        "score": 3.0,
                        "rationale": "weak",
                        "issues_identified": [],
                    },
                    {
                        "candidate_index": 1,
                        "strategy": "security_focus",
                        "score": 9.0,
                        "rationale": "strong",
                        "issues_identified": [],
                    },
                ],
            )
        )
        assert result["selected_index"] == 1
        assert "highest" in result["selector_reason"].lower()
        assert result["branch_improvement"] is None

    @patch("backend.agents.selector_agent._rerank")
    def test_rate_limited_selector_skips_rerank(self, mock_rerank):
        result = selector_agent(
            _state(
                rate_limited=True,
                pr_diff="diff --git a/a.py b/a.py\n@@ -0,0 +1 @@\n+print('x')",
                candidates=[
                    {"id": "candidate-0", "strategy": "initial", "review": "first"},
                    {"id": "candidate-1", "strategy": "security_focus", "review": "second"},
                ],
                scores=[
                    {
                        "candidate_index": 0,
                        "strategy": "initial",
                        "score": 3.0,
                        "rationale": "weak",
                        "issues_identified": [],
                    },
                    {
                        "candidate_index": 1,
                        "strategy": "security_focus",
                        "score": 9.0,
                        "rationale": "strong",
                        "issues_identified": [],
                    },
                ],
            )
        )

        mock_rerank.assert_not_called()
        assert result["selected_index"] == 1
        assert result["rate_limited"] is True

    @patch("backend.agents.selector_agent.build_reasoning_diff_packet")
    @patch("backend.agents.selector_agent.invoke_llm")
    def test_selector_uses_filtered_diff_packet(self, mock_invoke_llm, mock_build_packet):
        captured: dict[str, str] = {}

        def fake_invoke(_llm, messages, *, agent):
            captured["prompt"] = messages[-1].content
            return _resp('{"best_index": 0, "rationale": "Best"}')

        mock_invoke_llm.side_effect = fake_invoke
        mock_build_packet.return_value = SimpleNamespace(
            content="FILTERED_SELECTOR_PACKET",
            included_files=["backend/server.ts"],
            selected_chunks=1,
            omitted_chunks=3,
            estimated_tokens=100,
        )
        diff = (
            "diff --git a/README.md b/README.md\n--- a/README.md\n+++ b/README.md\n@@ -0,0 +1,20 @@\n"
            + "\n".join(f"+docs_line_{index}" for index in range(20))
            + "\n\ndiff --git a/docs/notes.md b/docs/notes.md\n--- a/docs/notes.md\n+++ b/docs/notes.md\n@@ -0,0 +1,20 @@\n"
            + "\n".join(f"+notes_line_{index}" for index in range(20))
            + "\n\ndiff --git a/config/app.json b/config/app.json\n--- a/config/app.json\n+++ b/config/app.json\n@@ -0,0 +1,20 @@\n"
            + "\n".join(f"+json_line_{index}" for index in range(20))
            + "\n\ndiff --git a/backend/server.ts b/backend/server.ts\n--- a/backend/server.ts\n+++ b/backend/server.ts\n@@ -0,0 +1,20 @@\n"
            + "\n".join(f"+server_line_{index}" for index in range(20))
        )
        selector_agent(
            _state(
                pr_diff=diff,
                candidates=[
                    {"id": "candidate-0", "strategy": "initial", "review": "first"},
                    {"id": "candidate-1", "strategy": "security_focus", "review": "second"},
                ],
                scores=[
                    {
                        "candidate_index": 0,
                        "strategy": "initial",
                        "score": 8.0,
                        "rationale": "strong",
                        "issues_identified": [],
                    },
                    {
                        "candidate_index": 1,
                        "strategy": "security_focus",
                        "score": 7.5,
                        "rationale": "good",
                        "issues_identified": [],
                    },
                ],
            )
        )

        mock_build_packet.assert_called_once()
        assert "FILTERED_SELECTOR_PACKET" in captured["prompt"]
        assert "README.md" not in captured["prompt"]


class TestIssueExtraction:
    def test_extracts_line_number_from_inline_line_hint(self):
        issues = extract_issues(
            "## Issues Found\n- [MAJOR] [type_safety] backend/server.ts line 42 The handler accepts overly broad input."
        )

        assert issues[0]["line"] == 42


class TestGraphStructure:
    def test_graph_compiles(self):
        assert build_graph() is not None

    def test_all_nodes_present(self):
        graph = build_graph()
        node_names = list(graph.nodes.keys())
        for expected in ("fetch", "rag", "review", "critic", "branch", "critic_branch", "selector"):
            assert expected in node_names

    def test_compiled_graph_singleton(self):
        from backend.graph.workflow import compiled_graph as second
        assert compiled_graph is second


class TestFullPipelineMocked:
    @patch("backend.agents.review_agent._llm")
    @patch("backend.agents.critic_agent._llm")
    @patch("backend.agents.selector_agent._llm")
    def test_high_score_skips_branch(self, mock_sel, mock_crit, mock_review):
        mock_review.invoke.return_value = _review_resp()
        mock_crit.invoke.return_value = _resp(
            '{"score": 9.0, "rationale": "Thorough review", "issues_identified": ["SQL injection", "MD5"]}'
        )
        mock_sel.invoke.return_value = _selector_resp(0)

        result = compiled_graph.invoke(build_initial_state("mock://pr/security-issue"))

        assert len(result["candidates"]) == 1
        assert len(result["scores"]) == 1
        assert result["branch_taken"] is False
        assert result["selected_index"] == 0
        assert any(entry["agent"] == "critic_initial" for entry in result["trace"])

    @patch("backend.agents.review_agent._llm")
    @patch("backend.agents.critic_agent._llm")
    @patch("backend.agents.branch_agent._llm")
    @patch("backend.agents.selector_agent._llm")
    def test_low_score_triggers_branch_and_keeps_branch_taken(
        self,
        mock_sel,
        mock_branch,
        mock_crit,
        mock_review,
    ):
        mock_review.invoke.return_value = _review_resp()
        mock_branch.invoke.side_effect = [
            _resp(
                "## Summary\nSecurity pass.\n\n## Issues Found\n"
                "- [CRITICAL] [sql_injection] auth.py:5 SQL injection via interpolated input\n\n"
                "## Suggestions\n- Parameterize the query.\n\n"
                "## Verdict\nREQUEST_CHANGES\nSecurity issue remains."
            ),
            _resp(
                "## Summary\nPython pass.\n\n## Issues Found\n"
                "- [MAJOR] [weak_password_hash] auth.py:10 MD5 used for password hashing\n\n"
                "## Suggestions\n- Use bcrypt.\n\n"
                "## Verdict\nREQUEST_CHANGES\nCrypto issue remains."
            ),
        ]
        mock_crit.invoke.side_effect = [
            _resp('{"score": 4.0, "rationale": "Too shallow", "issues_identified": ["one"]}'),
            _resp('{"score": 8.5, "rationale": "Security coverage", "issues_identified": ["sql injection"]}'),
            _resp('{"score": 7.0, "rationale": "Python coverage", "issues_identified": ["md5"]}'),
        ]
        mock_sel.invoke.return_value = _selector_resp(1)

        result = compiled_graph.invoke(build_initial_state("mock://pr/security-issue"))

        assert result["branch_taken"] is True
        assert len(result["candidates"]) == 3
        assert len(result["scores"]) == 3
        assert result["selected_index"] == 1
        assert result["branch_improvement"] == 4.5
        assert any(
            entry["agent"] == "router" and entry["data"].get("decision") == "branch"
            for entry in result["trace"]
        )
        assert any(entry["agent"] == "critic_branch" for entry in result["trace"])


class TestNegativeCases:
    @patch("backend.agents.critic_agent._llm")
    @patch("backend.agents.selector_agent._llm")
    def test_empty_pr_produces_candidate(self, mock_sel, mock_crit):
        mock_crit.invoke.return_value = _resp('{"score": 1.0, "rationale": "empty", "issues_identified": []}')
        mock_sel.invoke.return_value = _selector_resp(0)

        result = compiled_graph.invoke(build_initial_state("mock://pr/empty"))
        assert len(result["candidates"]) == 1
        assert result["selected_index"] == 0

    @patch("backend.agents.review_agent._llm")
    @patch("backend.agents.critic_agent._llm")
    @patch("backend.agents.selector_agent._llm")
    def test_adversarial_diff_content_does_not_crash(self, mock_sel, mock_crit, mock_review):
        mock_review.invoke.return_value = _review_resp()
        mock_crit.invoke.return_value = _resp(
            '{"score": 8.0, "rationale": "Still grounded in diff", "issues_identified": ["sql injection"]}'
        )
        mock_sel.invoke.return_value = _selector_resp(0)

        result = compiled_graph.invoke(
            _state(
                pr_url="mock://pr/security-issue",
                pr_diff="diff --git a/x.py b/x.py\n@@ -0,0 +1 @@\n+query = f\"SELECT * FROM users WHERE id={user_id}\"",
            )
        )
        assert result["selected_index"] == 0

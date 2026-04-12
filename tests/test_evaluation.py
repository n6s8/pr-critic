"""
tests/test_evaluation.py

Tests for:
  - scenario definitions (schema, counts, uniqueness)
  - metrics computation (all formulas)
  - evaluation runner (mock mode, filtering, output)
"""
import json
import math
import os
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("GROQ_API_KEY", "test_key")

from evaluation.scenarios import SCENARIOS, _CATEGORIES
from evaluation.metrics import (
    make_run_result,
    compute_summary,
    format_summary_table,
)


# ── Scenario schema tests ─────────────────────────────────────────────────────

class TestScenarioDefinitions:
    def test_at_least_20_scenarios(self):
        assert len(SCENARIOS) >= 20, f"Only {len(SCENARIOS)} scenarios"

    def test_all_ids_unique(self):
        ids = [s["id"] for s in SCENARIOS]
        assert len(ids) == len(set(ids)), "Duplicate scenario IDs found"

    def test_all_required_fields_present(self):
        required = {"id", "name", "category", "expected_issues", "diff"}
        for s in SCENARIOS:
            missing = required - set(s.keys())
            assert not missing, f"{s['id']} missing: {missing}"

    def test_all_categories_are_valid(self):
        valid = {"security", "style", "design", "edge", "adversarial"}
        for s in SCENARIOS:
            assert s["category"] in valid, \
                f"{s['id']} has invalid category '{s['category']}'"

    def test_expected_issues_is_list(self):
        for s in SCENARIOS:
            assert isinstance(s["expected_issues"], list), \
                f"{s['id']} expected_issues must be list"

    def test_diff_is_string(self):
        for s in SCENARIOS:
            assert isinstance(s["diff"], str), f"{s['id']} diff must be string"

    def test_has_security_scenarios(self):
        security = [s for s in SCENARIOS if s["category"] == "security"]
        assert len(security) >= 5

    def test_has_adversarial_scenarios(self):
        adversarial = [s for s in SCENARIOS if s["category"] == "adversarial"]
        assert len(adversarial) >= 2

    def test_has_edge_case_scenarios(self):
        edge = [s for s in SCENARIOS if s["category"] == "edge"]
        assert len(edge) >= 2

    def test_empty_diff_scenario_exists(self):
        empties = [s for s in SCENARIOS if s["diff"].strip() == ""]
        assert len(empties) >= 1, "Need at least one empty-diff scenario"

    def test_ids_follow_naming_convention(self):
        for s in SCENARIOS:
            assert s["id"].startswith("eval://"), \
                f"{s['id']} should start with 'eval://'"


# ── Metrics unit tests ────────────────────────────────────────────────────────

class TestMakeRunResult:
    def test_returns_dict_with_all_fields(self):
        r = make_run_result(
            scenario_id="eval://test",
            scenario_name="Test",
            category="security",
            expected_issues=["sql"],
            score=7.5,
            triggered_branch=True,
            n_candidates=3,
            selected_strategy="security_focus",
            latency_ms=1234.5,
            retrieval_sources=["owasp_top10"],
            review_text="This is a review.",
        )
        assert r["scenario_id"] == "eval://test"
        assert r["score"] == 7.5
        assert r["triggered_branch"] is True
        assert r["n_candidates"] == 3
        assert r["selected_strategy"] == "security_focus"
        assert r["error"] is None

    def test_score_rounded_to_2dp(self):
        r = make_run_result(
            "id", "name", "cat", [], 7.123456, False, 1, "initial",
            500.0, [], "review",
        )
        assert r["score"] == 7.12

    def test_review_preview_truncated(self):
        long_review = "A" * 1000
        r = make_run_result("id", "n", "cat", [], 5.0, False, 1, "initial",
                            100.0, [], long_review)
        assert len(r["review_preview"]) <= 400

    def test_error_field_set(self):
        r = make_run_result("id", "n", "cat", [], 0.0, False, 0, "error",
                            10.0, [], "", error="Something broke")
        assert r["error"] == "Something broke"


class TestComputeSummary:
    def _make_results(self, scores: list[float],
                      branched: list[bool] | None = None,
                      categories: list[str] | None = None,
                      strategies: list[str] | None = None) -> list[dict]:
        n = len(scores)
        branched = branched or [False] * n
        categories = categories or ["security"] * n
        strategies = strategies or ["initial"] * n
        return [
            make_run_result(
                f"eval://s/{i}", f"Scenario {i}", categories[i], [],
                scores[i], branched[i], 1 + int(branched[i]) * 2,
                strategies[i], 500.0, [], "review text"
            )
            for i in range(n)
        ]

    def test_avg_score_correct(self):
        results = self._make_results([8.0, 6.0, 4.0])
        summary = compute_summary(results)
        assert summary["avg_score"] == 6.0

    def test_branching_rate_correct(self):
        results = self._make_results(
            [5.0, 8.0, 5.0, 8.0],
            branched=[True, False, True, False],
        )
        summary = compute_summary(results)
        assert summary["branching_rate_pct"] == 50.0
        assert summary["branched_count"] == 2

    def test_zero_branching_rate(self):
        results = self._make_results([9.0, 8.5, 7.5])
        summary = compute_summary(results)
        assert summary["branching_rate_pct"] == 0.0

    def test_100_percent_branching_rate(self):
        results = self._make_results([4.0, 3.0], branched=[True, True])
        summary = compute_summary(results)
        assert summary["branching_rate_pct"] == 100.0

    def test_score_distribution_buckets(self):
        results = self._make_results([2.0, 4.5, 6.5, 9.0])
        summary = compute_summary(results)
        dist = summary["score_distribution"]
        assert dist.get("0-3 (poor)", 0) == 1
        assert dist.get("4-5 (weak)", 0) == 1
        assert dist.get("6-7 (adequate)", 0) == 1
        assert dist.get("8-10 (good)", 0) == 1

    def test_strategy_distribution(self):
        results = self._make_results(
            [8.0, 8.0, 6.0],
            strategies=["initial", "initial", "security_focus"],
        )
        summary = compute_summary(results)
        assert summary["strategy_distribution"]["initial"] == 2
        assert summary["strategy_distribution"]["security_focus"] == 1
        assert summary["most_common_strategy"] == "initial"

    def test_latency_stats(self):
        r = self._make_results([7.0])
        r[0]["latency_ms"] = 1000.0
        summary = compute_summary(r)
        assert summary["avg_latency_ms"] == 1000.0

    def test_per_category_avg(self):
        results = self._make_results(
            [8.0, 6.0, 4.0, 2.0],
            categories=["security", "security", "style", "style"],
        )
        summary = compute_summary(results)
        assert summary["category_avg_score"]["security"] == 7.0
        assert summary["category_avg_score"]["style"] == 3.0

    def test_errored_runs_excluded_from_averages(self):
        results = self._make_results([8.0, 6.0])
        # Add a failed run
        failed = make_run_result("eval://fail", "fail", "security", [],
                                 0.0, False, 0, "error", 10.0, [], "",
                                 error="LLM call failed")
        all_results = results + [failed]
        summary = compute_summary(all_results)
        assert summary["successful_runs"] == 2
        assert summary["failed_runs"] == 1
        assert summary["avg_score"] == 7.0  # only the two successful ones

    def test_all_runs_failed(self):
        failed = make_run_result("e", "n", "c", [], 0.0, False, 0, "e",
                                 0.0, [], "", error="fail")
        summary = compute_summary([failed])
        assert "error" in summary

    def test_min_max_score(self):
        results = self._make_results([3.0, 7.0, 9.5])
        summary = compute_summary(results)
        assert summary["min_score"] == 3.0
        assert summary["max_score"] == 9.5

    def test_total_counts(self):
        results = self._make_results([5.0, 8.0, 3.0])
        summary = compute_summary(results)
        assert summary["total_scenarios"] == 3
        assert summary["successful_runs"] == 3


class TestFormatSummaryTable:
    def test_returns_string(self):
        results = [make_run_result("e", "n", "security", [], 7.0, False,
                                  1, "initial", 300.0, [], "review")]
        summary = compute_summary(results)
        table = format_summary_table(summary)
        assert isinstance(table, str)
        assert len(table) > 100

    def test_contains_key_metrics(self):
        results = [make_run_result("e", "n", "security", [], 7.5, True,
                                  3, "security_focus", 400.0, [], "review")]
        summary = compute_summary(results)
        table = format_summary_table(summary)
        assert "7.5" in table
        assert "100.0%" in table   # 1/1 branching
        assert "security_focus" in table


# ── Evaluation runner integration test ───────────────────────────────────────

class TestEvaluationRunner:
    """Run the full evaluation in mock mode and validate the output JSON."""

    def test_mock_run_produces_valid_json(self, tmp_path):
        out = tmp_path / "results.json"
        # Run via subprocess to keep environment clean
        import subprocess
        proc = subprocess.run(
            [sys.executable, "scripts/run_evaluation.py",
             "--mock", "--output", str(out)],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            env={**os.environ, "GROQ_API_KEY": "test_key"},
        )
        assert proc.returncode == 0, f"Runner failed:\n{proc.stderr}"
        assert out.exists(), "Output file not created"

        data = json.loads(out.read_text())
        assert "meta" in data
        assert "summary" in data
        assert "results" in data
        assert len(data["results"]) == len(SCENARIOS)

    def test_mock_run_all_scenarios_have_results(self, tmp_path):
        out = tmp_path / "results.json"
        import subprocess
        subprocess.run(
            [sys.executable, "scripts/run_evaluation.py",
             "--mock", "--output", str(out)],
            cwd=str(ROOT), capture_output=True,
            env={**os.environ, "GROQ_API_KEY": "test_key"},
        )
        data = json.loads(out.read_text())
        result_ids = {r["scenario_id"] for r in data["results"]}
        scenario_ids = {s["id"] for s in SCENARIOS}
        assert result_ids == scenario_ids

    def test_mock_run_summary_fields(self, tmp_path):
        out = tmp_path / "results.json"
        import subprocess
        subprocess.run(
            [sys.executable, "scripts/run_evaluation.py",
             "--mock", "--output", str(out)],
            cwd=str(ROOT), capture_output=True,
            env={**os.environ, "GROQ_API_KEY": "test_key"},
        )
        summary = json.loads(out.read_text())["summary"]
        for field in ("avg_score", "branching_rate_pct", "score_distribution",
                      "strategy_distribution", "most_common_strategy",
                      "avg_latency_ms", "category_avg_score"):
            assert field in summary, f"Missing summary field: {field}"

    def test_category_filter(self, tmp_path):
        out = tmp_path / "security_only.json"
        import subprocess
        subprocess.run(
            [sys.executable, "scripts/run_evaluation.py",
             "--mock", "--categories", "security", "--output", str(out)],
            cwd=str(ROOT), capture_output=True,
            env={**os.environ, "GROQ_API_KEY": "test_key"},
        )
        data = json.loads(out.read_text())
        categories = {r["category"] for r in data["results"]}
        assert categories == {"security"}

    def test_single_scenario_filter(self, tmp_path):
        out = tmp_path / "one.json"
        import subprocess
        subprocess.run(
            [sys.executable, "scripts/run_evaluation.py",
             "--mock", "--scenario", "sql-injection", "--output", str(out)],
            cwd=str(ROOT), capture_output=True,
            env={**os.environ, "GROQ_API_KEY": "test_key"},
        )
        data = json.loads(out.read_text())
        assert len(data["results"]) == 1
        assert "sql-injection" in data["results"][0]["scenario_id"]

    def test_output_has_meta_fields(self, tmp_path):
        out = tmp_path / "meta.json"
        import subprocess
        subprocess.run(
            [sys.executable, "scripts/run_evaluation.py",
             "--mock", "--output", str(out)],
            cwd=str(ROOT), capture_output=True,
            env={**os.environ, "GROQ_API_KEY": "test_key"},
        )
        meta = json.loads(out.read_text())["meta"]
        assert "run_at" in meta
        assert "mode" in meta
        assert meta["mode"] == "mock"
        assert "groq_generation_model" in meta

    def test_each_result_has_required_fields(self, tmp_path):
        out = tmp_path / "fields.json"
        import subprocess
        subprocess.run(
            [sys.executable, "scripts/run_evaluation.py",
             "--mock", "--output", str(out)],
            cwd=str(ROOT), capture_output=True,
            env={**os.environ, "GROQ_API_KEY": "test_key"},
        )
        required = {"scenario_id", "scenario_name", "category", "score",
                    "triggered_branch", "n_candidates", "selected_strategy",
                    "latency_ms", "retrieval_sources", "review_preview", "error"}
        for r in json.loads(out.read_text())["results"]:
            missing = required - set(r.keys())
            assert not missing, f"Result {r.get('scenario_id')} missing: {missing}"

"""
Evaluation metrics and runner tests.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("GROQ_API_KEY", "test_key")

from evaluation.metrics import (
    compute_summary,
    evaluate_issue_quality,
    format_summary_table,
    make_run_result,
)
from evaluation.scenarios import SCENARIOS


class TestScenarioDefinitions:
    def test_at_least_20_scenarios(self):
        assert len(SCENARIOS) >= 20

    def test_all_ids_unique(self):
        ids = [scenario["id"] for scenario in SCENARIOS]
        assert len(ids) == len(set(ids))

    def test_all_required_fields_present(self):
        required = {"id", "name", "category", "expected_issues", "diff"}
        for scenario in SCENARIOS:
            assert required <= set(scenario.keys())


class TestIssueQuality:
    def test_matches_expected_issues_and_false_positives(self):
        quality = evaluate_issue_quality(
            ["sql injection", "parameterized", "owasp"],
            [
                "SQL injection risk from interpolated input; use parameterized queries.",
                "Function should be renamed.",
            ],
            "Reference: OWASP A03 Injection",
        )

        assert quality["matched_expected_issues"] == ["sql injection", "parameterized", "owasp"]
        assert quality["false_positives"] == 1
        assert quality["precision"] == 0.5
        assert quality["recall"] == 1.0

    def test_clean_review_with_no_expected_issues_scores_perfectly(self):
        quality = evaluate_issue_quality([], [], "No actionable issues found.")
        assert quality["precision"] == 1.0
        assert quality["recall"] == 1.0
        assert quality["f1"] == 1.0


class TestRunResultAndSummary:
    def test_make_run_result_contains_quality_fields(self):
        result = make_run_result(
            scenario_id="eval://test",
            scenario_name="Test",
            category="security",
            expected_issues=["sql injection"],
            review_score=8.5,
            precision=1.0,
            recall=0.5,
            f1=0.6667,
            false_positives=0,
            found_issues=["SQL injection risk from interpolated input."],
            matched_expected_issues=["sql injection"],
            unmatched_expected_issues=[],
            matched_found_issues=["SQL injection risk from interpolated input."],
            false_positive_issues=[],
            triggered_branch=True,
            n_candidates=3,
            selected_strategy="security_focus",
            latency_ms=1234.5,
            retrieval_sources=["owasp_top10"],
            review_text="A review body",
        )
        assert result["review_score"] == 8.5
        assert result["precision"] == 1.0
        assert result["recall"] == 0.5
        assert result["f1"] == 0.6667

    def test_compute_summary_aggregates_precision_recall_and_false_positives(self):
        results = [
            make_run_result(
                "eval://one",
                "One",
                "security",
                ["sql injection"],
                8.0,
                1.0,
                1.0,
                1.0,
                0,
                ["SQL injection risk."],
                ["sql injection"],
                [],
                ["SQL injection risk."],
                [],
                False,
                1,
                "initial",
                500.0,
                [],
                "review",
            ),
            make_run_result(
                "eval://two",
                "Two",
                "style",
                ["bare except"],
                4.0,
                0.5,
                0.5,
                0.5,
                1,
                ["Bare except catches everything.", "Naming could improve."],
                ["bare except"],
                [],
                ["Bare except catches everything."],
                ["Naming could improve."],
                True,
                3,
                "python_idioms",
                700.0,
                [],
                "review",
            ),
        ]
        summary = compute_summary(results)
        assert summary["avg_precision"] == 0.75
        assert summary["avg_recall"] == 0.75
        assert summary["avg_f1"] == 0.75
        assert summary["total_false_positives"] == 1
        assert summary["branching_rate_pct"] == 50.0

    def test_summary_table_mentions_quality_metrics(self):
        summary = compute_summary(
            [
                make_run_result(
                    "eval://one",
                    "One",
                    "security",
                    ["sql injection"],
                    8.0,
                    1.0,
                    1.0,
                    1.0,
                    0,
                    ["SQL injection risk."],
                    ["sql injection"],
                    [],
                    ["SQL injection risk."],
                    [],
                    False,
                    1,
                    "initial",
                    500.0,
                    [],
                    "review",
                )
            ]
        )
        table = format_summary_table(summary)
        assert "Avg precision" in table
        assert "Avg F1" in table


class TestEvaluationRunner:
    def test_mock_run_produces_valid_json(self, tmp_path):
        out = tmp_path / "results.json"
        proc = subprocess.run(
            [
                sys.executable,
                "scripts/run_evaluation.py",
                "--mock",
                "--scenario",
                "sql-injection",
                "--output",
                str(out),
            ],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            env={**os.environ, "GROQ_API_KEY": "test_key"},
        )
        assert proc.returncode == 0, proc.stderr
        payload = json.loads(out.read_text(encoding="utf-8"))
        assert payload["meta"]["mode"] == "mock"
        assert payload["summary"]["avg_precision"] >= 0.0
        assert payload["results"][0]["scenario_id"].endswith("sql-injection")

    def test_category_filter_only_returns_requested_categories(self, tmp_path):
        out = tmp_path / "security_only.json"
        proc = subprocess.run(
            [
                sys.executable,
                "scripts/run_evaluation.py",
                "--mock",
                "--categories",
                "security",
                "--output",
                str(out),
            ],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            env={**os.environ, "GROQ_API_KEY": "test_key"},
        )
        assert proc.returncode == 0, proc.stderr
        payload = json.loads(out.read_text(encoding="utf-8"))
        assert {result["category"] for result in payload["results"]} == {"security"}

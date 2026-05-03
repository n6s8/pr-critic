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
from evaluation.real_world_cases import load_real_world_cases
from evaluation.scenarios import SCENARIOS


def _issue(file: str, issue_type: str, description: str) -> dict[str, str]:
    return {
        "file": file,
        "type": issue_type,
        "description": description,
    }


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
            for issue in scenario["expected_issues"]:
                assert {"file", "type", "description"} <= set(issue.keys())

    def test_real_world_cases_have_required_fields(self):
        cases = load_real_world_cases()
        assert len(cases) >= 3
        for case in cases:
            assert {"id", "pr_url", "name", "category", "expected_issues"} <= set(case.keys())

    def test_real_world_dataset_balances_clean_and_issue_detection_cases(self):
        cases = load_real_world_cases()
        clean_cases = [case for case in cases if not case["expected_issues"]]
        issue_cases = [case for case in cases if case["expected_issues"]]

        assert len(clean_cases) >= 3
        assert len(issue_cases) >= 3

        issue_types = {
            issue["type"]
            for case in issue_cases
            for issue in case["expected_issues"]
        }
        assert {"missing_validation", "weak_password_hash", "broad_exception"} <= issue_types


class TestIssueQuality:
    def test_matches_expected_issues_by_type_and_file(self):
        quality = evaluate_issue_quality(
            [_issue("auth.py", "sql_injection", "Interpolated input is used in SQL.")],
            [_issue("auth.py", "sql_injection", "Use parameterized queries instead of interpolated SQL.")],
        )

        assert quality["matched_expected_issues"] == [
            _issue("auth.py", "sql_injection", "Interpolated input is used in SQL.")
        ]
        assert quality["matched_detected_issues"] == [
            _issue("auth.py", "sql_injection", "Use parameterized queries instead of interpolated SQL.")
        ]
        assert quality["false_positives"] == 0
        assert quality["precision"] == 1.0
        assert quality["recall"] == 1.0

    def test_clean_review_with_no_expected_issues_scores_perfectly(self):
        quality = evaluate_issue_quality([], [])
        assert quality["precision"] == 1.0
        assert quality["recall"] == 1.0
        assert quality["f1"] == 1.0

    def test_incorrect_file_creates_false_positive(self):
        quality = evaluate_issue_quality(
            [_issue("auth.py", "sql_injection", "Unsafe SQL string formatting.")],
            [_issue("other.py", "sql_injection", "Unsafe SQL string formatting.")],
        )
        assert quality["matched_issue_count"] == 0
        assert quality["false_positives"] == 1
        assert quality["recall"] == 0.0


class TestRunResultAndSummary:
    def test_make_run_result_contains_issue_level_fields(self):
        result = make_run_result(
            scenario_id="eval://test",
            scenario_name="Test",
            category="security",
            expected_issues=[_issue("auth.py", "sql_injection", "Unsafe SQL formatting.")],
            review_score=8.5,
            precision=1.0,
            recall=0.5,
            f1=0.6667,
            false_positives=0,
            detected_issues=[_issue("auth.py", "sql_injection", "Use parameterized queries.")],
            matched_expected_issues=[_issue("auth.py", "sql_injection", "Unsafe SQL formatting.")],
            unmatched_expected_issues=[],
            matched_detected_issues=[_issue("auth.py", "sql_injection", "Use parameterized queries.")],
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
        assert result["detected_issues"][0]["type"] == "sql_injection"

    def test_compute_summary_aggregates_precision_recall_and_false_positives(self):
        results = [
            make_run_result(
                "eval://one",
                "One",
                "security",
                [_issue("auth.py", "sql_injection", "Unsafe SQL formatting.")],
                8.0,
                1.0,
                1.0,
                1.0,
                0,
                [_issue("auth.py", "sql_injection", "Use parameterized queries.")],
                [_issue("auth.py", "sql_injection", "Unsafe SQL formatting.")],
                [],
                [_issue("auth.py", "sql_injection", "Use parameterized queries.")],
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
                [_issue("worker.py", "bare_except", "Bare except hides failures.")],
                4.0,
                0.5,
                0.5,
                0.5,
                1,
                [
                    _issue("worker.py", "bare_except", "Catch specific exceptions."),
                    _issue("worker.py", "duplicate_logic", "This file also duplicates logic."),
                ],
                [_issue("worker.py", "bare_except", "Bare except hides failures.")],
                [],
                [_issue("worker.py", "bare_except", "Catch specific exceptions.")],
                [_issue("worker.py", "duplicate_logic", "This file also duplicates logic.")],
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
                    [_issue("auth.py", "sql_injection", "Unsafe SQL formatting.")],
                    8.0,
                    1.0,
                    1.0,
                    1.0,
                    0,
                    [_issue("auth.py", "sql_injection", "Use parameterized queries.")],
                    [_issue("auth.py", "sql_injection", "Unsafe SQL formatting.")],
                    [],
                    [_issue("auth.py", "sql_injection", "Use parameterized queries.")],
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
        assert payload["results"][0]["expected_issues"][0]["type"] == "sql_injection"

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

    def test_threshold_flags_fail_the_process(self, tmp_path):
        out = tmp_path / "threshold.json"
        proc = subprocess.run(
            [
                sys.executable,
                "scripts/run_evaluation.py",
                "--mock",
                "--scenario",
                "sql-injection",
                "--min-avg-f1",
                "1.1",
                "--output",
                str(out),
            ],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            env={**os.environ, "GROQ_API_KEY": "test_key"},
        )
        assert proc.returncode != 0
